# MagicPay PHP SDK

PHP 8.0+ client for the MagicPay API. Only needs `ext-curl` and `ext-json`.

```bash
composer require magicpay/magicpay-php
```

## Quick start

```php
<?php
require 'vendor/autoload.php';

use MagicPay\MagicPayClient;
use MagicPay\Exception\ApiException;

$mp = new MagicPayClient('YOUR_API_KEY', 'YOUR_SECRET_KEY');   // trdev, auth V2
// production: new MagicPayClient($key, $secret, ['base_url' => MagicPayClient::PRODUCTION_URL]);

// 1) Initialize a 3D Secure payment
$init = $mp->payments->init3dsPayment([
    'price' => 100.0, 'paidPrice' => 100.0, 'installment' => 1, 'currency' => 'TRY',
    'paymentGroup' => 'PRODUCT', 'paymentChannel' => 'Online',
    'clientIp' => $_SERVER['REMOTE_ADDR'] ?? '127.0.0.1',
    'redirectUrl' => 'https://shop.example.com/magicpay/return',
    'callbackUrl' => 'https://shop.example.com/magicpay/callback',
    'bankOrderId' => 'ORDER-1001',
    'card' => [
        'cardHolderName' => 'Jane Doe', 'cardNumber' => '5406675406675403',
        'expireMonth' => '12', 'expireYear' => '2030', 'cvc' => '000',
    ],
    'items' => [['name' => 'Item1', 'price' => 100.0]],
]);

// 2) In your return/callback controller
$done = $mp->payments->complete3dsPayment(['paymentId' => 123]);

// Query, refunds, installments
$payment = $mp->payments->retrievePayment(123);
$mp->payments->refundPayment(['paymentId' => 123, 'conversationId' => 'r-1', 'refundDestinationType' => 'PROVIDER']);
$mp->installments->listCheckoutInstallments(['amount' => 1250.5, 'currency' => 'TRY']);

// Bearer (merchant-panel) endpoints: log in once, the token is kept on the client
$mp->login('panel-user@example.com', 'secret-word');
$mp->pos->listPos(['isActivePos' => 'ACTIVE']);
$mp->members->searchMembers(['isBuyer' => true, 'page' => 0, 'size' => 20]);

// Plugin POS management (V2 only)
$banks = $mp->plugin->listBanks();

try {
    $mp->login('panel-user@example.com', 'wrong');
} catch (ApiException $e) {
    echo $e->getStatus(), ' ', $e->getErrorCode(), ' ', $e->getRawBody();   // 200 7005 {...}
}
```

`ApiException` is thrown for HTTP ≥ 300 (redirects are never followed) and for a 2xx body with
an `errors` object; `ConnectionException` for network problems. A login access token is masked
(`***`) in exceptions. Path parameters `''`, `.` and `..` and header values with CR/LF throw
`InvalidArgumentException`.

Bodies: an empty PHP array encodes as `[]`; pass `new \stdClass()` (or any object) when the API
expects `{}`. Credentials are marked `#[\SensitiveParameter]` (hidden from stack traces on PHP 8.2+).

## Options

| Key | Default | |
|---|---|---|
| `base_url` | `MagicPayClient::SANDBOX_URL` = `https://trdev.magicpay.ai` (test) | `PRODUCTION_URL` = `https://tr.magicpay.ai` with live keys; must be https |
| `allow_insecure` | `false` | allow an `http://` base URL for non-loopback hosts (tests/proxies only) |
| `auth_version` | `V2` | or `V1` (rejected by `plugin` endpoints) |
| `access_token` | none | set by `login()`; `setAccessToken()` / `getAccessToken()` |
| `timeout` | `30` | seconds |
| `signature_encoding` | `hex` | `base64` only with V1 |
| `http_client` | cURL, redirects not followed | any `MagicPay\Http\HttpClientInterface` (Guzzle adapter, test double); must send `$body` unchanged and not follow redirects |

Generic signed call: `$mp->request('GET', '/path', null, ['page' => 1])`. Signing helpers:
`MagicPayClient::computeSignatureV2(...)`, `MagicPayClient::computeSignature(...)` (V1).

All methods: [../ENDPOINTS.md](../ENDPOINTS.md). Tests (from the repository root, where `composer.json` lives): `composer dump-autoload && php php/tests/run.php`.
