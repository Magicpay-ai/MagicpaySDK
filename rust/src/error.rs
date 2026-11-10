use serde_json::{Map, Value};

pub type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// The API answered with an HTTP status >= 300 (redirects are not followed), or with a 2xx body carrying an
    /// `errors` object (e.g. bad login credentials).
    #[error("MagicPay API error {status}: {message}")]
    Api {
        status: u16,
        message: String,
        body: Option<Value>,
        raw: String,
    },
    /// Network / transport failure. The request URL (and its query) is stripped.
    #[error("MagicPay connection error: {0}")]
    Http(reqwest::Error),
    /// JSON (de)serialization failure.
    #[error("MagicPay JSON error: {0}")]
    Json(#[from] serde_json::Error),
    /// Invalid client configuration.
    #[error("MagicPay config error: {0}")]
    Config(String),
    /// A path parameter was empty, `.` or `..`.
    #[error("MagicPay invalid path parameter: {0:?}")]
    InvalidPathParam(String),
}

impl From<reqwest::Error> for Error {
    fn from(e: reqwest::Error) -> Self {
        Error::Http(e.without_url())
    }
}

impl Error {
    /// MagicPay error code from the `errors` object (e.g. `"7005"`), if any.
    pub fn error_code(&self) -> Option<String> {
        let Error::Api {
            body: Some(body), ..
        } = self
        else {
            return None;
        };
        let errors = error_object(body)?;
        let code = errors
            .get("errorCode")
            .or_else(|| errors.get("error_code"))?;
        Some(
            code.as_str()
                .map(String::from)
                .unwrap_or_else(|| code.to_string()),
        )
    }
}

/// Top-level `errors` or (HTTPException style) `detail.errors`; non-empty objects only.
pub(crate) fn error_object(body: &Value) -> Option<&Map<String, Value>> {
    fn non_empty(v: Option<&Value>) -> Option<&Map<String, Value>> {
        v.and_then(Value::as_object).filter(|o| !o.is_empty())
    }
    non_empty(body.get("errors"))
        .or_else(|| non_empty(body.get("detail").and_then(|d| d.get("errors"))))
}
