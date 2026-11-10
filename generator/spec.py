"""
MagicPay API endpoint specification.

Single source of truth for every SDK in this repository: generator/generate.py turns it into each
language's resource layer and ENDPOINTS.md.

Synced with the MagicPay backend route table (FastAPI app served at https://trdev.magicpay.ai and
https://tr.magicpay.ai) on 2026-11-10. Paths, including trailing slashes, are exactly as the backend
declares them: FastAPI redirects on a slash mismatch and the redirect drops POST bodies.

Each endpoint: (method_name, http_method, path, has_body, has_query, auth, summary)

auth is how the backend authenticates the call:
    "signed" - x-api-key + HMAC signature headers, V1 or V2 accepted (the SDK default is V2)
    "v2"     - signature headers, V2 only (V1 is rejected)
    "bearer" - Authorization: Bearer <access token> from client.login() / users.authenticate()
    "signed_or_bearer" - a valid signature (V1/V2) or a valid Bearer token; either is enough
    "none"   - no authentication
Every SDK sends the signature headers on every request; the Bearer header is added whenever an
access token is set.

Path parameters are written as {snake_case} and become positional arguments (the SDK argument
name may differ from the backend's parameter name; the URL is identical).
"""

AUTH_KINDS = {
    "signed": "Signed (V1/V2)",
    "v2": "Signed (V2 only)",
    "bearer": "Bearer",
    "signed_or_bearer": "Signed or Bearer",
    "none": "None",
}

RESOURCES = {
    "payments": {
        "doc": "Card payments, 3D Secure, deposits and refunds.",
        "endpoints": [
            ("init_3ds_payment", "POST", "/payment/v1/card-payments/3ds-init", True, False, "signed", "Initialize a 3D Secure card payment."),
            ("complete_3ds_payment", "POST", "/payment/v1/card-payments/3ds-complete", True, False, "signed", "Complete a 3D Secure card payment (body: paymentId)."),
            ("retrieve_payment", "GET", "/payment/v1/card-payments/{id}", False, False, "signed", "Retrieve a payment by id."),
            ("retrieve_loyalties", "POST", "/payment/v1/card-loyalties/retrieve", True, False, "signed", "Reward (loyalty points) inquiry for a card."),
            ("refund_payment", "POST", "/payment/v1/refunds", True, False, "signed", "Refund a whole payment."),
            ("retrieve_refund", "GET", "/payment/v1/refunds/{id}", False, False, "bearer", "Retrieve a payment refund by id."),
            ("refund_payment_transaction", "POST", "/payment/v1/refund-transactions", True, False, "signed", "Refund a single payment transaction (item)."),
            ("retrieve_refund_transaction", "GET", "/payment/v1/refund-transactions/{id}", False, False, "bearer", "Retrieve a refund transaction by id."),
            ("create_deposit", "POST", "/payment/v1/deposits", True, False, "signed", "Deposit money into a member wallet with a card."),
            ("init_3ds_deposit", "POST", "/payment/v1/deposits/3ds-init", True, False, "signed", "Initialize a 3D Secure deposit."),
            ("complete_3ds_deposit", "POST", "/payment/v1/deposits/3ds-complete", True, False, "bearer", "Complete a 3D Secure deposit (body: paymentId)."),
            ("retrieve_refundable_amount", "GET", "/payment/v1/wallet-transactions/{wallet_transaction_id}/refundable-amount", False, False, "none", "Get the refundable amount of a wallet transaction."),
            ("refund_wallet_transaction", "POST", "/payment/v1/wallet-transactions/{wallet_transaction_id}/refunds", True, False, "bearer", "Create a refund for a wallet transaction."),
            ("list_wallet_transaction_refunds", "GET", "/payment/v1/wallet-transactions/{wallet_transaction_id}/refunds", False, False, "bearer", "List refunds of a wallet transaction."),
            ("init_3ds_non_card_payment", "POST", "/payment/v1/card-payments/3ds-init/non-cards", True, False, "signed", "Start a hosted (cardless) 3D Secure checkout; the buyer enters the card on the MagicPay page."),
            ("create_mobile_payment", "POST", "/payment/v1/card-payments/mobilepay", True, False, "signed", "Start a mobile (carrier billing) payment, \"Cepten Öde\"; send requestedPosAlias=payguru_mp (or requestedPosId) and phoneNumber or buyerMemberId."),
            ("init_account_payment", "POST", "/payment/v1/account-payments/init", True, False, "signed", "Start an open-banking payment, \"Hesaptan Öde\"; redirect the buyer to the returned redirectUrl."),
            ("init_bank_transfer", "POST", "/payment/v1/bank-transfers/init", True, False, "signed", "Start a bank transfer (Havale/EFT) payment; the buyer must use the returned bankTransfer.reference."),
            ("retrieve_bank_transfer_instructions", "GET", "/payment/v1/bank-transfers/{payment_id}/instructions", False, False, "signed", "Current transfer reference and bank accounts of a bank transfer payment."),
            ("notify_bank_transfer", "POST", "/payment/v1/bank-transfers/{payment_id}/notifications", True, False, "signed", "Record the buyer's \"I have sent the transfer\" notice (body: payerName, payerIban, transferDate, note); not a payment confirmation."),
            ("refresh_payguru_payment", "POST", "/payment/v1/payguru/payments/{payment_id}/refresh", False, False, "signed", "Fetch the current provider status of a Payguru payment (mobile, open banking, bank transfer)."),
            ("refresh_payguru_refund", "POST", "/payment/v1/payguru/refunds/{payment_id}/refresh", False, False, "signed", "Fetch the current provider status of a Payguru refund."),
        ],
    },
    "wallets": {
        "doc": "Member & merchant wallets, wallet transactions and remittances.",
        "endpoints": [
            ("create_member_wallet", "POST", "/wallet/v1/members/{member_id}/wallets", True, False, "bearer", "Create a wallet for a member."),
            ("retrieve_member_wallet", "GET", "/wallet/v1/members/{member_id}/wallet", False, False, "bearer", "Get a member's wallet."),
            ("search_wallet_transactions", "GET", "/wallet/v1/wallets/{member_id}/wallet-transactions", False, True, "bearer", "Search wallet transactions (query: page, size)."),
            ("send_remittance", "POST", "/wallet/v1/remittances/send", True, False, "bearer", "Send remittance from a member wallet."),
            ("receive_remittance", "POST", "/wallet/v1/remittances/receive", True, False, "none", "Receive remittance into a member wallet."),
            ("retrieve_remittance", "POST", "/wallet/v1/remittances/{id}", False, False, "none", "Retrieve a remittance by id."),
            ("retrieve_merchant_wallet", "GET", "/wallet/v1/merchants/me/wallet", False, False, "signed", "Get the merchant's own wallet."),
            ("reset_merchant_wallet_balance", "POST", "/wallet/v1/merchants/me/wallet/reset-balance", True, False, "bearer", "Reset merchant wallet balance (body: walletAmount)."),
        ],
    },
    "users": {
        "doc": "Merchant panel users.",
        "endpoints": [
            ("authenticate", "POST", "/merchant/v1/authenticate", True, False, "none", "Authenticate a user (body: email, secretWord)."),
            ("create_user", "POST", "/merchant/v1/users", True, False, "bearer", "Create a merchant user."),
            ("update_user", "PATCH", "/merchant/v1/users/{user_id}", True, False, "bearer", "Update a merchant user."),
        ],
    },
    "members": {
        "doc": "Members (buyers and sub-merchants).",
        "endpoints": [
            ("create_member", "POST", "/onboarding/v1/members", True, False, "bearer", "Create a member."),
            ("update_member", "PUT", "/onboarding/v1/members/{member_id}", True, False, "bearer", "Update a member."),
            ("retrieve_member", "GET", "/onboarding/v1/members/{member_id}", False, False, "bearer", "Get a member by id."),
            ("search_members", "GET", "/onboarding/v1/members/", False, True, "bearer", "Query members (isBuyer, isSubMerchant, memberType, memberExternalId, memberIds, name, page, size)."),
        ],
    },
    "api_members": {
        "doc": "Members under /api/v1 (signature or Bearer token); the members resource (/onboarding/v1) is Bearer only.",
        "endpoints": [
            ("create_member", "POST", "/api/v1/members/create", True, False, "signed_or_bearer", "Create a buyer or sub-merchant member (camelCase body, same fields as members.create_member)."),
            ("list_members", "GET", "/api/v1/members", False, True, "signed_or_bearer", "List members (query: page (from 1), size, id, memberExternalId, contactName, contactSurname, email)."),
            ("retrieve_member", "GET", "/api/v1/members/{member_id}", False, False, "signed_or_bearer", "Get a member by id."),
            ("update_member", "PUT", "/api/v1/members/{member_id}", True, False, "signed_or_bearer", "Update a member (snake_case body: is_buyer, member_type, settlement_earnings_destination, ...)."),
            ("delete_member", "DELETE", "/api/v1/delete-members/{member_id}", False, True, "signed_or_bearer", "Deactivate a member (sets it PASSIVE); requires query deleting=true."),
        ],
    },
    "installments": {
        "doc": "BIN lookup and installment options.",
        "endpoints": [
            ("retrieve_bin", "GET", "/installment/v1/bins/", False, True, "signed", "Look up card BIN information (query: binNumber)."),
            ("search_installments", "GET", "/installment/v1/installments", False, True, "bearer", "Get installment options for a BIN (query: bin_number)."),
            ("list_checkout_installments", "GET", "/payment/v1/checkout/installments", False, True, "signed", "Merchant-wide lowest customer price per installment (query: amount, currency=TRY|USD|EUR)."),
            ("check_bin", "GET", "/payment/v1/card-payments/bank-name/{bin_number}", False, False, "none", "BIN check: card type, scheme, bank, program and class for the first 6 or 8 digits (returns a JSON array)."),
        ],
    },
    "catalog": {
        "doc": "Menu, products, campaigns, rules, stories and categories.",
        "endpoints": [
            ("get_menu", "GET", "/menu/{merchant_id}", False, False, "bearer", "Get the merchant menu."),
            ("list_products", "GET", "/products", False, True, "bearer", "List products (description, category_id, id, name, page, size)."),
            ("retrieve_product", "GET", "/products/{product_id}", False, False, "bearer", "Get a product by id."),
            ("create_product", "POST", "/add-product", True, False, "bearer", "Create a product."),
            ("update_product", "PUT", "/update-product/{product_id}", True, False, "bearer", "Update a product."),
            ("list_campaigns", "GET", "/campaigns", False, True, "bearer", "List campaigns (description, id, name, page, size)."),
            ("retrieve_campaign", "GET", "/campaigns/{campaign_id}", False, False, "bearer", "Get a campaign by id."),
            ("create_campaign", "POST", "/add-campaign", True, False, "bearer", "Create a campaign."),
            ("update_campaign", "PUT", "/update-campaign/{campaign_id}", True, False, "bearer", "Update a campaign."),
            ("list_rules", "GET", "/rules", False, True, "bearer", "List rules (description, id, name, page, size)."),
            ("retrieve_rule", "GET", "/rules/{rule_id}", False, False, "bearer", "Get a rule by id."),
            ("create_rule", "POST", "/add-rule", True, False, "bearer", "Create a rule."),
            ("update_rule", "PUT", "/update-rule/{rule_id}", True, False, "bearer", "Update a rule."),
            ("list_stories", "GET", "/stories", False, True, "bearer", "List stories (description, id, name, page, size)."),
            ("retrieve_story", "GET", "/stories/{story_id}", False, False, "bearer", "Get a story by id."),
            ("create_story", "POST", "/add-story", True, False, "bearer", "Create a story."),
            ("update_story", "PUT", "/update-story/{story_id}", True, False, "bearer", "Update a story."),
            ("list_categories", "GET", "/categories", False, True, "bearer", "List categories (name, page, size)."),
            ("retrieve_category", "GET", "/categories/{category_id}", False, False, "bearer", "Get a category by id."),
            ("create_category", "POST", "/add-category", True, False, "bearer", "Create a category."),
            ("update_category", "PUT", "/update-category/{category_id}", True, False, "bearer", "Update a category."),
        ],
    },
    "custom_links": {
        "doc": "Custom payment links.",
        "endpoints": [
            ("create_custom_link", "POST", "/customlink/v1/products", True, False, "signed", "Create a custom link."),
            ("update_custom_link", "PUT", "/customlink/v1/products/{link_id}", True, False, "signed", "Update a custom link."),
            ("retrieve_custom_link", "GET", "/customlink/v1/products/{link_id}", False, False, "none", "Get a custom link by id."),
            ("delete_custom_link", "DELETE", "/customlink/v1/products/{link_id}", False, False, "signed", "Delete a custom link."),
            ("list_custom_links", "GET", "/customlink/v1/products", False, True, "signed", "List custom links (id, name, page, size, channel, orderId, conversationId, externalId, ...)."),
        ],
    },
    "magic_links": {
        "doc": "Magic payment links.",
        "endpoints": [
            ("create_magic_link", "POST", "/magiclink/v1/products", True, False, "bearer", "Create a magic link."),
            ("update_magic_link", "PUT", "/magiclink/v1/products/{link_id}", True, False, "bearer", "Update a magic link."),
            ("list_magic_links", "GET", "/magiclink/v1/products", False, True, "bearer", "List magic links (id, name, page, size, channel, orderId, conversationId, externalId, ...)."),
            ("delete_magic_link", "DELETE", "/magiclink/v1/products/{link_id}", False, False, "bearer", "Delete a magic link."),
            ("list_available_installments", "GET", "/magiclink/v1/available-installments", False, True, "signed", "Installment counts (> 1) available from the merchant's active POSes and commissions (query: merchantId, admin only)."),
        ],
    },
    "merchants": {
        "doc": "Merchants.",
        "endpoints": [
            ("create_merchant", "POST", "/merchant/v1/create-merchant", True, False, "bearer", "Create a merchant."),
            ("update_merchant", "PATCH", "/merchant/v1/update-merchant/{merchant_id}", True, False, "bearer", "Update a merchant."),
        ],
    },
    "payment_facilities": {
        "doc": "Payment facilities (PF).",
        "endpoints": [
            ("create_pf", "POST", "/pf", True, False, "signed", "Create a payment facility."),
            ("list_pf", "GET", "/pf", False, True, "signed", "List payment facilities (page, size)."),
            ("update_pf", "PUT", "/pf/{pf_id}", True, False, "signed", "Update a payment facility."),
            ("delete_pf", "DELETE", "/pf/{pf_id}", False, False, "signed", "Delete a payment facility."),
        ],
    },
    "pos": {
        "doc": "Merchant virtual POS definitions and commissions.",
        "endpoints": [
            ("create_pos", "POST", "/merchant/v1/merchant-poses/", True, False, "bearer", "Create a merchant POS."),
            ("update_pos_order", "PUT", "/merchant/v1/merchant-poses/order", True, False, "bearer", "Reorder POSes (body: pos_ids)."),
            ("list_pos", "GET", "/merchant/v1/merchant-poses/", False, True, "bearer", "List merchant POSes (query: isActivePos=ACTIVE|PASSIVE, default ACTIVE)."),
            ("retrieve_pos", "GET", "/merchant/v1/merchant-poses/{pos_id}", False, False, "bearer", "Get a merchant POS by id."),
            ("update_pos", "PUT", "/merchant/v1/merchant-poses/{pos_id}", True, False, "bearer", "Update a merchant POS."),
            ("retrieve_pos_metadata", "GET", "/merchant/v1/pos-metadata/", False, True, "bearer", "Get POS metadata (banks, integrators...)."),
            ("list_commissions", "GET", "/merchant/v1/merchant-poses/{pos_id}/commissions", False, False, "bearer", "Get POS commissions."),
            ("create_commissions", "POST", "/merchant/v1/merchant-poses/{pos_id}/commissions", True, False, "bearer", "Create/update POS commissions."),
            ("change_pos_status", "PUT", "/merchant/v1/merchant-poses/{pos_id}/status/{new_status}", False, False, "bearer", "Change POS status."),
            ("delete_pos", "DELETE", "/merchant/v1/merchant-poses/{pos_id}", False, False, "bearer", "Delete a merchant POS."),
            ("list_pos_ids", "GET", "/merchant/v1/merchant-poses/ids", False, False, "signed", "Ids, names and aliases of the merchant's active POSes."),
        ],
    },
    "submerchants": {
        "doc": "Sub-merchant rewards and transaction approval.",
        "endpoints": [
            ("list_submerchant_rewards", "GET", "/submerchant-rewards", False, True, "signed", "List sub-merchant rewards."),
            ("retrieve_submerchant_reward", "GET", "/submerchant-rewards/{id}", False, False, "signed", "Get a sub-merchant reward by id."),
        ],
    },
    "reports": {
        "doc": "Reports and exports.",
        "endpoints": [
            ("list_reports", "GET", "/merchant/v1/reports", False, True, "bearer", "Get reports (id, reportTypes, reportPeriod, page, size)."),
            ("export_report", "GET", "/export/{transaction_id}", False, False, "bearer", "Export a report by id."),
            ("create_transaction_report", "POST", "/file-reporting/v1/transaction-report-demands", True, True, "bearer", "Create a transaction report demand (query: export=true for Excel)."),
            ("daily_pos_summaries", "GET", "/payment-reporting/v1/pos-reports/daily-summaries", False, True, "bearer", "Daily POS report summaries (page, size, minDate, maxDate)."),
            ("daily_apm_summaries", "GET", "/payment-reporting/v1/apm-reports/daily-summaries", False, True, "bearer", "Daily APM report summaries (page, size, minDate, maxDate)."),
        ],
    },
    "subscriptions": {
        "doc": "Subscriptions.",
        "endpoints": [
            ("list_subscriptions", "GET", "/subscriptions", False, True, "signed", "List subscriptions (id, page, size)."),
            ("retrieve_subscription", "GET", "/subscriptions/{id}", False, False, "bearer", "Get a subscription by id."),
            ("list_subscription_products", "GET", "/subscription-products", False, True, "signed", "List subscription products (id, name, page, size)."),
        ],
    },
    "api_keys": {
        "doc": "API key and permission management.",
        "endpoints": [
            ("list_permissions", "GET", "/permissions", False, False, "bearer", "List assignable API key permissions (auth, preauth, postauth, refund, bin-check, installment-query)."),
            ("create_api_key", "POST", "/api_keys/", True, False, "bearer", "Create an API key (body: name, permissions)."),
            ("retrieve_api_key", "GET", "/api_keys/{api_key_id}", False, False, "signed_or_bearer", "Get an API key by id."),
            ("update_api_key", "PUT", "/api_keys/{api_key_id}", True, False, "signed_or_bearer", "Update an API key."),
            ("delete_api_key", "DELETE", "/api_keys/{api_key_id}", False, False, "signed_or_bearer", "Delete an API key."),
            ("add_permission", "POST", "/api_keys/{api_key_id}/permissions/", False, True, "bearer", "Add a permission to an API key (query: permission_id)."),
            ("delete_permission", "DELETE", "/api_keys/{api_key_id}/permissions/{permission_id}", False, False, "bearer", "Remove a permission from an API key."),
            ("list_api_credentials", "GET", "/api/merchant/v1/api-credentials", False, True, "signed_or_bearer", "List the merchant's API keys (query: page, size, status=ACTIVE|PASSIVE, name)."),
            ("retrieve_api_credential", "GET", "/api/api_keys/{api_key_id}", False, False, "signed_or_bearer", "Get an API key by id (secret_key is not returned)."),
            ("update_api_credential", "PUT", "/api/api_keys/{api_key_id}", True, False, "signed_or_bearer", "Update an API key (body: name, is_active; secret_key is not returned)."),
            ("delete_api_credential", "DELETE", "/api/api_keys/{api_key_id}", False, False, "signed_or_bearer", "Delete an API key."),
        ],
    },
    "plugin": {
        "doc": "Plugin POS management (e-commerce plugins). V2 signature only.",
        "endpoints": [
            ("list_banks", "GET", "/merchant/v1/plugin/banks", False, False, "v2", "Banks the merchant can add, with each bank's credential fields."),
            ("list_poses", "GET", "/merchant/v1/plugin/poses", False, False, "v2", "The merchant's ACTIVE and PASSIVE POSes (secrets masked)."),
            ("create_pos", "POST", "/merchant/v1/plugin/poses", True, False, "v2", "Add a bank POS (body: alias, name, credentials)."),
            ("update_pos_credentials", "PATCH", "/merchant/v1/plugin/poses/{pos_id}/credentials", True, False, "v2", "Update a POS's credentials; blank, null or the mask keeps a stored secret."),
        ],
    },
}
