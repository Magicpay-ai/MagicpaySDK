<?php

// Dependency-free test runner, from the repository root: `php php/tests/run.php` (or `composer test`)
declare(strict_types=1);

require dirname(__DIR__, 2) . '/vendor/autoload.php';

use MagicPay\Exception\ApiException;
use MagicPay\Http\HttpClientInterface;
use MagicPay\MagicPayClient;

// Shared cross-SDK test vectors (see ../../README.md)
const V1_URL = 'https://trdev.magicpay.ai/payment/v1/card-payments/1086?page=1&size=10';
const V1_SIG = 'a0a1b034e46f3690306e10ad629a72f0a5c7687068b0be53239d1feb6cf824c5';
const V2_URL = 'https://trdev.magicpay.ai/payment/v1/card-payments/3ds-complete';
const V2_BODY = '{"paymentId":123}';
const V2_SIG = 'ece3b0b7830f3b720257c097c2a6cc4d2dafc81cb937af758231c8fedb16b495';
const LOGIN_OK = '{"data":{"merchantId":7,"status":"Success","token":{"accessToken":"jwt-login","expiresIn":3600}}}';
const LOGIN_BAD = '{"errors":{"errorCode":"7005","errorDescription":"E-posta adresi ya da şifre hatalı"}}';

final class RecordingHttp implements HttpClientInterface
{
    /** @var list<array{string,string,array<string,string>,?string}> */
    public array $calls = [];
    /** @var list<array{int,string}> */
    private array $responses;

    /** @param array{int,string} ...$responses */
    public function __construct(array ...$responses)
    {
        $this->responses = $responses ?: [[200, '{"data":{"id":1}}']];
    }

    public function send(string $method, string $url, array $headers, ?string $body): array
    {
        $this->calls[] = [$method, $url, $headers, $body];
        return $this->responses[min(count($this->calls), count($this->responses)) - 1];
    }
}

$failures = 0;
function test(string $name, callable $fn): void
{
    global $failures;
    try {
        $fn();
        echo "ok   $name\n";
    } catch (\Throwable $e) {
        $failures++;
        echo "FAIL $name: {$e->getMessage()}\n";
    }
}
function eq($expected, $actual): void
{
    if ($expected !== $actual) {
        throw new \Exception('expected ' . var_export($expected, true) . ' got ' . var_export($actual, true));
    }
}
/** @param array<string,string> $h */
function v2(string $method, string $url, array $h, ?string $body): string
{
    return MagicPayClient::computeSignatureV2($method, $url, $body, 'k', 's', $h['x-timestamp'], $h['x-rnd-key']);
}

test('environment URLs', function () {
    eq('https://trdev.magicpay.ai', MagicPayClient::SANDBOX_URL);
    eq('https://tr.magicpay.ai', MagicPayClient::PRODUCTION_URL);
});

test('V1 signature vector', function () {
    eq(V1_SIG, MagicPayClient::computeSignature(V1_URL, 'test-api-key', 'test-secret-key', 'abc123'));
});

test('V2 signature vector', function () {
    eq(V2_SIG, MagicPayClient::computeSignatureV2('POST', V2_URL, V2_BODY, 'test-api-key', 'test-secret-key', '1700000000', 'abc123'));
    eq(V2_SIG, MagicPayClient::computeSignatureV2('post', V2_URL, V2_BODY, 'test-api-key', 'test-secret-key', '1700000000', 'abc123'));
    eq(
        MagicPayClient::computeSignatureV2('GET', V1_URL, '', 'k', 's', '1', 'r'),
        MagicPayClient::computeSignatureV2('GET', V1_URL, null, 'k', 's', '1', 'r')
    );
});

test('V2 headers by default (GET, path + query)', function () {
    $h = new RecordingHttp();
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    $res = $mp->wallets->searchWalletTransactions(42, ['page' => 1, 'size' => 10, 'skip' => null]);
    eq(1, $res['data']['id']);
    [$method, $url, $headers, $body] = $h->calls[0];
    eq('GET', $method);
    eq('https://trdev.magicpay.ai/wallet/v1/wallets/42/wallet-transactions?page=1&size=10', $url);
    eq(null, $body);
    eq('k', $headers['x-api-key']);
    eq('V2', $headers['x-auth-version']);
    eq(true, abs((int) $headers['x-timestamp'] - time()) <= 5);
    eq(v2('GET', $url, $headers, null), $headers['x-signature']);
});

test('rnd key changes per request', function () {
    $h = new RecordingHttp();
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    $mp->payments->retrievePayment(1);
    $mp->payments->retrievePayment(1);
    eq(false, $h->calls[0][2]['x-rnd-key'] === $h->calls[1][2]['x-rnd-key']);
});

test('V2 body hash uses the sent bytes', function () {
    $h = new RecordingHttp();
    $mp = new MagicPayClient('k', 's', ['http_client' => $h, 'base_url' => 'https://api.example.com/']);
    $mp->payments->complete3dsPayment(['paymentId' => 123, 'note' => 'ürün']);
    [$method, $url, $headers, $body] = $h->calls[0];
    eq(['POST', 'https://api.example.com/payment/v1/card-payments/3ds-complete'], [$method, $url]);
    eq('{"paymentId":123,"note":"ürün"}', $body);
    eq('application/json', $headers['Content-Type']);
    eq(v2('POST', $url, $headers, $body), $headers['x-signature']);
});

test('http base URL is signed as https', function () {
    $h = new RecordingHttp();
    (new MagicPayClient('k', 's', ['http_client' => $h, 'base_url' => 'http://127.0.0.1:8080']))->payments->retrievePayment(5);
    [$method, $url, $headers] = $h->calls[0];
    eq('http://127.0.0.1:8080/payment/v1/card-payments/5', $url);
    eq(v2('GET', 'https://127.0.0.1:8080/payment/v1/card-payments/5', $headers, null), $headers['x-signature']);
});

test('V1 option', function () {
    $h = new RecordingHttp();
    (new MagicPayClient('k', 's', ['http_client' => $h, 'auth_version' => 'V1']))->payments->retrievePayment(1086);
    [, $url, $headers] = $h->calls[0];
    eq('V1', $headers['x-auth-version']);
    eq(false, isset($headers['x-timestamp']));
    eq(MagicPayClient::computeSignature($url, 'k', 's', $headers['x-rnd-key']), $headers['x-signature']);
    foreach ([['auth_version' => 'V3'], ['signature_encoding' => 'base64']] as $bad) {
        try {
            new MagicPayClient('k', 's', $bad);
            throw new \Exception('no exception for ' . json_encode($bad));
        } catch (\InvalidArgumentException $e) {
        }
    }
    new MagicPayClient('k', 's', ['auth_version' => 'V1', 'signature_encoding' => 'base64']);
});

test('POST without body; array response', function () {
    $h = new RecordingHttp([200, '{}'], [200, '["CREDIT_CARD","Visa","Garanti BBVA","Bonus","Credit"]']);
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    $mp->payments->refreshPayguruPayment(77);
    [$method, $url, $headers, $body] = $h->calls[0];
    eq(['POST', 'https://trdev.magicpay.ai/payment/v1/payguru/payments/77/refresh'], [$method, $url]);
    eq(null, $body);
    eq(false, isset($headers['Content-Type']));
    eq(v2('POST', $url, $headers, null), $headers['x-signature']);
    eq('Garanti BBVA', $mp->installments->checkBin('435508')[2]);
    eq('https://trdev.magicpay.ai/payment/v1/card-payments/bank-name/435508', $h->calls[1][1]);
});

function throws(callable $fn, string $class): void
{
    try {
        $fn();
    } catch (\Throwable $e) {
        if ($e instanceof $class) {
            return;
        }
        throw new \Exception('expected ' . $class . ' got ' . get_class($e) . ': ' . $e->getMessage());
    }
    throw new \Exception('expected ' . $class . ', nothing thrown');
}

test('base_url must be https', function () {
    foreach (['http://trdev.magicpay.ai', 'ftp://x', 'trdev.magicpay.ai'] as $bad) {
        throws(fn () => new MagicPayClient('k', 's', ['base_url' => $bad]), \InvalidArgumentException::class);
    }
    foreach (['http://127.0.0.1:1', 'http://localhost', 'http://[::1]:8080', MagicPayClient::PRODUCTION_URL] as $ok) {
        new MagicPayClient('k', 's', ['base_url' => $ok]);
    }
    new MagicPayClient('k', 's', ['base_url' => 'http://trdev.magicpay.ai', 'allow_insecure' => true]);
});

test('path params reject dot segments', function () {
    $h = new RecordingHttp();
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    foreach (['', '.', '..'] as $bad) {
        throws(fn () => $mp->payments->retrievePayment($bad), \InvalidArgumentException::class);
    }
    $mp->payments->retrievePayment('a b/..');
    eq('https://trdev.magicpay.ai/payment/v1/card-payments/a%20b%2F..', $h->calls[0][1]);
});

test('3xx is an error; login token redacted', function () {
    $h = new RecordingHttp([302, LOGIN_OK]);
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    try {
        $mp->login('user@example.com', 'pw');
        throw new \Exception('no exception');
    } catch (ApiException $e) {
        eq(302, $e->getStatus());
        eq(false, str_contains($e->getMessage() . $e->getRawBody() . json_encode($e->getBody()), 'jwt-login'));
        eq('***', $e->getBody()['data']['token']['accessToken']);
    }
    eq(null, $mp->getAccessToken());
});

test('errors list is not an error; empty path; object body', function () {
    $h = new RecordingHttp([200, '{"errors":["x"]}'], [200, '{}'], [200, '{}']);
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    eq(['errors' => ['x']], $mp->payments->retrievePayment(1));
    $mp->request('GET', '');
    eq('https://trdev.magicpay.ai/', $h->calls[1][1]);
    $mp->request('POST', '/x', new \stdClass());
    eq('{}', $h->calls[2][3]);
});

test('CR/LF in header values is rejected', function () {
    throws(fn () => (new \MagicPay\Http\CurlHttpClient())->send('GET', 'https://127.0.0.1:1/', ['Authorization' => "Bearer a\r\nX-Evil: 1"], null), \InvalidArgumentException::class);
});

test('PUT with two path params', function () {
    $h = new RecordingHttp();
    (new MagicPayClient('k', 's', ['http_client' => $h]))->pos->changePosStatus(7, 'PASSIVE');
    eq('PUT', $h->calls[0][0]);
    eq('https://trdev.magicpay.ai/merchant/v1/merchant-poses/7/status/PASSIVE', $h->calls[0][1]);
});

test('Bearer token', function () {
    $h = new RecordingHttp();
    $mp = new MagicPayClient('k', 's', ['http_client' => $h, 'access_token' => 'jwt-1']);
    $mp->pos->listPos();
    eq('Bearer jwt-1', $h->calls[0][2]['Authorization']);
    $mp->setAccessToken(null);
    $mp->pos->listPos();
    eq(false, isset($h->calls[1][2]['Authorization']));
});

test('login stores the token; Bearer added afterwards', function () {
    $h = new RecordingHttp([200, LOGIN_OK], [200, '{"data":[]}']);
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    $res = $mp->login('user@example.com', 'pw');
    eq(7, $res['data']['merchantId']);
    eq('jwt-login', $mp->getAccessToken());
    [$method, $url, $headers, $body] = $h->calls[0];
    eq(['POST', 'https://trdev.magicpay.ai/merchant/v1/authenticate'], [$method, $url]);
    eq('{"email":"user@example.com","secretWord":"pw"}', $body);
    eq(false, isset($headers['Authorization']));
    $mp->pos->listPos(['isActivePos' => 'PASSIVE']);
    eq('Bearer jwt-login', $h->calls[1][2]['Authorization']);
    eq('https://trdev.magicpay.ai/merchant/v1/merchant-poses/?isActivePos=PASSIVE', $h->calls[1][1]);
});

test('login errors body raises', function () {
    $h = new RecordingHttp([200, LOGIN_BAD]);
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    try {
        $mp->login('user@example.com', 'wrong');
        throw new \Exception('no exception');
    } catch (ApiException $e) {
        eq(200, $e->getStatus());
        eq('7005', $e->getErrorCode());
        eq(true, str_contains($e->getMessage(), '7005'));
    }
    eq(null, $mp->getAccessToken());
});

test('API error', function () {
    $h = new RecordingHttp([400, '{"message":"invalid card"}']);
    try {
        (new MagicPayClient('k', 's', ['http_client' => $h]))->payments->retrievePayment(1);
        throw new \Exception('no exception');
    } catch (ApiException $e) {
        eq(400, $e->getStatus());
        eq(true, str_contains($e->getMessage(), 'invalid card'));
    }
});

test('API error with detail.errors', function () {
    $h = new RecordingHttp([400, '{"detail":{"errors":{"errorCode":"2006","errorDescription":"bad signature"}}}']);
    try {
        (new MagicPayClient('k', 's', ['http_client' => $h]))->payments->retrievePayment(1);
        throw new \Exception('no exception');
    } catch (ApiException $e) {
        eq('2006', $e->getErrorCode());
        eq(true, str_contains($e->getMessage(), 'bad signature'));
    }
});

test('null / empty errors is not an error', function () {
    $h = new RecordingHttp([200, '{"data":{"id":1},"errors":null}'], [200, '{"errors":{}}']);
    $mp = new MagicPayClient('k', 's', ['http_client' => $h]);
    eq(1, $mp->payments->retrievePayment(1)['data']['id']);
    eq(['errors' => []], $mp->payments->retrievePayment(1));
});

echo $failures === 0 ? "ALL PASSED\n" : "$failures FAILED\n";
exit($failures === 0 ? 0 : 1);
