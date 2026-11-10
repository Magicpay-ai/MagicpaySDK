# MagicPay Rust SDK

Async Rust client (reqwest + rustls) for the MagicPay API.

```toml
[dependencies]
magicpay = "0.1"          # or: magicpay = { path = "rust" }
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
serde_json = "1"
```

## Quick start

```rust
use magicpay::{Client, Config, Error, PRODUCTION_URL};
use serde_json::json;

#[tokio::main]
async fn main() -> magicpay::Result<()> {
    let mp = Client::new(Config::new("YOUR_API_KEY", "YOUR_SECRET_KEY"))?; // trdev, auth V2
    // production: Config::new(..).base_url(PRODUCTION_URL)
    // V1:         Config::new(..).auth_version(magicpay::AuthVersion::V1)

    // 1) Initialize 3D Secure (any `Serialize` works: json!, HashMap, your own structs)
    let init = mp.payments().init_3ds_payment(&json!({
        "price": 100.0, "paidPrice": 100.0, "installment": 1, "currency": "TRY",
        "paymentGroup": "PRODUCT", "paymentChannel": "Online", "clientIp": "192.168.1.1",
        "redirectUrl": "https://shop.example.com/magicpay/return",
        "callbackUrl": "https://shop.example.com/magicpay/callback",
        "bankOrderId": "ORDER-1001",
        "card": { "cardHolderName": "Jane Doe", "cardNumber": "5406675406675403",
                  "expireMonth": "12", "expireYear": "2030", "cvc": "000" },
        "items": [{ "name": "Item1", "price": 100.0 }]
    })).await?;

    // 2) Complete after the bank redirects back
    mp.payments().complete_3ds_payment(&json!({ "paymentId": 123 })).await?;

    // Path params accept anything `Display`; query is a slice of pairs
    let payment = mp.payments().retrieve_payment(123).await?;
    println!("{}", payment["data"]["payment_status"]);

    // Bearer (merchant-panel) endpoints: log in once, the token is kept on the client
    mp.login("panel-user@example.com", "secret-word").await?;
    mp.pos().list_pos(&[("isActivePos", "ACTIVE")]).await?;

    // Plugin POS management (V2 only)
    mp.plugin().list_banks().await?;

    match mp.login("panel-user@example.com", "wrong").await {
        Err(e @ Error::Api { .. }) => eprintln!("{e} (code {:?})", e.error_code()), // 200, 7005
        other => { other?; }
    }
    Ok(())
}
```

`Error::Api` is returned for HTTP ≥ 300 and for a 2xx body with an `errors` object; a login access
token is masked (`***`) in it. `Error::Http` never contains the request URL, `Debug` output of
`Config`/`Client` masks the keys and token, and path parameters `""`, `.`, `..` give
`Error::InvalidPathParam`.

The base URL must be https (`PRODUCTION_URL` with live keys for production; the default is the test
environment). `http://` is accepted only for loopback hosts or with `Config::allow_insecure(true)`.
The built-in HTTP client never follows redirects; for `Client::with_http_client(config, http)` build
`http` with `.redirect(reqwest::redirect::Policy::none())`.

`Client` is cheap to clone; clones share the access token. `Client::access_token()` is
authoritative: `Config::access_token` is only the initial value and does not change after
`login` / `set_access_token`.
Generic signed call: `mp.request(Method::GET, "/path", None, &[])`. Signing helpers:
`compute_signature_v2(...)`, `compute_signature(...)` (V1).

All methods: [../ENDPOINTS.md](../ENDPOINTS.md). Tests: `cargo test`.

Building on the MSRV toolchain without a `Cargo.lock`: newer transitive crates need a newer Cargo,
so create the lockfile with an MSRV-aware resolver first
(`CARGO_RESOLVER_INCOMPATIBLE_RUST_VERSIONS=fallback cargo generate-lockfile` with Cargo ≥ 1.84).
