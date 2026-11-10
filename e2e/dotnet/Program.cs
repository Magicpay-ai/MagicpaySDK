using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using MagicPay;

var apiKey = Environment.GetEnvironmentVariable("MAGICPAY_API_KEY") ?? throw new Exception("MAGICPAY_API_KEY missing");
var secret = Environment.GetEnvironmentVariable("MAGICPAY_SECRET_KEY") ?? throw new Exception("MAGICPAY_SECRET_KEY missing");
var baseUrl = Environment.GetEnvironmentVariable("MAGICPAY_BASE_URL") is { Length: > 0 } b ? b : MagicPayOptions.SandboxUrl;
var e2e = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../.."));
var scenarios = JsonNode.Parse(File.ReadAllText(Path.Combine(e2e, "scenarios.json")))!.AsArray();

var rec = new Rec();
using var mp = new MagicPayClient(new MagicPayOptions { ApiKey = apiKey, SecretKey = secret, BaseUrl = baseUrl }, new HttpClient(rec));
using var outFile = new StreamWriter(Path.Combine(e2e, "out", "dotnet.jsonl"), false, new UTF8Encoding(false));
string Pascal(string s) => string.Concat(s.Split('_').Select(p => char.ToUpper(p[0]) + p[1..]));

foreach (var sc in scenarios)
{
    var resource = mp.GetType().GetProperty(Pascal(sc!["resource"]!.GetValue<string>()))!.GetValue(mp)!;
    var m = resource.GetType().GetMethod(Pascal(sc["method"]!.GetValue<string>()) + "Async")!;
    var callArgs = new List<object?>();
    foreach (var a in sc["args"]!.AsArray()) callArgs.Add(a is JsonValue v && v.TryGetValue<long>(out var l) ? l : a!.GetValue<string>());
    if (sc["body"] != null) callArgs.Add(sc["body"]!.DeepClone());
    var hasQueryParam = m.GetParameters().Any(p => p.Name == "query");
    if (hasQueryParam)
        callArgs.Add(sc["query"] == null ? null : sc["query"]!.AsObject().ToDictionary(kv => kv.Key, kv => (object?)(kv.Value is JsonValue q && q.TryGetValue<long>(out var n) ? n : kv.Value!.GetValue<string>())) as IReadOnlyDictionary<string, object?>);
    callArgs.Add(CancellationToken.None);
    await (Task<JsonNode?>)m.Invoke(resource, callArgs.ToArray())!;
    var r = rec.Last!;
    var headers = r.Headers.ToDictionary(h => h.Key, h => string.Join(",", h.Value));
    if (r.Content != null) foreach (var h in r.Content.Headers) headers[h.Key] = string.Join(",", h.Value);
    outFile.WriteLine(JsonSerializer.Serialize(new { method = r.Method.Method, url = r.RequestUri!.AbsoluteUri, headers, body = rec.LastBody, name = sc["name"]!.GetValue<string>() },
        new JsonSerializerOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }));
}
Console.WriteLine($"dotnet: {scenarios.Count} requests recorded");

sealed class Rec : HttpMessageHandler
{
    public HttpRequestMessage? Last; public string? LastBody;
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        Last = request; LastBody = request.Content == null ? null : await request.Content.ReadAsStringAsync(ct);
        return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
    }
}
