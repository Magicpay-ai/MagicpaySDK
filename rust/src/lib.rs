//! # MagicPay Rust SDK
//!
//! ```no_run
//! use magicpay::{Client, Config};
//! use serde_json::json;
//!
//! # async fn run() -> magicpay::Result<()> {
//! let mp = Client::new(Config::new("API_KEY", "SECRET_KEY"))?; // trdev, auth V2
//! let payment = mp.payments().retrieve_payment(1086).await?;
//! let init = mp.payments().init_3ds_payment(&json!({ "price": 100.0, "paidPrice": 100.0 })).await?;
//! mp.login("panel-user@example.com", "secret-word").await?; // Bearer endpoints
//! let poses = mp.pos().list_pos(&[]).await?;
//! # Ok(()) }
//! ```

mod client;
mod error;
mod resources;

pub use client::{
    compute_signature, compute_signature_v2, signing_url, AuthVersion, Client, Config,
    SignatureEncoding, PRODUCTION_URL, SANDBOX_URL,
};
pub use error::{Error, Result};
pub use resources::*;
pub use serde_json::Value;
