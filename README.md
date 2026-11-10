# MagicPay SDKs

Official client libraries for the MagicPay API.

| Language | Folder | Package | Runtime deps |
|---|---|---|---|
| Python 3.8+ | [`python/`](python) | `magicpay` (PyPI) | none (stdlib) |
| .NET 6 / 8 | [`dotnet/`](dotnet) | `MagicPay` (NuGet) | none (BCL) |
| Rust 1.70+ | [`rust/`](rust) | `magicpay` (crates.io) | reqwest, serde, sha2, hmac |
| PHP 8.0+ | [`php/`](php) | `magicpay/magicpay-php` (Packagist) | ext-curl, ext-json |

119 endpoints in 17 resources: `payments`, `wallets`, `users`, `members`, `api_members`,
`installments`, `catalog`, `custom_links`, `magic_links`, `merchants`, `payment_facilities`, `pos`,
`submerchants`, `reports`, `subscriptions`, `api_keys`, `plugin`. The list is synced with the
backend route table and the public integration docs; [ENDPOINTS.md](ENDPOINTS.md) maps every endpoint to its method in each SDK
and says how it is authenticated. Backend behaviour worth knowing: [API_NOTES.md](API_NOTES.md).

## Environments

| Environment | Base URL | Constant |
|---|---|---|
| Dev / test (default) | `https://trdev.magicpay.ai` | `SANDBOX_URL` / `MagicPayOptions.SandboxUrl` |
| Production | `https://tr.magicpay.ai` | `PRODUCTION_URL` / `MagicPayOptions.ProductionUrl` |

> **The default base URL is the TEST environment.** For live payments pass `PRODUCTION_URL` and
> your live API key/secret; test keys do not work in production and vice versa.

The base URL must be https. `http://` is accepted only for loopback hosts (127.0.0.1, localhost,
::1) or with the explicit `allow_insecure` / `AllowInsecure` option (meant for tests and recording
proxies). The SDKs never follow redirects, so the signed headers cannot be forwarded to another host
or downgraded to http.

## Authentication

Endpoints use one of five schemes (the **Auth** column in ENDPOINTS.md):

| Auth | Meaning |
|---|---|
| Signed (V1/V2) | API key + signature headers; V1 or V2 accepted |
| Signed (V2 only) | V1 is rejected (`plugin.*`) |
| Bearer | merchant-panel access token: call `login(email, secretWord)` first |
| Signed or Bearer | a valid signature or a Bearer token; either is enough |
| None | public |

Every request carries the signature headers; `Authorization: Bearer` is added once a token is set.

### V2 signature (default)

| Header | Value |
|---|---|
| `x-api-key` | your API key |
| `x-rnd-key` | random string, new per request |
| `x-auth-version` | `V2` |
| `x-timestamp` | unix seconds, as a string |
| `x-signature` | lowercase hex `HMAC-SHA256(secretKey, message)` |

```
message = METHOD + "\n" + fullUrl + "\n" + sha256_hex(body) + "\n" + apiKey + "\n" + timestamp + "\n" + rndKey
```

- `fullUrl` is the URL sent (scheme, host, path, query). The server verifies the `https://` form,
  so the SDKs sign `https://` even when talking to an `http://` base URL.
- `body` is the exact bytes sent; the SDKs serialize JSON once and send the signed bytes. No body
  hashes as `e3b0c442…b855` (sha256 of empty input).
- The server rejects timestamps more than 300 s off and replayed `(key, timestamp, rnd)` triples.

V1 is still available (`auth_version="V1"` / `AuthVersion.V1`):
`x-signature = sha256_hex(fullUrl + apiKey + secretKey + rndKey)`, no timestamp, body not signed.
A base64 encoding option exists for V1 only; the backend compares hex.

**Cross-SDK test vectors** (asserted in every test suite):

```
V2  method = POST   url = https://trdev.magicpay.ai/payment/v1/card-payments/3ds-complete
    body = {"paymentId":123}   apiKey = test-api-key   secret = test-secret-key
    timestamp = 1700000000     rnd = abc123
    sig = ece3b0b7830f3b720257c097c2a6cc4d2dafc81cb937af758231c8fedb16b495

V1  url = https://trdev.magicpay.ai/payment/v1/card-payments/1086?page=1&size=10
    apiKey = test-api-key   secret = test-secret-key   rnd = abc123
    sig = a0a1b034e46f3690306e10ad629a72f0a5c7687068b0be53239d1feb6cf824c5
```

### Login (Bearer endpoints)

`client.login(email, secretWord)` (`LoginAsync` in .NET) calls `POST /merchant/v1/authenticate`
and stores `data.token.accessToken` as the client's access token. Bad credentials come back as
**HTTP 200** with `{"errors": {"errorCode": "7005", ...}}`; the SDKs raise their API error for it.

## Errors

The API error (`MagicPayAPIError` / `ApiException` / `MagicPayApiException` / `Error::Api`) is
raised for HTTP ≥ 300 (a redirect is reported, not followed) **and** for a 2xx body with a
non-empty top-level `errors` object. It carries the status, parsed body, raw text and
`errors.errorCode`; a login access token is masked as `***` in it. Network failures raise a
separate connection error. Path parameters that are empty, `.` or `..` are rejected before the
request is sent.

## Design

- **One spec, four SDKs.** `generator/spec.py` lists every endpoint with its auth kind;
  `generator/generate.py` writes each SDK's resource layer and `ENDPOINTS.md`. The HTTP/signing
  core of each SDK is hand-written and small.
- **Request bodies are plain JSON** (dict / anonymous object / `serde_json::Value` / array) with
  the backend's field names. Responses are returned as parsed JSON exactly as the backend sends
  them: most use a `{"data": ...}` envelope, but not all (e.g. `init_3ds_payment` returns a flat
  object with `htmlContent`, `paymentId`, …; `check_bin` returns an array).
- **Escape hatch**: every client has a generic signed `request(method, path, body, query)`.

## Adding or changing an endpoint

```bash
# 1. edit generator/spec.py (path exactly as the backend declares it, trailing slash included)
python3 generator/generate.py   # also rustfmt's the Rust output (local rustfmt or Docker)
# 2. run the tests
(cd python && python3 -m unittest discover -s tests)
(cd dotnet && dotnet run --project tests/MagicPay.Tests)
(cd rust && cargo test)
(cd php && composer dump-autoload && php tests/run.php)
# 3. cross-SDK request comparison (no network; keys only from the environment)
python3 e2e/record.py [--docker] && python3 e2e/compare.py
```

## Live test against the test environment

`examples/live_test.py` drives the Python SDK against `https://trdev.magicpay.ai` with your test
key pair (taken from the environment only):

```bash
export MAGICPAY_API_KEY=...  MAGICPAY_SECRET_KEY=...   # test keys from the merchant panel
python3 examples/live_test.py smoke      # read-only calls, V2 and V1
python3 examples/live_test.py pay        # 3D payment with the EsnekPOS test card; opens the bank page
python3 examples/live_test.py complete   # after pressing ONAYLA (password is prefilled)
python3 examples/live_test.py status
python3 examples/live_test.py refund     # same day: the bank cancels instead of refunding
```

Press VAZGEÇ on the bank page to see a failed payment (`complete` then answers `FAILURE`, code 1042).
