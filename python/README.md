# MagicPay Python SDK

Zero-dependency Python (3.8+) client for the MagicPay API.

```bash
pip install magicpay        # or: pip install ./python
```

## Quick start

```python
from magicpay import PRODUCTION_URL, MagicPay, MagicPayAPIError

mp = MagicPay(api_key="YOUR_API_KEY", secret_key="YOUR_SECRET_KEY")  # trdev, auth V2
# production: MagicPay(..., base_url=PRODUCTION_URL)

# 1) Initialize a 3D Secure payment
init = mp.payments.init_3ds_payment({
    "price": 100.0,
    "paidPrice": 100.0,
    "installment": 1,
    "currency": "TRY",
    "paymentGroup": "PRODUCT",
    "paymentChannel": "Online",
    "clientIp": "192.168.1.1",
    "redirectUrl": "https://shop.example.com/magicpay/return",
    "callbackUrl": "https://shop.example.com/magicpay/callback",
    "bankOrderId": "ORDER-1001",
    "card": {
        "cardHolderName": "Jane Doe",
        "cardNumber": "5406675406675403",
        "expireMonth": "12",
        "expireYear": "2030",
        "cvc": "000",
    },
    "items": [{"name": "Item1", "price": 100.0}],
})

# 2) After the bank redirects back, complete it
done = mp.payments.complete_3ds_payment({"paymentId": 123})

# Query / refund
payment = mp.payments.retrieve_payment(123)
mp.payments.refund_payment({"paymentId": 123, "conversationId": "r-1", "refundDestinationType": "PROVIDER"})

# Installments
mp.installments.list_checkout_installments(query={"amount": 1250.5, "currency": "TRY"})
mp.installments.retrieve_bin(query={"binNumber": "540667"})

# Bearer (merchant-panel) endpoints: log in once, the token is kept on the client
mp.login("panel-user@example.com", "secret-word")
mp.pos.list_pos(query={"isActivePos": "ACTIVE"})
mp.members.search_members(query={"isBuyer": True, "page": 0, "size": 20})  # None skipped, lists repeated

# Plugin POS management (V2 only)
mp.plugin.list_banks()
```

## Errors

```python
try:
    mp.login("panel-user@example.com", "wrong")
except MagicPayAPIError as e:
    print(e.status, e.error_code, e.body)   # 200 7005 {...}: errors body on HTTP 200
```

`MagicPayAPIError` is raised for HTTP ≥ 300 (redirects are never followed, so the signed headers
cannot be forwarded) and for a 2xx body with an `errors` object. A login access token is masked
(`***`) in error bodies and messages. Path parameters `""`, `.` and `..` raise `ValueError`.
`MagicPayConnectionError` is raised for network problems; both inherit from `MagicPayError`.

## Options

| Argument | Default | |
|---|---|---|
| `base_url` | `SANDBOX_URL` = `https://trdev.magicpay.ai` (test) | `PRODUCTION_URL` = `https://tr.magicpay.ai` with live keys; must be https |
| `allow_insecure` | `False` | allow an `http://` base URL for non-loopback hosts (tests/proxies only; loopback is always allowed) |
| `auth_version` | `"V2"` | or `"V1"` (rejected by `plugin.*`) |
| `access_token` | `None` | set by `login()`; can be set/cleared directly. Shared by every request on this client: `login()` switches concurrent requests to the new token, so use one client per panel user |
| `timeout` | `30` | seconds |
| `signature_encoding` | `"hex"` | `"base64"` only with V1 |
| `transport` | urllib, redirects not followed | callable `(method, url, headers, body, timeout) -> (status, text)` — plug in `requests`/`httpx` or a test double; send `body` unchanged and do not follow redirects |

Undocumented endpoint? `mp.request("GET", "/some/path", body=None, query={...})` is signed the
same way. Signing helpers: `compute_signature_v2(...)`, `compute_signature(...)` (V1).

All methods: [../ENDPOINTS.md](../ENDPOINTS.md). Tests: `python3 -m unittest discover -s tests`.
