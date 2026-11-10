//! Records the signed requests the Rust SDK produces for e2e/scenarios.json.
//! Routes traffic through a local plain-HTTP proxy (MAGICPAY_RECORD_PROXY) that
//! captures the absolute request. Credentials come from the environment only.
use std::env;
use std::fs;

use magicpay::{Client, Config};
use serde_json::Value;

#[tokio::main]
async fn main() -> magicpay::Result<()> {
    let api_key = env::var("MAGICPAY_API_KEY").expect("MAGICPAY_API_KEY missing");
    let secret = env::var("MAGICPAY_SECRET_KEY").expect("MAGICPAY_SECRET_KEY missing");
    // http:// form of the base URL so the plain-HTTP recording proxy sees the request.
    let base = env::var("MAGICPAY_RUST_BASE_URL")
        .unwrap_or_else(|_| magicpay::SANDBOX_URL.replacen("https://", "http://", 1));
    let proxy = env::var("MAGICPAY_RECORD_PROXY").expect("MAGICPAY_RECORD_PROXY missing");
    let scenarios: Vec<Value> = serde_json::from_str(
        &fs::read_to_string(env::var("SCENARIOS").unwrap()).expect("read scenarios"),
    )?;

    let http = reqwest::Client::builder()
        .proxy(reqwest::Proxy::http(&proxy)?)
        .build()?;
    let mp = Client::with_http_client(
        Config::new(api_key, secret)
            .base_url(base)
            .allow_insecure(true),
        http,
    )?;

    for sc in &scenarios {
        let name = sc["name"].as_str().unwrap();
        let args: Vec<String> = sc["args"]
            .as_array()
            .unwrap()
            .iter()
            .map(|a| {
                a.as_str()
                    .map(String::from)
                    .unwrap_or_else(|| a.to_string())
            })
            .collect();
        let q: Vec<(String, String)> = sc["query"]
            .as_object()
            .map(|o| {
                o.iter()
                    .map(|(k, v)| {
                        (
                            k.clone(),
                            v.as_str()
                                .map(String::from)
                                .unwrap_or_else(|| v.to_string()),
                        )
                    })
                    .collect()
            })
            .unwrap_or_default();
        let query: Vec<(&str, &str)> = q.iter().map(|(k, v)| (k.as_str(), v.as_str())).collect();
        let body = &sc["body"];

        // record.py labels the proxied requests in scenario order.
        println!("{name}");
        let res = match (
            sc["resource"].as_str().unwrap(),
            sc["method"].as_str().unwrap(),
        ) {
            ("members", "search_members") => mp.members().search_members(&query).await,
            ("members", "retrieve_member") => mp.members().retrieve_member(&args[0]).await,
            ("wallets", "retrieve_member_wallet") => {
                mp.wallets().retrieve_member_wallet(&args[0]).await
            }
            ("wallets", "search_wallet_transactions") => {
                mp.wallets()
                    .search_wallet_transactions(&args[0], &query)
                    .await
            }
            ("wallets", "retrieve_merchant_wallet") => {
                mp.wallets().retrieve_merchant_wallet().await
            }
            ("payments", "retrieve_payment") => mp.payments().retrieve_payment(&args[0]).await,
            ("payments", "init_3ds_payment") => mp.payments().init_3ds_payment(body).await,
            ("payments", "init_3ds_non_card_payment") => {
                mp.payments().init_3ds_non_card_payment(body).await
            }
            ("installments", "list_checkout_installments") => {
                mp.installments().list_checkout_installments(&query).await
            }
            ("users", "authenticate") => mp.users().authenticate(body).await,
            ("payments", "create_mobile_payment") => {
                mp.payments().create_mobile_payment(body).await
            }
            ("payments", "init_bank_transfer") => mp.payments().init_bank_transfer(body).await,
            ("payments", "notify_bank_transfer") => {
                mp.payments().notify_bank_transfer(&args[0], body).await
            }
            ("payments", "refresh_payguru_payment") => {
                mp.payments().refresh_payguru_payment(&args[0]).await
            }
            ("installments", "check_bin") => mp.installments().check_bin(&args[0]).await,
            ("pos", "list_pos_ids") => mp.pos().list_pos_ids().await,
            ("api_members", "list_members") => mp.api_members().list_members(&query).await,
            ("api_members", "delete_member") => {
                mp.api_members().delete_member(&args[0], &query).await
            }
            ("api_keys", "list_api_credentials") => {
                mp.api_keys().list_api_credentials(&query).await
            }
            ("plugin", "list_banks") => mp.plugin().list_banks().await,
            ("plugin", "list_poses") => mp.plugin().list_poses().await,
            ("plugin", "create_pos") => mp.plugin().create_pos(body).await,
            ("plugin", "update_pos_credentials") => {
                mp.plugin().update_pos_credentials(&args[0], body).await
            }
            ("installments", "retrieve_bin") => mp.installments().retrieve_bin(&query).await,
            ("installments", "search_installments") => {
                mp.installments().search_installments(&query).await
            }
            ("catalog", "list_products") => mp.catalog().list_products(&query).await,
            ("catalog", "list_categories") => mp.catalog().list_categories(&query).await,
            ("custom_links", "list_custom_links") => {
                mp.custom_links().list_custom_links(&query).await
            }
            ("magic_links", "list_magic_links") => mp.magic_links().list_magic_links(&query).await,
            ("pos", "list_pos") => mp.pos().list_pos(&query).await,
            ("pos", "retrieve_pos_metadata") => mp.pos().retrieve_pos_metadata(&query).await,
            ("submerchants", "list_submerchant_rewards") => {
                mp.submerchants().list_submerchant_rewards(&query).await
            }
            ("reports", "list_reports") => mp.reports().list_reports(&query).await,
            ("reports", "daily_pos_summaries") => mp.reports().daily_pos_summaries(&query).await,
            ("subscriptions", "list_subscriptions") => {
                mp.subscriptions().list_subscriptions(&query).await
            }
            ("payment_facilities", "list_pf") => mp.payment_facilities().list_pf(&query).await,
            (r, m) => panic!("scenario {r}.{m} not mapped in e2e_record.rs"),
        };
        res?;
    }
    Ok(())
}
