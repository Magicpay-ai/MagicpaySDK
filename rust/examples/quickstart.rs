use magicpay::{Client, Config, Error};
use serde_json::json;

#[tokio::main]
async fn main() -> magicpay::Result<()> {
    // trdev and auth V2 by default.
    // production: Config::new(..).base_url(magicpay::PRODUCTION_URL)
    let mp = Client::new(Config::new("YOUR_API_KEY", "YOUR_SECRET_KEY"))?;

    // 1) Initialize 3D Secure (any `Serialize` works: json!, HashMap, your own structs)
    let init = mp
        .payments()
        .init_3ds_payment(&json!({
            "price": 100.0, "paidPrice": 100.0, "installment": 1, "currency": "TRY",
            "paymentGroup": "PRODUCT", "paymentChannel": "Online", "clientIp": "192.168.1.1",
            "redirectUrl": "https://shop.example.com/magicpay/return",
            "callbackUrl": "https://shop.example.com/magicpay/callback",
            "bankOrderId": "ORDER-1001",
            "card": { "cardHolderName": "Jane Doe", "cardNumber": "5406675406675403",
                      "expireMonth": "12", "expireYear": "2030", "cvc": "000" },
            "items": [{ "name": "Item1", "price": 100.0 }]
        }))
        .await?;

    println!("3DS init: {init}");

    // 2) Complete after the bank redirects back
    mp.payments()
        .complete_3ds_payment(&json!({ "paymentId": 123 }))
        .await?;

    // Path params accept anything `Display`; query is a slice of pairs
    let payment = mp.payments().retrieve_payment(123).await?;
    println!("{}", payment["data"]["payment_status"]);

    // Bearer (merchant-panel) endpoints: log in once, the token is kept on the client
    mp.login("panel-user@example.com", "secret-word").await?;
    mp.pos().list_pos(&[("isActivePos", "ACTIVE")]).await?;
    mp.members()
        .search_members(&[("isBuyer", "true"), ("page", "0"), ("size", "20")])
        .await?;

    // Plugin POS management (V2 only)
    mp.plugin().list_banks().await?;

    match mp.payments().retrieve_payment(1).await {
        Err(e @ Error::Api { .. }) => eprintln!("{e} (code {:?})", e.error_code()),
        other => {
            other?;
        }
    }
    Ok(())
}
