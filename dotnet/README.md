# MagicPay .NET SDK

.NET 6 / .NET 8 client for the MagicPay API. No external dependencies.

```bash
dotnet add package MagicPay      # or reference src/MagicPay/MagicPay.csproj
```

## Quick start

```csharp
using MagicPay;

using var mp = new MagicPayClient(new MagicPayOptions
{
    ApiKey = "YOUR_API_KEY",
    SecretKey = "YOUR_SECRET_KEY",
    // BaseUrl = MagicPayOptions.ProductionUrl,   // trdev (SandboxUrl) by default
    // AuthVersion = AuthVersion.V1,              // V2 by default
});

// 1) Initialize a 3D Secure payment (anonymous object, Dictionary, JsonNode or your own DTO)
var init = await mp.Payments.Init3dsPaymentAsync(new
{
    price = 100.0, paidPrice = 100.0, installment = 1, currency = "TRY",
    paymentGroup = "PRODUCT", paymentChannel = "Online", clientIp = "192.168.1.1",
    redirectUrl = "https://shop.example.com/magicpay/return",
    callbackUrl = "https://shop.example.com/magicpay/callback",
    bankOrderId = "ORDER-1001",
    card = new { cardHolderName = "Jane Doe", cardNumber = "5406675406675403",
                 expireMonth = "12", expireYear = "2030", cvc = "000" },
    items = new[] { new { name = "Item1", price = 100.0 } },
});

// 2) Complete after the bank redirects back
var done = await mp.Payments.Complete3dsPaymentAsync(new { paymentId = 123 });

// Responses are System.Text.Json.Nodes.JsonNode
var payment = await mp.Payments.RetrievePaymentAsync(123);
string? status = (string?)payment?["data"]?["payment_status"];

// Bearer (merchant-panel) endpoints: log in once, the token is kept on the client
await mp.LoginAsync("panel-user@example.com", "secret-word");
var poses = await mp.Pos.ListPosAsync(new Dictionary<string, object?> { ["isActivePos"] = "ACTIVE" });

// Plugin POS management (V2 only)
var banks = await mp.Plugin.ListBanksAsync();
```

## ASP.NET Core / IHttpClientFactory

```csharp
builder.Services.AddHttpClient("magicpay");
builder.Services.AddSingleton(sp => new MagicPayClient(
    new MagicPayOptions { ApiKey = cfg["MagicPay:ApiKey"]!, SecretKey = cfg["MagicPay:SecretKey"]! },
    sp.GetRequiredService<IHttpClientFactory>().CreateClient("magicpay")));
```

The access token is per client instance: with a singleton client, `LoginAsync` affects all callers.

## Errors

```csharp
try { await mp.LoginAsync("panel-user@example.com", "wrong"); }
catch (MagicPayApiException e) { Console.WriteLine($"{e.StatusCode} {e.ErrorCode} {e.RawBody}"); } // 200 7005
catch (MagicPayConnectionException e) { /* network / timeout */ }
```

`MagicPayApiException` is thrown for HTTP ≥ 300 and for a 2xx body with an `errors` object. The
built-in HttpClient never follows redirects; when you pass your own HttpClient, configure its
handler with `AllowAutoRedirect = false`. A login access token is masked (`***`) in exceptions.
Path parameters `""`, `.` and `..` throw `ArgumentException`. The options object is copied by the
constructor; change the token later with `mp.AccessToken`.

## Options

| Property | Default | |
|---|---|---|
| `BaseUrl` | `SandboxUrl` = `https://trdev.magicpay.ai` (test) | `ProductionUrl` = `https://tr.magicpay.ai` with live keys; must be https |
| `AllowInsecure` | false | allow an `http://` BaseUrl for non-loopback hosts (tests/proxies only) |
| `AuthVersion` | `V2` | `V1` is rejected by `Plugin` endpoints |
| `AccessToken` | null | set by `LoginAsync`; also `mp.AccessToken` |
| `Timeout` | 30 s | |
| `SignatureEncoding` | `Hex` | `Base64` only with V1 |

Every method accepts a `CancellationToken`. Generic signed call:
`mp.SendAsync(HttpMethod.Get, "/path", body, query)`. Signing helpers:
`MagicPayClient.ComputeSignatureV2(...)`, `MagicPayClient.ComputeSignature(...)` (V1).

All methods: [../ENDPOINTS.md](../ENDPOINTS.md). Tests: `dotnet run --project tests/MagicPay.Tests`.
