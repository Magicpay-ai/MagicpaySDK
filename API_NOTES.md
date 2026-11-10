# Backend notes (trdev.magicpay.ai / tr.magicpay.ai)

Behaviour of the MagicPay API the SDKs rely on (checked 2026-11-10). `generator/spec.py` holds the
endpoint list and the auth kind of each endpoint.

## Authentication

| Topic | Behaviour | SDK |
|---|---|---|
| Header names | hyphenated only (`x-api-key`, not `x_api_key`) | hyphenated |
| Auth versions | `x-auth-version` must be `V1` or `V2`; `plugin.*` accepts V2 only | V2 by default, V1 option |
| V2 window | `abs(now - x-timestamp) > 300` s is rejected — keep the host clock in sync | timestamp per request |
| V2 replay | a `(api key, timestamp, rnd key)` triple is accepted once (10 min); a failed nonce store answers 503 | new rnd key per request — do not retry by resending identical headers |
| Signed URL | `str(request.url)` with `http://` replaced by `https://` | signs the https form |
| Signature compare | exact bytes; hex is the only encoding that can match | hex (base64 V1 option kept for compatibility only) |
| Path parameters | the server sees the decoded path, so a percent-encoded path segment would not match the signed URL | path params are ids in practice; avoid non-ASCII/space in them |
| Trailing slashes | FastAPI redirects on a mismatch and the redirect drops POST bodies | spec paths match the backend exactly |
| Signature or Bearer | `api_members.*` and the `api_keys` methods on `/api_keys/{id}`, `/api/api_keys/{id}` and `/api/merchant/v1/api-credentials` accept a valid signature **or** a merchant-panel Bearer token; neither gives 401. No route accepts a bare `x-api-key` any more | signature headers on every request, Bearer added after `login()` |
| Signed routes | `magic_links.list_available_installments` and `GET /payment/v1/task-status` (not wrapped) expect a valid signature; an unknown `x-api-key` is 401 | always signed |
| Signed routes | `installments.retrieve_bin`, `pos.list_pos_ids` and `wallets.retrieve_merchant_wallet` (404 when the merchant has no wallet) require a valid signature | signed |
| Unauthenticated | `installments.check_bin` (`/payment/v1/card-payments/bank-name/{bin}`) needs no auth | headers are sent but ignored |
| `POST /calculate_signature` | deprecated (answers with a `Deprecation: true` header) | the SDKs sign locally and never call it — never send your secret anywhere |

## Login

`POST /merchant/v1/authenticate` (no auth) with `{"email", "secretWord"}`:

- success: HTTP 200 `{"data": {"merchantId", "status": "Success", "token": {"accessToken", "expiresIn"}}}`
- bad credentials: **HTTP 200** `{"errors": {"errorCode": "7005", "errorDescription": "..."}}`
- the backend also sends a verification SMS on every successful login.

`login()` stores the token; Bearer endpoints then work until `expiresIn` seconds pass (log in again).

## Error bodies

Errors come in three shapes; the SDK API error handles all of them and exposes `errorCode`:

| Shape | Example |
|---|---|
| HTTP 4xx/5xx + `{"errors": {"errorCode", "errorDescription"}}` | signature failure `2006` on payment/plugin endpoints |
| HTTP 4xx + `{"detail": "..."}` or `{"detail": {"errors": {...}}}` | `401 Invalid signature`, checkout validation |
| HTTP 200 + `{"errors": {...}}` | login `7005`, some POS endpoints `7404` |

No backend response combines `data` with a non-empty `errors` object, so the SDKs treat any 2xx
body with a non-empty top-level `errors` object as an error.

## Endpoint notes

| Endpoint | Note |
|---|---|
| `payments.init_3ds_payment` | the response is a flat object (`htmlContent`, `paymentId`, …) without a `data` envelope; required: `price`, `paidPrice`, `currency`, `installment`, `paymentGroup`, `paymentChannel`, `clientIp`, `redirectUrl`, `card`, `items` (`name`, `price`); POS choice via optional `requestedPosAlias` / `requestedPosId` |
| `payments.init_3ds_non_card_payment` | same body without `card`; routes to a hosted payment page where the buyer enters the card |
| `payments.refund_payment` | `refundIban` / `refundContactName` are dropped for V1 requests (kept with V2) |
| `payments.refund_payment` / `refund_payment_transaction` | refunds of a `FAILURE`, `OTP_WAITING` or `WAITING_CARD` payment fail early with HTTP 400, `errorCode` `3009` (REFUND_ERROR, "İşlem iade için uygun değildir."), before any provider call (Elekse used to answer `2014`). The body is a top-level `errors` object (`error_code`, `error_message`, `error_message_detail` "Ödeme başarılı olmadığı için iade edilemez.") |
| 3DS redirect (`redirectUrl?status=…`) | the `status` query value is a hint only: Elekse now redirects with `status=error` on a bank-side 3D failure (it sent `success` before). Always confirm the result server-side with `payments.complete_3ds_payment` or `payments.retrieve_payment` before fulfilling an order |
| `payments.complete_3ds_payment` | the answer carries `paymentStatus` and `pending`. `pending: true` (HTTP 400) means the provider has not decided yet: call again later, do not fail the order. A failed payment returns `paymentStatus: "FAILURE"`, `pending: false` and the stored error code (the provider is still re-checked, so a late bank approval turns it into a success). A refunded or cancelled payment never answers success |
| `payments.retrieve_payment` | polling while the shopper is still on the 3D page no longer fails the payment; it reports `WAITING` until the provider gives a final answer |
| `installments.retrieve_bin` / `search_installments` | query parameters (`binNumber`, `bin_number`), not path segments |
| `installments.list_checkout_installments` | `amount` (> 0) and `currency` (`TRY`, `USD`, `EUR`) |
| `pos.list_pos` | `isActivePos` query, default `ACTIVE` |
| `wallets.retrieve_remittance` | `POST` for a read, as the backend declares it |
| `api_keys.add_permission` | `permission_id` is a query parameter |
| `payments.create_mobile_payment` / `init_account_payment` / `init_bank_transfer` | Payguru products: TRY, installment 1, `bankOrderId` (required for account/bank transfer; the docs require it for mobile too); mobile needs `requestedPosAlias: "payguru_mp"` (or `requestedPosId`) and `phoneNumber` or `buyerMemberId`; bank transfer refunds need `additionalParams.refundContactName` / `refundIban` in the init body |
| `payments.notify_bank_transfer` | body `payerName` (required), `payerIban`, `transferDate` (ISO 8601), `note`; records the buyer's notice only, not a payment confirmation |
| `payments.refresh_payguru_payment` / `refresh_payguru_refund` | `POST` without a body (signed over the empty body hash) |
| `installments.check_bin` | returns a bare JSON array: `[cardType, scheme, bank, program, class]` |
| `api_members.delete_member` | requires `?deleting=true`; it sets the member `PASSIVE`, it does not delete the row |
| `plugin.*` | V2 only; `create_pos` body keys `alias`, `name`, `credentials`; `update_pos_credentials` body key `credentials` (blank / null / mask keeps a stored secret); 201 on create, 409 if the POS exists |

Removed from the SDKs because the backend has no such route: `POST /payment/v1/card-payments`
(non-3DS card payment) and `POST /payment/v1/payment-transactions/approve`.

## Two member APIs

| | `members` | `api_members` |
|---|---|---|
| Paths | `/onboarding/v1/members…` | `/api/v1/members…`, `/api/v1/delete-members/{id}` |
| Auth | Bearer (panel user) | signature or Bearer |
| List | `search_members` (`isBuyer`, `isSubMerchant`, `memberType`, `memberIds`, …) | `list_members` (`page` from 1, `size`, `id`, `memberExternalId`, `contactName`, `contactSurname`, `email`) |
| Failures | HTTP status codes | `delete_member` answers **HTTP 200** `{"success": false, "message": …}` for an unknown member or invalid key — check `success`; the SDK does not raise for it |

Both create calls take the same camelCase body; both update calls take a **snake_case** body
(`is_buyer`, `member_type`, `settlement_earnings_destination` = `IBAN` / `WALLET` / `CROSS_BORDER`, …).

## API key management

`api_keys.list_api_credentials` / `retrieve_api_credential` / `update_api_credential` /
`delete_api_credential` (`/api/...`) and `retrieve_api_key` / `update_api_key` /
`delete_api_key` (`/api_keys/{id}`) accept a valid signature or a merchant-panel Bearer token and
only touch the caller's own merchant's keys (another merchant's id answers 404).
`retrieve_api_credential` and `update_api_credential` return `success`, `api_key`, `name`,
`is_active` — no `secret_key`. `retrieve_api_key` / `update_api_key` include the secret only for
panel users with the `api_secret_view` permission (never for signed callers). `list_api_credentials`
returns key ids, names and status to signed callers, without `apiKey` / `secretKey`; panel users with
the `api_secret_view` permission get both. `list_api_keys`,
`create_api_key` and the permission methods stay Bearer only.

## Documented but not implemented

The integration docs pages "Havale ile Ödeme", "Tahsilat Oluşturma", "Tahsilat Sorgulama",
"Tahsilat Doğrulama" and "Webhook Bildirimi" describe `/wallet/v1/money-catch/*`
(`POST orders`, `GET orders/{orderId}`, `POST orders/{orderId}/refresh`,
`POST orders/{orderId}/webhook/retry`). No such routes exist in the prod or dev backend, so the
SDKs do not wrap them. (The "Para Transferi" page documents the implemented
`/payment/v1/bank-transfers/*` endpoints.)

## Integration docs vs backend code

| Docs | Backend |
|---|---|
| "Ortamlar": production link text `https://tr.magicpay.ai` points to `live.magicpay.ai`; the panel links are swapped | API: `https://tr.magicpay.ai`, panel: `https://live.magicpay.ai` |
| 3DS example host `https://api.magicpay.ai`; cURL samples use `http://<API_URL>` | use `https://trdev.magicpay.ai` / `https://tr.magicpay.ai`; https only |
| Authentication page lists `x_api_key`, `x_rnd_key`, … | only hyphenated header names are accepted |
| V2 described as "for Payguru endpoints"; Payguru pages say V2 is required | every signed endpoint accepts V2; Payguru endpoints also accept V1; only `plugin.*` enforces V2 |
| Invalid key/signature → 401 | some endpoints answer 400 with `errorCode` 2006, login answers 200 with `errors` |
| Hesaptan Öde / Cepten Öde / Para Transferi tables and example bodies omit `paymentGroup`, `paymentChannel`, `clientIp` | all three are required fields in the request schema (they may be `null`, but must be present) |
| Payguru item `name` "optional" | `items[].name` is required |
| `api-credentials` list example has no `secret_key` | matches for signed callers; panel users with `api_secret_view` also get `apiKey` / `secretKey` (see above) |
| Member update request/response in snake_case, create in camelCase | matches the code; the inconsistency is in the API itself |
| BIN check example host `api.alanadiniz.com` | placeholder for the base URL |
