#nullable enable
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace MagicPay
{
    /// <summary>Encoding of the x-signature header value (auth V1 only; V2 is always hex).</summary>
    public enum SignatureEncoding { Hex, Base64 }

    /// <summary>Request signing scheme, sent as the x-auth-version header.</summary>
    public enum AuthVersion
    {
        /// <summary>SHA-256(url + apiKey + secretKey + rndKey). Not accepted by V2-only endpoints.</summary>
        V1,
        /// <summary>HMAC-SHA256 over method, url, body hash, apiKey, timestamp and rndKey (default).</summary>
        V2,
    }

    /// <summary>Client configuration.</summary>
    public sealed class MagicPayOptions
    {
        /// <summary>Dev/test environment (default).</summary>
        public const string SandboxUrl = "https://trdev.magicpay.ai";
        /// <summary>Live environment.</summary>
        public const string ProductionUrl = "https://tr.magicpay.ai";

        public string ApiKey { get; set; } = "";
        public string SecretKey { get; set; } = "";
        public string BaseUrl { get; set; } = SandboxUrl;
        public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(30);
        public AuthVersion AuthVersion { get; set; } = AuthVersion.V2;
        public SignatureEncoding SignatureEncoding { get; set; } = SignatureEncoding.Hex;
        /// <summary>Initial merchant-panel JWT for Bearer endpoints (normally set by LoginAsync).</summary>
        public string? AccessToken { get; set; }
        /// <summary>Allow an http:// BaseUrl for non-loopback hosts (tests/proxies only). Loopback http is always allowed.</summary>
        public bool AllowInsecure { get; set; }
    }

    /// <summary>MagicPay API client. Thread-safe; create once and reuse.</summary>
    public sealed partial class MagicPayClient : IDisposable
    {
        public const string Version = "0.1.0";
        internal static readonly HttpMethod Patch = new HttpMethod("PATCH");

        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.Never,
        };

        private readonly MagicPayOptions _options;
        private readonly HttpClient _http;
        private readonly bool _ownsHttp;
        private volatile string? _accessToken;

        public MagicPayClient(string apiKey, string secretKey, string baseUrl = MagicPayOptions.SandboxUrl)
            : this(new MagicPayOptions { ApiKey = apiKey, SecretKey = secretKey, BaseUrl = baseUrl }) { }

        /// <param name="options">Credentials and settings (copied; later changes to the object have no effect).</param>
        /// <param name="httpClient">Optional HttpClient (e.g. from IHttpClientFactory). Not disposed by this client.
        /// Configure its handler with AllowAutoRedirect = false so signed headers are never sent to a redirect target.</param>
        public MagicPayClient(MagicPayOptions options, HttpClient? httpClient = null)
        {
            if (options == null) throw new ArgumentNullException(nameof(options));
            _options = new MagicPayOptions
            {
                ApiKey = options.ApiKey,
                SecretKey = options.SecretKey,
                BaseUrl = (options.BaseUrl ?? "").TrimEnd('/'),
                Timeout = options.Timeout,
                AuthVersion = options.AuthVersion,
                SignatureEncoding = options.SignatureEncoding,
                AllowInsecure = options.AllowInsecure,
            };
            _accessToken = options.AccessToken;
            if (string.IsNullOrEmpty(_options.ApiKey) || string.IsNullOrEmpty(_options.SecretKey))
                throw new ArgumentException("ApiKey and SecretKey are required.");
            if (_options.AuthVersion == AuthVersion.V2 && _options.SignatureEncoding != SignatureEncoding.Hex)
                throw new ArgumentException("SignatureEncoding applies to auth V1 only; V2 is always hex.");
            CheckBaseUrl(_options.BaseUrl, _options.AllowInsecure);
            if (httpClient == null)
            {
                // Never follow redirects: the signed headers must not reach another URL.
                _http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = _options.Timeout };
                _ownsHttp = true;
            }
            else
            {
                _http = httpClient;
            }
            InitResources();
        }

        /// <summary>Set or clear the merchant-panel access token used for Bearer-protected endpoints.</summary>
        public string? AccessToken
        {
            get => _accessToken;
            set => _accessToken = value;
        }

        private static void CheckBaseUrl(string baseUrl, bool allowInsecure)
        {
            if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out var uri) || (uri.Scheme != "https" && uri.Scheme != "http"))
                throw new ArgumentException("Invalid BaseUrl: " + baseUrl);
            if (uri.Scheme == "http" && !allowInsecure && !uri.IsLoopback)
                throw new ArgumentException("BaseUrl must use https (http is allowed only for loopback hosts or with AllowInsecure).");
        }

        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);

        /// <summary>
        /// Log in as a merchant-panel user and keep the access token for Bearer endpoints.
        /// Throws <see cref="MagicPayApiException"/> on bad credentials (the API answers HTTP 200 with an "errors" body).
        /// </summary>
        public async Task<JsonNode?> LoginAsync(string email, string secretWord, CancellationToken cancellationToken = default)
        {
            var body = new JsonObject { ["email"] = email, ["secretWord"] = secretWord };
            var result = await Users.AuthenticateAsync(body, cancellationToken).ConfigureAwait(false);
            if (result is JsonObject root && root["data"] is JsonObject data && data["token"] is JsonObject token
                && token["accessToken"] is JsonValue v && v.TryGetValue<string>(out var accessToken)
                && !string.IsNullOrEmpty(accessToken))
                AccessToken = accessToken;
            return result;
        }

        /// <summary>The URL form the server verifies: a leading http:// becomes https://.</summary>
        public static string SigningUrl(string url) =>
            url.StartsWith("http://", StringComparison.Ordinal) ? "https://" + url.Substring(7) : url;

        /// <summary>Auth V1: SHA-256 over url + apiKey + secretKey + rndKey.</summary>
        public static string ComputeSignature(string url, string apiKey, string secretKey, string rndKey,
            SignatureEncoding encoding = SignatureEncoding.Hex)
        {
            using var sha = SHA256.Create();
            var hash = sha.ComputeHash(Utf8.GetBytes(url + apiKey + secretKey + rndKey));
            if (encoding == SignatureEncoding.Base64) return Convert.ToBase64String(hash);
            return Hex(hash);
        }

        /// <summary>
        /// Auth V2: lowercase hex HMAC-SHA256(secretKey, "METHOD\nurl\nsha256_hex(body)\napiKey\ntimestamp\nrndKey").
        /// <paramref name="body"/> must be exactly the bytes sent (null or empty for no body).
        /// </summary>
        public static string ComputeSignatureV2(string method, string url, byte[]? body, string apiKey, string secretKey,
            string timestamp, string rndKey)
        {
            string bodyHash;
            using (var sha = SHA256.Create()) bodyHash = Hex(sha.ComputeHash(body ?? Array.Empty<byte>()));
            var message = string.Join("\n", method.ToUpperInvariant(), url, bodyHash, apiKey, timestamp, rndKey);
            using var hmac = new HMACSHA256(Utf8.GetBytes(secretKey));
            return Hex(hmac.ComputeHash(Utf8.GetBytes(message)));
        }

        /// <summary>Auth V2 with a string body (UTF-8 encoded).</summary>
        public static string ComputeSignatureV2(string method, string url, string? body, string apiKey, string secretKey,
            string timestamp, string rndKey) =>
            ComputeSignatureV2(method, url, body == null ? null : Utf8.GetBytes(body), apiKey, secretKey, timestamp, rndKey);

        private static string Hex(byte[] bytes)
        {
            var sb = new StringBuilder(bytes.Length * 2);
            foreach (var b in bytes) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        /// <summary>URL-encode one path segment; "", "." and ".." are rejected (they would change the path).</summary>
        internal static string PathParam(object value)
        {
            var text = Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";
            if (text.Length == 0 || text == "." || text == "..")
                throw new ArgumentException($"Invalid path parameter: '{text}'.", nameof(value));
            return Uri.EscapeDataString(text);
        }

        internal static string BuildQuery(IReadOnlyDictionary<string, object?>? query)
        {
            if (query == null || query.Count == 0) return "";
            var parts = new List<string>();
            foreach (var kv in query)
            {
                if (kv.Value == null) continue;
                IEnumerable values = kv.Value is IEnumerable e && !(kv.Value is string) ? e : new[] { kv.Value };
                foreach (var v in values)
                {
                    if (v == null) continue;
                    var s = v is bool b ? (b ? "true" : "false") : Convert.ToString(v, CultureInfo.InvariantCulture);
                    parts.Add(Uri.EscapeDataString(kv.Key) + "=" + Uri.EscapeDataString(s ?? ""));
                }
            }
            return string.Join("&", parts);
        }

        /// <summary>Send a signed request. Use for endpoints not wrapped by the SDK.</summary>
        public async Task<JsonNode?> SendAsync(HttpMethod method, string path, object? body = null,
            IReadOnlyDictionary<string, object?>? query = null, CancellationToken cancellationToken = default)
        {
            var url = _options.BaseUrl + (path.StartsWith("/") ? path : "/" + path);
            var qs = BuildQuery(query);
            if (qs.Length > 0) url += (url.Contains("?") ? "&" : "?") + qs;

            // Serialize once: the signed bytes and the sent bytes must be identical.
            byte[]? payload = null;
            if (body != null)
            {
                var json = body is JsonNode node ? node.ToJsonString() : JsonSerializer.Serialize(body, body.GetType(), JsonOptions);
                payload = Utf8.GetBytes(json);
            }

            var rnd = Hex(RandomNumberGenerator.GetBytes(16));
            using var req = new HttpRequestMessage(method, url);
            // Sign the URL exactly as HttpClient will send it (normalized host, escaping).
            var signUrl = SigningUrl(req.RequestUri!.AbsoluteUri);
            req.Headers.TryAddWithoutValidation("Accept", "application/json");
            req.Headers.TryAddWithoutValidation("User-Agent", "magicpay-dotnet/" + Version);
            req.Headers.TryAddWithoutValidation("x-api-key", _options.ApiKey);
            req.Headers.TryAddWithoutValidation("x-rnd-key", rnd);
            if (_options.AuthVersion == AuthVersion.V2)
            {
                var ts = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString(CultureInfo.InvariantCulture);
                req.Headers.TryAddWithoutValidation("x-auth-version", "V2");
                req.Headers.TryAddWithoutValidation("x-timestamp", ts);
                req.Headers.TryAddWithoutValidation("x-signature",
                    ComputeSignatureV2(method.Method, signUrl, payload, _options.ApiKey, _options.SecretKey, ts, rnd));
            }
            else
            {
                req.Headers.TryAddWithoutValidation("x-auth-version", "V1");
                req.Headers.TryAddWithoutValidation("x-signature",
                    ComputeSignature(signUrl, _options.ApiKey, _options.SecretKey, rnd, _options.SignatureEncoding));
            }

            var accessToken = _accessToken;
            if (!string.IsNullOrEmpty(accessToken))
                req.Headers.TryAddWithoutValidation("Authorization", "Bearer " + accessToken);

            if (payload != null)
            {
                req.Content = new ByteArrayContent(payload);
                req.Content.Headers.TryAddWithoutValidation("Content-Type", "application/json; charset=utf-8");
            }

            HttpResponseMessage resp;
            try
            {
                resp = await _http.SendAsync(req, cancellationToken).ConfigureAwait(false);
            }
            catch (HttpRequestException ex)
            {
                throw new MagicPayConnectionException(ex.Message, ex);
            }
            catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
            {
                throw new MagicPayConnectionException("Request timed out.", ex);
            }

            using (resp)
            {
                var text = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
                JsonNode? parsed = null;
                if (!string.IsNullOrWhiteSpace(text))
                {
                    try { parsed = JsonNode.Parse(text); }
                    catch (JsonException) { parsed = JsonValue.Create(text); }
                }
                var status = (int)resp.StatusCode;
                // The API also reports some failures (e.g. bad login) as HTTP 200 + {"errors": {...}}.
                // 3xx is an error too: redirects are not followed.
                if (status >= 300 || (parsed is JsonObject o && o["errors"] is JsonObject errors && errors.Count > 0))
                {
                    // Never put a login access token into an exception.
                    if (parsed is JsonObject root && root["data"] is JsonObject data && data["token"] is JsonObject token
                        && token["accessToken"] is JsonValue tv && tv.TryGetValue<string>(out var jwt) && jwt.Length > 0)
                    {
                        token["accessToken"] = "***";
                        text = text.Replace(jwt, "***");
                    }
                    throw new MagicPayApiException(status, parsed, text);
                }
                return parsed;
            }
        }

        public void Dispose()
        {
            if (_ownsHttp) _http.Dispose();
        }
    }

    public class MagicPayException : Exception
    {
        public MagicPayException(string message, Exception? inner = null) : base(message, inner) { }
    }

    public sealed class MagicPayConnectionException : MagicPayException
    {
        public MagicPayConnectionException(string message, Exception? inner = null) : base(message, inner) { }
    }

    /// <summary>The API answered with an HTTP status &gt;= 300 (redirects are not followed), or with a 2xx body carrying an "errors" object.</summary>
    public sealed class MagicPayApiException : MagicPayException
    {
        public int StatusCode { get; }
        public JsonNode? Body { get; }
        public string RawBody { get; }
        /// <summary>MagicPay error code from the "errors" object (e.g. "7005"), if any.</summary>
        public string? ErrorCode { get; }

        public MagicPayApiException(int statusCode, JsonNode? body, string rawBody)
            : base($"MagicPay API error {statusCode}: {ExtractMessage(body) ?? rawBody}")
        {
            StatusCode = statusCode;
            Body = body;
            RawBody = rawBody;
            ErrorCode = Str(ErrorObject(body), "errorCode", "error_code");
        }

        /// <summary>Top-level "errors" or (HTTPException style) "detail.errors"; non-empty objects only.</summary>
        private static JsonObject? ErrorObject(JsonNode? body)
        {
            if (!(body is JsonObject o)) return null;
            if (o["errors"] is JsonObject e && e.Count > 0) return e;
            if (o["detail"] is JsonObject d && d["errors"] is JsonObject de && de.Count > 0) return de;
            return null;
        }

        private static string? Str(JsonObject? o, params string[] keys)
        {
            if (o == null) return null;
            foreach (var k in keys)
                if (o.TryGetPropertyValue(k, out var v) && v != null)
                    return v is JsonValue jv && jv.TryGetValue<string>(out var s) ? s : v.ToJsonString();
            return null;
        }

        private static string? ExtractMessage(JsonNode? body)
        {
            if (!(body is JsonObject o)) return null;
            var msg = Str(o, "message", "error");
            if (msg != null) return msg;
            if (o["detail"] is JsonValue) return Str(o, "detail");
            var errors = ErrorObject(body);
            if (errors != null)
            {
                var code = Str(errors, "errorCode", "error_code");
                var desc = Str(errors, "errorDescription", "error_description");
                if (code != null && desc != null) return code + ": " + desc;
                if (desc != null || code != null) return desc ?? code;
            }
            return Str(o, "detail");
        }
    }
}
