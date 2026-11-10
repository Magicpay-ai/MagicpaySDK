<?php

declare(strict_types=1);

namespace MagicPay;

use MagicPay\Exception\ApiException;
use MagicPay\Http\CurlHttpClient;
use MagicPay\Http\HttpClientInterface;

/**
 * MagicPay API client.
 *
 *   $mp = new MagicPayClient('API_KEY', 'SECRET_KEY');          // trdev, auth V2
 *   $payment = $mp->payments->retrievePayment(1086);
 *   $mp->login('panel-user@example.com', 'secret-word');        // Bearer endpoints
 *   $poses = $mp->pos->listPos();
 */
final class MagicPayClient
{
    use ResourcesTrait;

    public const VERSION = '0.1.0';
    /** Dev/test environment (default). */
    public const SANDBOX_URL = 'https://trdev.magicpay.ai';
    /** Live environment. */
    public const PRODUCTION_URL = 'https://tr.magicpay.ai';
    public const AUTH_V1 = 'V1';
    public const AUTH_V2 = 'V2';

    private string $apiKey;
    private string $secretKey;
    private string $baseUrl;
    private string $signatureEncoding;
    private string $authVersion;
    private ?string $accessToken;
    private HttpClientInterface $http;

    /**
     * @param array{base_url?: string, allow_insecure?: bool, timeout?: int, auth_version?: 'V1'|'V2', signature_encoding?: 'hex'|'base64', http_client?: HttpClientInterface, access_token?: string} $options
     */
    public function __construct(
        #[\SensitiveParameter] string $apiKey,
        #[\SensitiveParameter] string $secretKey,
        #[\SensitiveParameter] array $options = []
    ) {
        if ($apiKey === '' || $secretKey === '') {
            throw new \InvalidArgumentException('apiKey and secretKey are required');
        }
        $this->apiKey = $apiKey;
        $this->secretKey = $secretKey;
        $baseUrl = $options['base_url'] ?? self::SANDBOX_URL;
        self::checkBaseUrl($baseUrl, (bool) ($options['allow_insecure'] ?? false));
        $this->baseUrl = rtrim($baseUrl, '/');
        $this->signatureEncoding = $options['signature_encoding'] ?? 'hex';
        if (!in_array($this->signatureEncoding, ['hex', 'base64'], true)) {
            throw new \InvalidArgumentException("signature_encoding must be 'hex' or 'base64'");
        }
        $this->authVersion = $options['auth_version'] ?? self::AUTH_V2;
        if (!in_array($this->authVersion, [self::AUTH_V1, self::AUTH_V2], true)) {
            throw new \InvalidArgumentException("auth_version must be 'V1' or 'V2'");
        }
        if ($this->authVersion === self::AUTH_V2 && $this->signatureEncoding !== 'hex') {
            throw new \InvalidArgumentException('signature_encoding applies to auth V1 only; V2 is always hex');
        }
        $this->accessToken = $options['access_token'] ?? null;
        $this->http = $options['http_client'] ?? new CurlHttpClient((int) ($options['timeout'] ?? 30));
        $this->initResources();
    }

    /** https is required; http only for loopback hosts or with allow_insecure. */
    private static function checkBaseUrl(string $baseUrl, bool $allowInsecure): void
    {
        $scheme = strtolower((string) parse_url($baseUrl, PHP_URL_SCHEME));
        $host = strtolower(trim((string) parse_url($baseUrl, PHP_URL_HOST), '[]'));
        if ($host === '' || !in_array($scheme, ['https', 'http'], true)) {
            throw new \InvalidArgumentException('invalid base_url: ' . $baseUrl);
        }
        $loopback = $host === 'localhost' || $host === '::1' || strncmp($host, '127.', 4) === 0;
        if ($scheme === 'http' && !$allowInsecure && !$loopback) {
            throw new \InvalidArgumentException('base_url must use https (http is allowed only for loopback hosts or with allow_insecure)');
        }
    }

    /** array_is_list() with a fallback for PHP < 8.1. */
    public static function isList(array $value): bool
    {
        if (function_exists('array_is_list')) {
            return array_is_list($value);
        }
        $i = 0;
        foreach ($value as $key => $_) {
            if ($key !== $i++) {
                return false;
            }
        }
        return true;
    }

    /** Set or clear the merchant-panel JWT used for Bearer-protected endpoints. */
    public function setAccessToken(#[\SensitiveParameter] ?string $token): void
    {
        $this->accessToken = $token;
    }

    public function getAccessToken(): ?string
    {
        return $this->accessToken;
    }

    /**
     * Log in as a merchant-panel user and keep the access token for Bearer endpoints.
     *
     * @throws ApiException on bad credentials (the API answers HTTP 200 with an "errors" body)
     * @return array<string, mixed>|list<mixed>|null
     */
    public function login(string $email, #[\SensitiveParameter] string $secretWord): ?array
    {
        $result = $this->users->authenticate(['email' => $email, 'secretWord' => $secretWord]);
        $token = $result['data']['token']['accessToken'] ?? null;
        if (is_string($token) && $token !== '') {
            $this->accessToken = $token;
        }
        return $result;
    }

    /** The URL form the server verifies: a leading http:// becomes https://. */
    public static function signingUrl(string $url): string
    {
        return strncmp($url, 'http://', 7) === 0 ? 'https://' . substr($url, 7) : $url;
    }

    /**
     * Auth V2: lowercase hex HMAC-SHA256(secretKey, "METHOD\nurl\nsha256_hex(body)\napiKey\ntimestamp\nrndKey").
     * $body must be exactly the bytes sent (null or '' for no body).
     */
    public static function computeSignatureV2(string $method, string $url, ?string $body, string $apiKey, #[\SensitiveParameter] string $secretKey, string $timestamp, string $rndKey): string
    {
        $message = implode("\n", [strtoupper($method), $url, hash('sha256', $body ?? ''), $apiKey, $timestamp, $rndKey]);
        return hash_hmac('sha256', $message, $secretKey);
    }

    /** Auth V1: SHA-256 over url + apiKey + secretKey + rndKey. */
    public static function computeSignature(string $url, string $apiKey, #[\SensitiveParameter] string $secretKey, string $rndKey, string $encoding = 'hex'): string
    {
        $raw = hash('sha256', $url . $apiKey . $secretKey . $rndKey, true);
        return $encoding === 'base64' ? base64_encode($raw) : bin2hex($raw);
    }

    /** @param array<string, mixed> $query */
    public static function buildQuery(array $query): string
    {
        $parts = [];
        foreach ($query as $key => $value) {
            if ($value === null) {
                continue;
            }
            foreach (is_array($value) ? $value : [$value] as $v) {
                if ($v === null) {
                    continue;
                }
                if (is_bool($v)) {
                    $v = $v ? 'true' : 'false';
                }
                $parts[] = rawurlencode((string) $key) . '=' . rawurlencode((string) $v);
            }
        }
        return implode('&', $parts);
    }

    /**
     * Send a signed request. Use for endpoints not wrapped by the SDK.
     *
     * $body: an array, or an object (e.g. stdClass, JsonSerializable) to send exactly that JSON.
     * An empty PHP array encodes as `[]`; pass `new \stdClass()` for `{}`.
     *
     * @param array<string, mixed>|list<mixed>|object|null $body
     * @param array<string, mixed> $query
     * @return array<string, mixed>|list<mixed>|null
     */
    public function request(string $method, string $path, array|object|null $body = null, array $query = []): ?array
    {
        $url = $this->baseUrl . (strncmp($path, '/', 1) === 0 ? $path : '/' . $path);
        $qs = self::buildQuery($query);
        if ($qs !== '') {
            $url .= (strpos($url, '?') === false ? '?' : '&') . $qs;
        }

        $method = strtoupper($method);
        // Serialize once: the signed bytes and the sent bytes must be identical.
        $payload = null;
        if ($body !== null) {
            $payload = json_encode($body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        }

        $headers = [
            'Accept' => 'application/json',
            'User-Agent' => 'magicpay-php/' . self::VERSION,
        ] + $this->authHeaders($method, $url, $payload);
        if ($this->accessToken !== null && $this->accessToken !== '') {
            $headers['Authorization'] = 'Bearer ' . $this->accessToken;
        }
        if ($payload !== null) {
            $headers['Content-Type'] = 'application/json';
        }

        [$status, $text] = $this->http->send($method, $url, $headers, $payload);

        $parsed = null;
        if (trim($text) !== '') {
            $parsed = json_decode($text, true);
            if (json_last_error() !== JSON_ERROR_NONE) {
                $parsed = ['raw' => $text];
            }
        }
        // The API also reports some failures (e.g. bad login) as HTTP 200 + {"errors": {...}}.
        // Same rule as the other SDKs: only a non-empty JSON object counts, not a list.
        $errorsBody = is_array($parsed) && isset($parsed['errors']) && is_array($parsed['errors'])
            && $parsed['errors'] !== [] && !self::isList($parsed['errors']);
        // 3xx is an error too: redirects are not followed.
        if ($status >= 300 || $errorsBody) {
            $body = is_array($parsed) ? $parsed : null;
            $token = $body['data']['token']['accessToken'] ?? null;
            if (is_string($token) && $token !== '') {
                // Never put a login access token into an exception.
                $body['data']['token']['accessToken'] = '***';
                $text = str_replace($token, '***', $text);
            }
            throw new ApiException($status, $body, $text);
        }
        return is_array($parsed) ? $parsed : null;
    }

    /**
     * Signature headers for one request. $body must be the exact bytes that will be sent.
     *
     * @return array<string, string>
     */
    public function authHeaders(string $method, string $url, ?string $body, ?string $rndKey = null, ?string $timestamp = null): array
    {
        $rnd = $rndKey ?? bin2hex(random_bytes(16));
        $signUrl = self::signingUrl($url);
        $headers = ['x-api-key' => $this->apiKey, 'x-rnd-key' => $rnd, 'x-auth-version' => $this->authVersion];
        if ($this->authVersion === self::AUTH_V2) {
            $ts = $timestamp ?? (string) time();
            $headers['x-timestamp'] = $ts;
            $headers['x-signature'] = self::computeSignatureV2($method, $signUrl, $body, $this->apiKey, $this->secretKey, $ts, $rnd);
        } else {
            $headers['x-signature'] = self::computeSignature($signUrl, $this->apiKey, $this->secretKey, $rnd, $this->signatureEncoding);
        }
        return $headers;
    }
}
