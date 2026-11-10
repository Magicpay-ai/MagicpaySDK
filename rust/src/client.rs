use std::fmt::{self, Display};
use std::net::IpAddr;
use std::sync::{Arc, RwLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use base64::Engine;
use hmac::{Hmac, Mac};
use percent_encoding::{utf8_percent_encode, AsciiSet, NON_ALPHANUMERIC};
use rand::{distributions::Alphanumeric, Rng};
use reqwest::header::CONTENT_TYPE;
use reqwest::{redirect, Method, Url};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::error::{error_object, Error, Result};

/// RFC 3986 unreserved characters stay as-is.
const UNRESERVED: &AsciiSet = &NON_ALPHANUMERIC
    .remove(b'-')
    .remove(b'_')
    .remove(b'.')
    .remove(b'~');

/// Dev/test environment (default).
pub const SANDBOX_URL: &str = "https://trdev.magicpay.ai";
/// Live environment.
pub const PRODUCTION_URL: &str = "https://tr.magicpay.ai";
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Encoding of the `x-signature` header value (auth V1 only; V2 is always hex).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum SignatureEncoding {
    #[default]
    Hex,
    Base64,
}

/// Request signing scheme, sent as the `x-auth-version` header.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum AuthVersion {
    /// `SHA-256(url + api_key + secret_key + rnd_key)`. Not accepted by V2-only endpoints.
    V1,
    /// HMAC-SHA256 over method, url, body hash, api key, timestamp and rnd key.
    #[default]
    V2,
}

impl AuthVersion {
    pub fn as_str(self) -> &'static str {
        match self {
            AuthVersion::V1 => "V1",
            AuthVersion::V2 => "V2",
        }
    }
}

/// Client configuration. `Debug` masks the credentials.
#[derive(Clone)]
pub struct Config {
    pub api_key: String,
    pub secret_key: String,
    pub base_url: String,
    pub timeout: Duration,
    pub auth_version: AuthVersion,
    pub signature_encoding: SignatureEncoding,
    /// Initial merchant-panel JWT for endpoints that need `Authorization: Bearer`.
    /// Only read when the client is built: after [`Client::login`] or
    /// [`Client::set_access_token`], [`Client::access_token`] is authoritative.
    pub access_token: Option<String>,
    /// Allow an `http://` base URL for non-loopback hosts (tests/proxies only).
    /// Loopback http (127.0.0.1, localhost, ::1) is always allowed.
    pub allow_insecure: bool,
}

const MASK: &str = "***";

fn mask(v: &Option<String>) -> Option<&'static str> {
    v.as_ref().map(|_| MASK)
}

impl fmt::Debug for Config {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Config")
            .field("api_key", &MASK)
            .field("secret_key", &MASK)
            .field("base_url", &self.base_url)
            .field("timeout", &self.timeout)
            .field("auth_version", &self.auth_version)
            .field("signature_encoding", &self.signature_encoding)
            .field("access_token", &mask(&self.access_token))
            .field("allow_insecure", &self.allow_insecure)
            .finish()
    }
}

impl Config {
    pub fn new(api_key: impl Into<String>, secret_key: impl Into<String>) -> Self {
        Self {
            api_key: api_key.into(),
            secret_key: secret_key.into(),
            base_url: SANDBOX_URL.to_string(),
            timeout: Duration::from_secs(30),
            auth_version: AuthVersion::V2,
            signature_encoding: SignatureEncoding::Hex,
            access_token: None,
            allow_insecure: false,
        }
    }

    pub fn allow_insecure(mut self, allow: bool) -> Self {
        self.allow_insecure = allow;
        self
    }

    pub fn access_token(mut self, token: impl Into<String>) -> Self {
        self.access_token = Some(token.into());
        self
    }

    pub fn base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = url.into();
        self
    }

    pub fn timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    pub fn auth_version(mut self, version: AuthVersion) -> Self {
        self.auth_version = version;
        self
    }

    pub fn signature_encoding(mut self, encoding: SignatureEncoding) -> Self {
        self.signature_encoding = encoding;
        self
    }

    fn validate(&mut self) -> Result<()> {
        if self.api_key.is_empty() || self.secret_key.is_empty() {
            return Err(Error::Config("api_key and secret_key are required".into()));
        }
        if self.auth_version == AuthVersion::V2 && self.signature_encoding != SignatureEncoding::Hex
        {
            return Err(Error::Config(
                "signature_encoding applies to auth V1 only; V2 is always hex".into(),
            ));
        }
        self.base_url = self.base_url.trim_end_matches('/').to_string();
        let url = Url::parse(&self.base_url)
            .map_err(|e| Error::Config(format!("invalid base_url: {e}")))?;
        let host = url
            .host_str()
            .unwrap_or("")
            .trim_matches(|c| c == '[' || c == ']');
        let loopback = host.eq_ignore_ascii_case("localhost")
            || host.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback());
        match url.scheme() {
            "https" if url.host().is_some() => Ok(()),
            "http" if url.host().is_some() && (loopback || self.allow_insecure) => Ok(()),
            "http" => Err(Error::Config(
                "base_url must use https (http is allowed only for loopback hosts or with allow_insecure)"
                    .into(),
            )),
            _ => Err(Error::Config(format!("invalid base_url: {}", self.base_url))),
        }
    }
}

/// The URL form the server verifies: a leading `http://` becomes `https://`.
pub fn signing_url(url: &str) -> String {
    match url.strip_prefix("http://") {
        Some(rest) => format!("https://{rest}"),
        None => url.to_string(),
    }
}

/// Auth V1: SHA-256 over `url + api_key + secret_key + rnd_key`.
pub fn compute_signature(
    url: &str,
    api_key: &str,
    secret_key: &str,
    rnd_key: &str,
    encoding: SignatureEncoding,
) -> String {
    let mut h = Sha256::new();
    h.update(url.as_bytes());
    h.update(api_key.as_bytes());
    h.update(secret_key.as_bytes());
    h.update(rnd_key.as_bytes());
    let digest = h.finalize();
    match encoding {
        SignatureEncoding::Hex => hex::encode(digest),
        SignatureEncoding::Base64 => base64::engine::general_purpose::STANDARD.encode(digest),
    }
}

/// Auth V2: lowercase hex `HMAC-SHA256(secret_key, message)` where message is
/// `METHOD\nurl\nsha256_hex(body)\napi_key\ntimestamp\nrnd_key`.
///
/// `body` must be exactly the bytes sent on the wire (empty for no body).
pub fn compute_signature_v2(
    method: &str,
    url: &str,
    body: &[u8],
    api_key: &str,
    secret_key: &str,
    timestamp: &str,
    rnd_key: &str,
) -> String {
    let body_hash = hex::encode(Sha256::digest(body));
    let message = [
        method.to_ascii_uppercase().as_str(),
        url,
        body_hash.as_str(),
        api_key,
        timestamp,
        rnd_key,
    ]
    .join("\n");
    let mut mac = Hmac::<Sha256>::new_from_slice(secret_key.as_bytes())
        .expect("HMAC accepts keys of any length");
    mac.update(message.as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

/// URL-encode one path segment; `""`, `.` and `..` are rejected (they would change the path).
pub(crate) fn path_param(v: impl Display) -> Result<String> {
    let text = v.to_string();
    if text.is_empty() || text == "." || text == ".." {
        return Err(Error::InvalidPathParam(text));
    }
    Ok(utf8_percent_encode(&text, UNRESERVED).to_string())
}

fn encode_query(query: &[(&str, &str)]) -> String {
    query
        .iter()
        .map(|(k, v)| {
            format!(
                "{}={}",
                utf8_percent_encode(k, UNRESERVED),
                utf8_percent_encode(v, UNRESERVED)
            )
        })
        .collect::<Vec<_>>()
        .join("&")
}

/// MagicPay API client. Cheap to clone; reuse a single instance.
///
/// Clones share the access token, so [`Client::login`] on one clone applies to all.
/// `Debug` masks the credentials and the token.
#[derive(Clone)]
pub struct Client {
    config: Config,
    http: reqwest::Client,
    access_token: Arc<RwLock<Option<String>>>,
}

impl fmt::Debug for Client {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Client")
            .field("config", &self.config)
            .field("access_token", &mask(&self.access_token()))
            .finish_non_exhaustive()
    }
}

impl Client {
    pub fn new(mut config: Config) -> Result<Self> {
        config.validate()?;
        let http = reqwest::Client::builder()
            // Never follow redirects: the signed headers must not reach another URL.
            .redirect(redirect::Policy::none())
            .timeout(config.timeout)
            .user_agent(format!("magicpay-rust/{VERSION}"))
            .build()?;
        Ok(Self::build(config, http))
    }

    /// Use your own `reqwest::Client` (proxies, custom TLS, ...). Build it with
    /// `.redirect(reqwest::redirect::Policy::none())` so signed headers are never
    /// sent to a redirect target.
    pub fn with_http_client(mut config: Config, http: reqwest::Client) -> Result<Self> {
        config.validate()?;
        Ok(Self::build(config, http))
    }

    fn build(config: Config, http: reqwest::Client) -> Self {
        let token = config.access_token.clone();
        Self {
            config,
            http,
            access_token: Arc::new(RwLock::new(token)),
        }
    }

    pub fn config(&self) -> &Config {
        &self.config
    }

    /// The access token currently sent as `Authorization: Bearer`.
    pub fn access_token(&self) -> Option<String> {
        self.access_token
            .read()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }

    /// Set or clear the merchant-panel access token used for Bearer-protected endpoints.
    pub fn set_access_token(&self, token: Option<String>) {
        *self.access_token.write().unwrap_or_else(|e| e.into_inner()) = token;
    }

    /// Log in as a merchant-panel user and keep the access token for Bearer endpoints.
    ///
    /// Bad credentials come back as HTTP 200 with an `errors` body; this returns
    /// [`Error::Api`] for them.
    pub async fn login(&self, email: &str, secret_word: &str) -> Result<Value> {
        let res = self
            .users()
            .authenticate(&json!({ "email": email, "secretWord": secret_word }))
            .await?;
        if let Some(token) = res["data"]["token"]["accessToken"].as_str() {
            if !token.is_empty() {
                self.set_access_token(Some(token.to_string()));
            }
        }
        Ok(res)
    }

    pub(crate) fn build_url(&self, path: &str, query: &[(&str, &str)]) -> String {
        let mut url = self.config.base_url.clone();
        if !path.starts_with('/') {
            url.push('/');
        }
        url.push_str(path);
        if !query.is_empty() {
            url.push(if url.contains('?') { '&' } else { '?' });
            url.push_str(&encode_query(query));
        }
        url
    }

    /// Send a signed request. Use for endpoints not wrapped by the SDK.
    pub async fn request(
        &self,
        method: Method,
        path: &str,
        body: Option<Value>,
        query: &[(&str, &str)],
    ) -> Result<Value> {
        // Parse once and sign exactly the URL reqwest will send (normalized host/port).
        let url = Url::parse(&self.build_url(path, query))
            .map_err(|e| Error::Config(format!("invalid URL: {e}")))?;
        let sign_url = signing_url(url.as_str());
        // Serialize once: the signed bytes and the sent bytes must be identical.
        let payload = body.as_ref().map(serde_json::to_vec).transpose()?;
        let rnd: String = rand::thread_rng()
            .sample_iter(&Alphanumeric)
            .take(32)
            .map(char::from)
            .collect();

        let mut req = self
            .http
            .request(method.clone(), url)
            .header("Accept", "application/json")
            .header("x-api-key", &self.config.api_key)
            .header("x-rnd-key", &rnd)
            .header("x-auth-version", self.config.auth_version.as_str());
        req = match self.config.auth_version {
            AuthVersion::V2 => {
                let ts = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map(|d| d.as_secs())
                    .unwrap_or(0)
                    .to_string();
                let signature = compute_signature_v2(
                    method.as_str(),
                    &sign_url,
                    payload.as_deref().unwrap_or_default(),
                    &self.config.api_key,
                    &self.config.secret_key,
                    &ts,
                    &rnd,
                );
                req.header("x-timestamp", ts)
                    .header("x-signature", signature)
            }
            AuthVersion::V1 => req.header(
                "x-signature",
                compute_signature(
                    &sign_url,
                    &self.config.api_key,
                    &self.config.secret_key,
                    &rnd,
                    self.config.signature_encoding,
                ),
            ),
        };
        if let Some(token) = self.access_token() {
            req = req.bearer_auth(token);
        }
        if let Some(bytes) = payload {
            req = req.header(CONTENT_TYPE, "application/json").body(bytes);
        }

        let resp = req.send().await?;
        let status = resp.status().as_u16();
        let raw = resp.text().await?;
        let parsed: Option<Value> = if raw.trim().is_empty() {
            None
        } else {
            Some(serde_json::from_str(&raw).unwrap_or_else(|_| Value::String(raw.clone())))
        };

        // The API also reports some failures (e.g. bad login) as HTTP 200 + {"errors": {...}}.
        let errors_body = parsed
            .as_ref()
            .and_then(|v| v.get("errors"))
            .and_then(Value::as_object)
            .is_some_and(|o| !o.is_empty());
        // 3xx is an error too: redirects are not followed.
        if status >= 300 || errors_body {
            let (parsed, raw) = redact_token(parsed, raw);
            let message = parsed
                .as_ref()
                .and_then(api_message)
                .unwrap_or_else(|| raw.clone());
            return Err(Error::Api {
                status,
                message,
                body: parsed,
                raw,
            });
        }
        Ok(parsed.unwrap_or(Value::Null))
    }
}

/// Never put a login access token into an error.
fn redact_token(mut parsed: Option<Value>, mut raw: String) -> (Option<Value>, String) {
    if let Some(slot) = parsed
        .as_mut()
        .and_then(|v| v.pointer_mut("/data/token/accessToken"))
    {
        if let Some(token) = slot.as_str().filter(|t| !t.is_empty()).map(String::from) {
            *slot = Value::String(MASK.into());
            raw = raw.replace(&token, MASK);
        }
    }
    (parsed, raw)
}

fn as_text(v: &Value) -> String {
    v.as_str()
        .map(String::from)
        .unwrap_or_else(|| v.to_string())
}

/// Human-readable message from an error body.
fn api_message(body: &Value) -> Option<String> {
    if let Some(m) = ["message", "error"]
        .iter()
        .find_map(|k| body.get(*k).filter(|v| !v.is_null()))
    {
        return Some(as_text(m));
    }
    if let Some(d) = body.get("detail").and_then(Value::as_str) {
        return Some(d.to_string());
    }
    if let Some(errors) = error_object(body) {
        let code = errors
            .get("errorCode")
            .or_else(|| errors.get("error_code"))
            .map(as_text);
        let desc = errors
            .get("errorDescription")
            .or_else(|| errors.get("error_description"))
            .map(as_text);
        match (code, desc) {
            (Some(c), Some(d)) => return Some(format!("{c}: {d}")),
            (c, d) => {
                if let Some(x) = d.or(c) {
                    return Some(x);
                }
            }
        }
    }
    body.get("detail").filter(|v| !v.is_null()).map(as_text)
}
