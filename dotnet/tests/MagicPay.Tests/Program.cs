// Dependency-free test runner (no xUnit download needed): `dotnet run --project tests/MagicPay.Tests`
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using MagicPay;

// Shared cross-SDK test vectors (see ../../../README.md)
const string V1Url = "https://trdev.magicpay.ai/payment/v1/card-payments/1086?page=1&size=10";
const string V1Sig = "a0a1b034e46f3690306e10ad629a72f0a5c7687068b0be53239d1feb6cf824c5";
const string V2Url = "https://trdev.magicpay.ai/payment/v1/card-payments/3ds-complete";
const string V2Body = "{\"paymentId\":123}";
const string V2Sig = "ece3b0b7830f3b720257c097c2a6cc4d2dafc81cb937af758231c8fedb16b495";
const string LoginOk = "{\"data\":{\"merchantId\":7,\"status\":\"Success\",\"token\":{\"accessToken\":\"jwt-login\",\"expiresIn\":3600}}}";
const string LoginBad = "{\"errors\":{\"errorCode\":\"7005\",\"errorDescription\":\"E-posta adresi ya da şifre hatalı\"}}";

var failures = 0;
async Task Test(string name, Func<Task> body)
{
    try { await body(); Console.WriteLine("ok   " + name); }
    catch (Exception e) { failures++; Console.WriteLine("FAIL " + name + ": " + e.Message); }
}
void Eq(object? expected, object? actual)
{
    if (!Equals(expected, actual)) throw new Exception($"expected <{expected}> got <{actual}>");
}
string Hdr(HttpRequestMessage r, string n) => string.Join(",", r.Headers.GetValues(n));
string V2(HttpRequestMessage r, string url, byte[]? body) =>
    MagicPayClient.ComputeSignatureV2(r.Method.Method, url, body, "k", "s", Hdr(r, "x-timestamp"), Hdr(r, "x-rnd-key"));
MagicPayClient Client(RecordingHandler h, Action<MagicPayOptions>? configure = null)
{
    var o = new MagicPayOptions { ApiKey = "k", SecretKey = "s" };
    configure?.Invoke(o);
    return new MagicPayClient(o, new HttpClient(h));
}

await Test("environment URLs", () =>
{
    Eq("https://trdev.magicpay.ai", MagicPayOptions.SandboxUrl);
    Eq("https://tr.magicpay.ai", MagicPayOptions.ProductionUrl);
    Eq(MagicPayOptions.SandboxUrl, new MagicPayOptions().BaseUrl);
    return Task.CompletedTask;
});

await Test("V1 signature vector", () =>
{
    Eq(V1Sig, MagicPayClient.ComputeSignature(V1Url, "test-api-key", "test-secret-key", "abc123"));
    return Task.CompletedTask;
});

await Test("V2 signature vector", () =>
{
    Eq(V2Sig, MagicPayClient.ComputeSignatureV2("POST", V2Url, V2Body, "test-api-key", "test-secret-key", "1700000000", "abc123"));
    Eq(V2Sig, MagicPayClient.ComputeSignatureV2("post", V2Url, Encoding.UTF8.GetBytes(V2Body), "test-api-key", "test-secret-key", "1700000000", "abc123"));
    Eq(MagicPayClient.ComputeSignatureV2("GET", V1Url, (byte[]?)null, "k", "s", "1", "r"),
        MagicPayClient.ComputeSignatureV2("GET", V1Url, "", "k", "s", "1", "r"));
    return Task.CompletedTask;
});

await Test("V2 headers by default (GET, path + query)", async () =>
{
    var h = new RecordingHandler((200, "{\"data\":{\"id\":1}}"));
    using var mp = Client(h);
    var res = await mp.Wallets.SearchWalletTransactionsAsync(42,
        new Dictionary<string, object?> { ["page"] = 1, ["size"] = 10, ["skip"] = null });
    Eq(1, (int)res!["data"]!["id"]!);
    var r = h.Last!;
    Eq("GET", r.Method.Method);
    var url = r.RequestUri!.AbsoluteUri;
    Eq("https://trdev.magicpay.ai/wallet/v1/wallets/42/wallet-transactions?page=1&size=10", url);
    Eq(null, h.LastBody);
    Eq("k", Hdr(r, "x-api-key"));
    Eq("V2", Hdr(r, "x-auth-version"));
    Eq(true, Math.Abs(long.Parse(Hdr(r, "x-timestamp")) - DateTimeOffset.UtcNow.ToUnixTimeSeconds()) <= 5);
    Eq(V2(r, url, null), Hdr(r, "x-signature"));
});

await Test("rnd key changes per request", async () =>
{
    var h = new RecordingHandler((200, "{}"));
    using var mp = Client(h);
    await mp.Payments.RetrievePaymentAsync(1);
    var first = Hdr(h.Last!, "x-rnd-key");
    await mp.Payments.RetrievePaymentAsync(1);
    Eq(false, first == Hdr(h.Last!, "x-rnd-key"));
});

await Test("V2 body hash uses the sent bytes", async () =>
{
    var h = new RecordingHandler((200, "{}"));
    using var mp = Client(h, o => o.BaseUrl = "https://api.example.com/");
    await mp.Payments.Complete3dsPaymentAsync(new { paymentId = 123, note = "ürün" });
    var r = h.Last!;
    Eq("POST", r.Method.Method);
    Eq("https://api.example.com/payment/v1/card-payments/3ds-complete", r.RequestUri!.AbsoluteUri);
    Eq("{\"paymentId\":123,\"note\":\"\\u00FCr\\u00FCn\"}", Encoding.UTF8.GetString(h.LastBytes!));
    Eq("application/json; charset=utf-8", h.LastContentType);
    Eq(V2(r, r.RequestUri.AbsoluteUri, h.LastBytes), Hdr(r, "x-signature"));
});

await Test("http base URL is signed as https", async () =>
{
    var h = new RecordingHandler((200, "{}"));
    using var mp = Client(h, o => o.BaseUrl = "http://127.0.0.1:8080");
    await mp.Payments.RetrievePaymentAsync(5);
    var r = h.Last!;
    Eq("http://127.0.0.1:8080/payment/v1/card-payments/5", r.RequestUri!.AbsoluteUri);
    Eq(V2(r, "https://127.0.0.1:8080/payment/v1/card-payments/5", null), Hdr(r, "x-signature"));
});

await Test("V1 option", async () =>
{
    var h = new RecordingHandler((200, "{}"));
    using var mp = Client(h, o => o.AuthVersion = AuthVersion.V1);
    await mp.Payments.RetrievePaymentAsync(1086);
    var r = h.Last!;
    Eq("V1", Hdr(r, "x-auth-version"));
    Eq(false, r.Headers.Contains("x-timestamp"));
    Eq(MagicPayClient.ComputeSignature(r.RequestUri!.AbsoluteUri, "k", "s", Hdr(r, "x-rnd-key")), Hdr(r, "x-signature"));
    try
    {
        using var bad = new MagicPayClient(new MagicPayOptions { ApiKey = "k", SecretKey = "s", SignatureEncoding = SignatureEncoding.Base64 });
        throw new Exception("base64 accepted with V2");
    }
    catch (ArgumentException) { }
    using var ok = new MagicPayClient(new MagicPayOptions { ApiKey = "k", SecretKey = "s", AuthVersion = AuthVersion.V1, SignatureEncoding = SignatureEncoding.Base64 });
});

await Test("POST without body; array response", async () =>
{
    var h = new RecordingHandler((200, "{}"), (200, "[\"CREDIT_CARD\",\"Visa\",\"Garanti BBVA\",\"Bonus\",\"Credit\"]"));
    using var mp = Client(h);
    await mp.Payments.RefreshPayguruPaymentAsync(77);
    var r = h.Requests[0];
    Eq("POST", r.Method.Method);
    Eq("https://trdev.magicpay.ai/payment/v1/payguru/payments/77/refresh", r.RequestUri!.AbsoluteUri);
    Eq(null, h.Bodies[0]);
    Eq(V2(r, r.RequestUri.AbsoluteUri, null), Hdr(r, "x-signature"));
    var bin = await mp.Installments.CheckBinAsync("435508");
    Eq("Garanti BBVA", (string?)bin![2]);
    Eq("/payment/v1/card-payments/bank-name/435508", h.Last!.RequestUri!.AbsolutePath);
});

await Test("BaseUrl must be https", () =>
{
    foreach (var bad in new[] { "http://trdev.magicpay.ai", "ftp://x", "trdev.magicpay.ai" })
    {
        try { using var c = new MagicPayClient(new MagicPayOptions { ApiKey = "k", SecretKey = "s", BaseUrl = bad }); throw new Exception("accepted " + bad); }
        catch (ArgumentException) { }
    }
    foreach (var ok in new[] { "http://127.0.0.1:1", "http://localhost", "http://[::1]:8080", MagicPayOptions.ProductionUrl })
    { using var c = new MagicPayClient(new MagicPayOptions { ApiKey = "k", SecretKey = "s", BaseUrl = ok }); }
    using var insecure = new MagicPayClient(new MagicPayOptions { ApiKey = "k", SecretKey = "s", BaseUrl = "http://trdev.magicpay.ai", AllowInsecure = true });
    return Task.CompletedTask;
});

await Test("options are copied", async () =>
{
    var h = new RecordingHandler((200, "{}"));
    var o = new MagicPayOptions { ApiKey = "k", SecretKey = "s", BaseUrl = "https://api.example.com/", AccessToken = "t1" };
    using var mp = new MagicPayClient(o, new HttpClient(h));
    Eq("https://api.example.com/", o.BaseUrl);
    o.ApiKey = "changed"; o.AccessToken = "changed";
    await mp.Payments.RetrievePaymentAsync(1);
    Eq("k", Hdr(h.Last!, "x-api-key"));
    Eq("Bearer t1", Hdr(h.Last!, "Authorization"));
    Eq(32, Hdr(h.Last!, "x-rnd-key").Length);
});

await Test("path params reject dot segments", async () =>
{
    var h = new RecordingHandler((200, "{}"));
    using var mp = Client(h);
    foreach (var bad in new[] { "", ".", ".." })
    {
        try { await mp.Payments.RetrievePaymentAsync(bad); throw new Exception("accepted '" + bad + "'"); }
        catch (ArgumentException) { }
    }
    await mp.Payments.RetrievePaymentAsync("a b/..");
    Eq("https://trdev.magicpay.ai/payment/v1/card-payments/a%20b%2F..", h.Last!.RequestUri!.AbsoluteUri);
});

await Test("3xx is an error; login token redacted", async () =>
{
    var h = new RecordingHandler((302, LoginOk));
    using var mp = Client(h);
    try { await mp.LoginAsync("user@example.com", "pw"); throw new Exception("no exception"); }
    catch (MagicPayApiException e)
    {
        Eq(302, e.StatusCode);
        Eq(false, (e.Message + e.RawBody + e.Body!.ToJsonString()).Contains("jwt-login"));
        Eq("***", (string?)e.Body!["data"]!["token"]!["accessToken"]);
    }
    Eq(null, mp.AccessToken);
});

await Test("default HttpClient does not follow redirects", async () =>
{
    var listener = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
    listener.Start();
    var port = ((IPEndPoint)listener.LocalEndpoint).Port;
    var hits = 0;
    var server = Task.Run(async () =>
    {
        while (true)
        {
            using var c = await listener.AcceptTcpClientAsync();
            hits++;
            var stream = c.GetStream();
            var buf = new byte[8192];
            await stream.ReadAsync(buf);
            var resp = Encoding.ASCII.GetBytes("HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:" + port + "/elsewhere\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
            await stream.WriteAsync(resp);
        }
    });
    try
    {
        using var mp = new MagicPayClient(new MagicPayOptions { ApiKey = "k", SecretKey = "s", BaseUrl = "http://127.0.0.1:" + port });
        try { await mp.Payments.RetrievePaymentAsync(1); throw new Exception("no exception"); }
        catch (MagicPayApiException e) { Eq(302, e.StatusCode); }
        Eq(1, hits);
    }
    finally { listener.Stop(); }
});

await Test("PUT with two path params", async () =>
{
    var h = new RecordingHandler((200, "{}"));
    using var mp = Client(h);
    await mp.Pos.ChangePosStatusAsync(7, "PASSIVE");
    Eq("PUT", h.Last!.Method.Method);
    Eq("/merchant/v1/merchant-poses/7/status/PASSIVE", h.Last.RequestUri!.AbsolutePath);
});

await Test("Bearer token", async () =>
{
    var h = new RecordingHandler((200, "{}"));
    using var mp = Client(h, o => o.AccessToken = "jwt-1");
    await mp.Pos.ListPosAsync();
    Eq("Bearer jwt-1", Hdr(h.Last!, "Authorization"));
    mp.AccessToken = null;
    await mp.Pos.ListPosAsync();
    Eq(false, h.Last!.Headers.Contains("Authorization"));
});

await Test("login stores the token; Bearer added afterwards", async () =>
{
    var h = new RecordingHandler((200, LoginOk), (200, "{\"data\":[]}"));
    using var mp = Client(h);
    var res = await mp.LoginAsync("user@example.com", "pw");
    Eq(7, (int)res!["data"]!["merchantId"]!);
    Eq("jwt-login", mp.AccessToken);
    var login = h.Requests[0];
    Eq("POST", login.Method.Method);
    Eq("https://trdev.magicpay.ai/merchant/v1/authenticate", login.RequestUri!.AbsoluteUri);
    Eq("{\"email\":\"user@example.com\",\"secretWord\":\"pw\"}", h.Bodies[0]);
    Eq(false, login.Headers.Contains("Authorization"));
    await mp.Pos.ListPosAsync(new Dictionary<string, object?> { ["isActivePos"] = "PASSIVE" });
    Eq("Bearer jwt-login", Hdr(h.Last!, "Authorization"));
    Eq("https://trdev.magicpay.ai/merchant/v1/merchant-poses/?isActivePos=PASSIVE", h.Last!.RequestUri!.AbsoluteUri);
});

await Test("login errors body raises", async () =>
{
    var h = new RecordingHandler((200, LoginBad));
    using var mp = Client(h);
    try { await mp.LoginAsync("user@example.com", "wrong"); throw new Exception("no exception"); }
    catch (MagicPayApiException e)
    {
        Eq(200, e.StatusCode);
        Eq("7005", e.ErrorCode);
        if (!e.Message.Contains("7005")) throw new Exception("message: " + e.Message);
    }
    Eq(null, mp.AccessToken);
});

await Test("API error", async () =>
{
    var h = new RecordingHandler((400, "{\"message\":\"invalid card\"}"));
    using var mp = Client(h);
    try { await mp.Payments.RetrievePaymentAsync(1); throw new Exception("no exception"); }
    catch (MagicPayApiException e) { Eq(400, e.StatusCode); if (!e.Message.Contains("invalid card")) throw; }
});

await Test("API error with detail.errors", async () =>
{
    var h = new RecordingHandler((400, "{\"detail\":{\"errors\":{\"errorCode\":\"2006\",\"errorDescription\":\"bad signature\"}}}"));
    using var mp = Client(h);
    try { await mp.Payments.RetrievePaymentAsync(1); throw new Exception("no exception"); }
    catch (MagicPayApiException e) { Eq("2006", e.ErrorCode); if (!e.Message.Contains("bad signature")) throw new Exception(e.Message); }
});

await Test("null / empty errors is not an error", async () =>
{
    var h = new RecordingHandler((200, "{\"data\":{\"id\":1},\"errors\":null}"), (200, "{\"errors\":{}}"));
    using var mp = Client(h);
    Eq(1, (int)(await mp.Payments.RetrievePaymentAsync(1))!["data"]!["id"]!);
    Eq("{\"errors\":{}}", (await mp.Payments.RetrievePaymentAsync(1))!.ToJsonString());
});

Console.WriteLine(failures == 0 ? "ALL PASSED" : $"{failures} FAILED");
return failures == 0 ? 0 : 1;

sealed class RecordingHandler : HttpMessageHandler
{
    private readonly (int Status, string Body)[] _responses;
    public readonly List<HttpRequestMessage> Requests = new();
    public readonly List<string?> Bodies = new();
    public HttpRequestMessage? Last; public string? LastBody; public byte[]? LastBytes; public string? LastContentType;
    public RecordingHandler(params (int, string)[] responses) { _responses = responses; }
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        Last = request;
        LastBytes = request.Content == null ? null : await request.Content.ReadAsByteArrayAsync(ct);
        LastBody = LastBytes == null ? null : Encoding.UTF8.GetString(LastBytes);
        LastContentType = request.Content?.Headers.ContentType?.ToString();
        Requests.Add(request); Bodies.Add(LastBody);
        var (status, body) = _responses[Math.Min(Requests.Count, _responses.Length) - 1];
        return new HttpResponseMessage((HttpStatusCode)status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
    }
}
