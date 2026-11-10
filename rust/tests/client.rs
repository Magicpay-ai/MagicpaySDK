use std::time::{SystemTime, UNIX_EPOCH};

use magicpay::{
    compute_signature, compute_signature_v2, AuthVersion, Client, Config, Error, SignatureEncoding,
    PRODUCTION_URL, SANDBOX_URL,
};
use serde_json::json;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;

// Shared cross-SDK test vectors (see ../../README.md)
const V1_URL: &str = "https://trdev.magicpay.ai/payment/v1/card-payments/1086?page=1&size=10";
const V1_SIG: &str = "a0a1b034e46f3690306e10ad629a72f0a5c7687068b0be53239d1feb6cf824c5";
const V2_URL: &str = "https://trdev.magicpay.ai/payment/v1/card-payments/3ds-complete";
const V2_BODY: &[u8] = br#"{"paymentId":123}"#;
const V2_SIG: &str = "ece3b0b7830f3b720257c097c2a6cc4d2dafc81cb937af758231c8fedb16b495";
const LOGIN_OK: &str = r#"{"data":{"merchantId":7,"status":"Success","token":{"accessToken":"jwt-login","expiresIn":3600}}}"#;
const LOGIN_BAD: &str =
    r#"{"errors":{"errorCode":"7005","errorDescription":"E-posta adresi ya da şifre hatalı"}}"#;

#[test]
fn environment_urls() {
    assert_eq!(SANDBOX_URL, "https://trdev.magicpay.ai");
    assert_eq!(PRODUCTION_URL, "https://tr.magicpay.ai");
    assert_eq!(Config::new("k", "s").base_url, SANDBOX_URL);
    assert_eq!(Config::new("k", "s").auth_version, AuthVersion::V2);
}

#[test]
fn v1_signature_vector() {
    assert_eq!(
        compute_signature(
            V1_URL,
            "test-api-key",
            "test-secret-key",
            "abc123",
            SignatureEncoding::Hex
        ),
        V1_SIG
    );
}

#[test]
fn v2_signature_vector() {
    let sig = |m: &str| {
        compute_signature_v2(
            m,
            V2_URL,
            V2_BODY,
            "test-api-key",
            "test-secret-key",
            "1700000000",
            "abc123",
        )
    };
    assert_eq!(sig("POST"), V2_SIG);
    assert_eq!(sig("post"), V2_SIG);
}

#[test]
fn config_validation() {
    assert!(
        Client::new(Config::new("k", "s").signature_encoding(SignatureEncoding::Base64)).is_err()
    );
    assert!(Client::new(
        Config::new("k", "s")
            .auth_version(AuthVersion::V1)
            .signature_encoding(SignatureEncoding::Base64)
    )
    .is_ok());
    assert!(Client::new(Config::new("", "s")).is_err());
}

/// Local HTTP server answering one connection per response, in order; yields the raw requests.
async fn mock_seq(
    responses: Vec<(u16, &'static str)>,
) -> (String, tokio::task::JoinHandle<Vec<String>>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = format!("http://{}", listener.local_addr().unwrap());
    let handle = tokio::spawn(async move {
        let mut seen = Vec::new();
        for (status, body) in responses {
            let (mut sock, _) = listener.accept().await.unwrap();
            let mut buf = vec![0u8; 16384];
            let mut req = Vec::new();
            loop {
                let n = sock.read(&mut buf).await.unwrap();
                req.extend_from_slice(&buf[..n]);
                let s = String::from_utf8_lossy(&req).to_string();
                if let Some(i) = s.find("\r\n\r\n") {
                    let cl = s
                        .lines()
                        .find_map(|l| {
                            l.to_ascii_lowercase()
                                .strip_prefix("content-length:")
                                .map(|v| v.trim().parse::<usize>().unwrap())
                        })
                        .unwrap_or(0);
                    if req.len() >= i + 4 + cl {
                        break;
                    }
                }
                if n == 0 {
                    break;
                }
            }
            let resp = format!(
                "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            );
            sock.write_all(resp.as_bytes()).await.unwrap();
            seen.push(String::from_utf8_lossy(&req).to_string());
        }
        seen
    });
    (addr, handle)
}

async fn mock(status: u16, body: &'static str) -> (String, tokio::task::JoinHandle<Vec<String>>) {
    mock_seq(vec![(status, body)]).await
}

fn header<'a>(req: &'a str, name: &str) -> &'a str {
    try_header(req, name).unwrap_or_else(|| panic!("missing header {name}"))
}

fn try_header<'a>(req: &'a str, name: &str) -> Option<&'a str> {
    req.split("\r\n\r\n").next().unwrap().lines().find_map(|l| {
        let (k, v) = l.split_once(':')?;
        (k.eq_ignore_ascii_case(name)).then(|| v.trim())
    })
}

fn body_of(req: &str) -> &str {
    req.split_once("\r\n\r\n").map(|(_, b)| b).unwrap_or("")
}

/// The base URL is http://127.0.0.1:port, so the SDK must sign the https:// form.
fn v2_expected(req: &str, method: &str, http_url: &str) -> String {
    compute_signature_v2(
        method,
        &http_url.replacen("http://", "https://", 1),
        body_of(req).as_bytes(),
        "k",
        "s",
        header(req, "x-timestamp"),
        header(req, "x-rnd-key"),
    )
}

#[tokio::test]
async fn v2_headers_by_default() {
    let (addr, h) = mock(200, r#"{"data":{"id":1}}"#).await;
    let mp = Client::new(Config::new("k", "s").base_url(format!("{addr}/"))).unwrap();
    let res = mp
        .wallets()
        .search_wallet_transactions(42, &[("page", "1"), ("size", "10")])
        .await
        .unwrap();
    assert_eq!(res["data"]["id"], 1);
    let req = h.await.unwrap().remove(0);
    assert!(
        req.starts_with("GET /wallet/v1/wallets/42/wallet-transactions?page=1&size=10 HTTP/1.1")
    );
    assert_eq!(header(&req, "x-api-key"), "k");
    assert_eq!(header(&req, "x-auth-version"), "V2");
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64;
    assert!((header(&req, "x-timestamp").parse::<i64>().unwrap() - now).abs() <= 5);
    let url = format!("{addr}/wallet/v1/wallets/42/wallet-transactions?page=1&size=10");
    assert_eq!(header(&req, "x-signature"), v2_expected(&req, "GET", &url));
}

#[tokio::test]
async fn rnd_key_changes_per_request() {
    let (addr, h) = mock_seq(vec![(200, "{}"), (200, "{}")]).await;
    let mp = Client::new(Config::new("k", "s").base_url(addr)).unwrap();
    mp.payments().retrieve_payment(1).await.unwrap();
    mp.payments().retrieve_payment(1).await.unwrap();
    let reqs = h.await.unwrap();
    assert_ne!(header(&reqs[0], "x-rnd-key"), header(&reqs[1], "x-rnd-key"));
}

#[tokio::test]
async fn v2_body_hash_uses_sent_bytes_and_error() {
    let (addr, h) = mock(400, r#"{"message":"invalid card"}"#).await;
    let mp = Client::new(Config::new("k", "s").base_url(addr.clone())).unwrap();
    let err = mp
        .payments()
        .complete_3ds_payment(&json!({ "paymentId": 123, "note": "ürün" }))
        .await
        .unwrap_err();
    match err {
        Error::Api {
            status, message, ..
        } => {
            assert_eq!(status, 400);
            assert_eq!(message, "invalid card");
        }
        e => panic!("unexpected {e:?}"),
    }
    let req = h.await.unwrap().remove(0);
    assert!(req.starts_with("POST /payment/v1/card-payments/3ds-complete HTTP/1.1"));
    assert_eq!(body_of(&req), r#"{"note":"ürün","paymentId":123}"#);
    assert_eq!(header(&req, "content-type"), "application/json");
    let url = format!("{addr}/payment/v1/card-payments/3ds-complete");
    assert_eq!(header(&req, "x-signature"), v2_expected(&req, "POST", &url));
}

#[tokio::test]
async fn v1_option() {
    let (addr, h) = mock(200, "{}").await;
    let mp = Client::new(
        Config::new("k", "s")
            .base_url(addr.clone())
            .auth_version(AuthVersion::V1),
    )
    .unwrap();
    mp.payments().retrieve_payment(1086).await.unwrap();
    let req = h.await.unwrap().remove(0);
    assert_eq!(header(&req, "x-auth-version"), "V1");
    assert!(try_header(&req, "x-timestamp").is_none());
    let url = format!("{addr}/payment/v1/card-payments/1086").replacen("http://", "https://", 1);
    assert_eq!(
        header(&req, "x-signature"),
        compute_signature(
            &url,
            "k",
            "s",
            header(&req, "x-rnd-key"),
            SignatureEncoding::Hex
        )
    );
}

#[tokio::test]
async fn post_without_body_and_array_response() {
    let (addr, h) = mock_seq(vec![
        (200, "{}"),
        (
            200,
            r#"["CREDIT_CARD","Visa","Garanti BBVA","Bonus","Credit"]"#,
        ),
    ])
    .await;
    let mp = Client::new(Config::new("k", "s").base_url(addr.clone())).unwrap();
    mp.payments().refresh_payguru_payment(77).await.unwrap();
    let bin = mp.installments().check_bin("435508").await.unwrap();
    assert_eq!(bin[2], "Garanti BBVA");
    let reqs = h.await.unwrap();
    assert!(reqs[0].starts_with("POST /payment/v1/payguru/payments/77/refresh HTTP/1.1"));
    assert_eq!(body_of(&reqs[0]), "");
    assert!(try_header(&reqs[0], "content-type").is_none());
    let url = format!("{addr}/payment/v1/payguru/payments/77/refresh");
    assert_eq!(
        header(&reqs[0], "x-signature"),
        v2_expected(&reqs[0], "POST", &url)
    );
    assert!(reqs[1].starts_with("GET /payment/v1/card-payments/bank-name/435508 HTTP/1.1"));
}

#[test]
fn base_url_must_be_https() {
    for bad in ["http://trdev.magicpay.ai", "ftp://x", "trdev.magicpay.ai"] {
        assert!(
            Client::new(Config::new("k", "s").base_url(bad)).is_err(),
            "{bad}"
        );
    }
    for ok in [
        "http://127.0.0.1:1",
        "http://localhost",
        "http://[::1]:8080",
        PRODUCTION_URL,
    ] {
        assert!(
            Client::new(Config::new("k", "s").base_url(ok)).is_ok(),
            "{ok}"
        );
    }
    assert!(Client::new(
        Config::new("k", "s")
            .base_url("http://trdev.magicpay.ai")
            .allow_insecure(true)
    )
    .is_ok());
}

#[test]
fn debug_masks_credentials() {
    let mp = Client::new(Config::new("api-k-123", "secret-456").access_token("jwt-789")).unwrap();
    let out = format!("{:?} {:?}", mp, mp.config());
    for secret in ["api-k-123", "secret-456", "jwt-789"] {
        assert!(!out.contains(secret), "{out}");
    }
    assert!(out.contains("***"));
}

#[tokio::test]
async fn path_params_reject_dot_segments() {
    let mp = Client::new(Config::new("k", "s")).unwrap();
    for bad in ["", ".", ".."] {
        match mp.payments().retrieve_payment(bad).await {
            Err(Error::InvalidPathParam(v)) => assert_eq!(v, bad),
            other => panic!("unexpected {other:?}"),
        }
    }
    let (addr, h) = mock(200, "{}").await;
    let mp = Client::new(Config::new("k", "s").base_url(addr)).unwrap();
    mp.payments().retrieve_payment("a b/..").await.unwrap();
    assert!(h.await.unwrap()[0].starts_with("GET /payment/v1/card-payments/a%20b%2F.. HTTP/1.1"));
}

#[tokio::test]
async fn redirect_is_not_followed_and_token_is_redacted() {
    let (addr, h) = mock(302, LOGIN_OK).await;
    let mp = Client::new(Config::new("k", "s").base_url(addr)).unwrap();
    let err = mp.login("user@example.com", "pw").await.unwrap_err();
    match &err {
        Error::Api {
            status, body, raw, ..
        } => {
            assert_eq!(*status, 302);
            assert!(!raw.contains("jwt-login"));
            assert_eq!(
                body.as_ref().unwrap()["data"]["token"]["accessToken"],
                "***"
            );
        }
        e => panic!("unexpected {e:?}"),
    }
    assert!(!format!("{err} {err:?}").contains("jwt-login"));
    assert!(mp.access_token().is_none());
    assert_eq!(h.await.unwrap().len(), 1);
}

#[tokio::test]
async fn connection_error_hides_the_url() {
    let mp = Client::new(Config::new("k", "s").base_url("http://127.0.0.1:1")).unwrap();
    let err = mp
        .members()
        .search_members(&[("email", "private@example.com")])
        .await
        .unwrap_err();
    assert!(matches!(err, Error::Http(_)));
    let text = format!("{err} {err:?}");
    assert!(!text.contains("private"), "{text}");
}

#[tokio::test]
async fn two_path_params() {
    let (addr, h) = mock(200, "{}").await;
    let mp = Client::new(Config::new("k", "s").base_url(addr)).unwrap();
    mp.pos().change_pos_status(7, "PASSIVE").await.unwrap();
    assert!(h.await.unwrap()[0]
        .starts_with("PUT /merchant/v1/merchant-poses/7/status/PASSIVE HTTP/1.1"));
}

#[tokio::test]
async fn bearer_token_header() {
    let (addr, h) = mock_seq(vec![(200, "{}"), (200, "{}")]).await;
    let mp = Client::new(Config::new("k", "s").base_url(addr).access_token("jwt-1")).unwrap();
    mp.pos().list_pos(&[]).await.unwrap();
    mp.set_access_token(None);
    mp.pos().list_pos(&[]).await.unwrap();
    let reqs = h.await.unwrap();
    assert_eq!(header(&reqs[0], "authorization"), "Bearer jwt-1");
    assert!(try_header(&reqs[1], "authorization").is_none());
}

#[tokio::test]
async fn login_stores_token_then_bearer() {
    let (addr, h) = mock_seq(vec![(200, LOGIN_OK), (200, r#"{"data":[]}"#)]).await;
    let mp = Client::new(Config::new("k", "s").base_url(addr)).unwrap();
    let res = mp.login("user@example.com", "pw").await.unwrap();
    assert_eq!(res["data"]["merchantId"], 7);
    assert_eq!(mp.access_token().as_deref(), Some("jwt-login"));
    mp.pos()
        .list_pos(&[("isActivePos", "PASSIVE")])
        .await
        .unwrap();
    let reqs = h.await.unwrap();
    assert!(reqs[0].starts_with("POST /merchant/v1/authenticate HTTP/1.1"));
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(body_of(&reqs[0])).unwrap(),
        json!({ "email": "user@example.com", "secretWord": "pw" })
    );
    assert!(try_header(&reqs[0], "authorization").is_none());
    assert!(reqs[1].starts_with("GET /merchant/v1/merchant-poses/?isActivePos=PASSIVE HTTP/1.1"));
    assert_eq!(header(&reqs[1], "authorization"), "Bearer jwt-login");
}

#[tokio::test]
async fn login_errors_body_is_an_error() {
    let (addr, _h) = mock(200, LOGIN_BAD).await;
    let mp = Client::new(Config::new("k", "s").base_url(addr)).unwrap();
    let err = mp.login("user@example.com", "wrong").await.unwrap_err();
    assert_eq!(err.error_code().as_deref(), Some("7005"));
    match &err {
        Error::Api {
            status, message, ..
        } => {
            assert_eq!(*status, 200);
            assert!(message.starts_with("7005: "), "{message}");
        }
        e => panic!("unexpected {e:?}"),
    }
    assert!(mp.access_token().is_none());
}

#[tokio::test]
async fn detail_errors_and_empty_errors() {
    let (addr, _h) = mock_seq(vec![
        (
            400,
            r#"{"detail":{"errors":{"errorCode":"2006","errorDescription":"bad signature"}}}"#,
        ),
        (200, r#"{"data":{"id":1},"errors":null}"#),
        (200, r#"{"errors":{}}"#),
    ])
    .await;
    let mp = Client::new(Config::new("k", "s").base_url(addr)).unwrap();
    let err = mp.payments().retrieve_payment(1).await.unwrap_err();
    assert_eq!(err.error_code().as_deref(), Some("2006"));
    assert!(err.to_string().contains("bad signature"));
    assert_eq!(
        mp.payments().retrieve_payment(1).await.unwrap()["data"]["id"],
        1
    );
    assert_eq!(
        mp.payments().retrieve_payment(1).await.unwrap(),
        json!({ "errors": {} })
    );
}
