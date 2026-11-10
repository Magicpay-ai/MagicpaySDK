# End-to-end harness

Runs the same scenarios (`scenarios.json`) through every SDK and compares the exact signed HTTP
requests each one produces. No request reaches MagicPay: each SDK gets a recording transport
(Python `transport`, PHP `http_client`, .NET `HttpMessageHandler`, Rust via a local HTTP proxy).

Credentials are read **only** from the environment — never put keys in files. Recording does not
need real keys; any value works:

```bash
export MAGICPAY_API_KEY=...
export MAGICPAY_SECRET_KEY=...
export MAGICPAY_BASE_URL=https://trdev.magicpay.ai   # optional (default)
```

- `python3 e2e/record.py` — writes `e2e/out/<sdk>.jsonl` for all four SDKs. Needs `php`,
  `composer`, `dotnet` and `cargo` on PATH; with `--docker` (or `MAGICPAY_E2E_DOCKER=1`) the
  PHP/.NET/Rust recorders run in `composer:2`, `mcr.microsoft.com/dotnet/sdk:8.0` and `rust:1.82`
  instead (keys are passed to containers by name, not on the command line).
- `python3 e2e/compare.py` — asserts all SDKs produced the same method, URL, JSON body and `x-*` /
  `Authorization` headers, ignoring the per-request `x-rnd-key`, `x-timestamp` and `x-signature`.
  Those are checked per record instead: the timestamp must be current, rnd keys must be unique, and
  `x-signature` must equal the server's V2 HMAC over the recorded method, `https://` URL, exact body
  bytes, timestamp and rnd key. Set `MAGICPAY_AUTH_VERSION=V1` when recording with V1 clients.

The Rust recorder talks to the `http://` form of the base URL through the proxy, so the check also
proves it signs the `https://` form, as the server does.

Write `query` keys in `scenarios.json` in alphabetical order: the Rust recorder reads scenarios into a
`serde_json` map, which sorts keys, while the other recorders keep file order. Two scenarios
(`encoding.query`, `encoding.path`) compare percent-encoding of spaces, `+`, `/`, `&`, `~` and
non-ASCII characters across the SDKs.
