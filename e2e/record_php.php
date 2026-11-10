<?php
declare(strict_types=1);
require __DIR__ . '/../php/vendor/autoload.php';

use MagicPay\Http\HttpClientInterface;
use MagicPay\MagicPayClient;

$apiKey = getenv('MAGICPAY_API_KEY') ?: exit("MAGICPAY_API_KEY missing\n");
$secret = getenv('MAGICPAY_SECRET_KEY') ?: exit("MAGICPAY_SECRET_KEY missing\n");
$base = getenv('MAGICPAY_BASE_URL') ?: MagicPayClient::SANDBOX_URL;
$scenarios = json_decode(file_get_contents(__DIR__ . '/scenarios.json'), true);

final class Rec implements HttpClientInterface {
    public array $last = [];
    public function send(string $method, string $url, array $headers, ?string $body): array {
        $this->last = ['method' => $method, 'url' => $url, 'headers' => $headers, 'body' => $body];
        return [200, '{}'];
    }
}
$rec = new Rec();
$mp = new MagicPayClient($apiKey, $secret, ['base_url' => $base, 'http_client' => $rec]);
$out = fopen(__DIR__ . '/out/php.jsonl', 'w');
$camel = fn(string $s) => lcfirst(str_replace('_', '', ucwords($s, '_')));
foreach ($scenarios as $sc) {
    $args = $sc['args'];
    if (isset($sc['body'])) $args[] = $sc['body'];
    if (isset($sc['query'])) $args[] = $sc['query'];
    $mp->{$camel($sc['resource'])}->{$camel($sc['method'])}(...$args);
    fwrite($out, json_encode($rec->last + ['name' => $sc['name']], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n");
}
echo 'php: ', count($scenarios), " requests recorded\n";
