<?php

declare(strict_types=1);

namespace MagicPay\Http;

use MagicPay\Exception\ConnectionException;

final class CurlHttpClient implements HttpClientInterface
{
    private int $timeout;

    public function __construct(int $timeout = 30)
    {
        $this->timeout = $timeout;
    }

    public function send(string $method, string $url, array $headers, ?string $body): array
    {
        $ch = curl_init($url);
        $lines = [];
        foreach ($headers as $k => $v) {
            if (preg_match('/[\r\n]/', $k . $v)) {
                throw new \InvalidArgumentException('header ' . preg_replace('/[\r\n]/', '', $k) . ' contains CR/LF');
            }
            $lines[] = $k . ': ' . $v;
        }
        curl_setopt_array($ch, [
            CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER => $lines,
            CURLOPT_TIMEOUT => $this->timeout,
            CURLOPT_CONNECTTIMEOUT => min(10, $this->timeout),
            // Never follow redirects: the signed headers must not reach another URL.
            CURLOPT_FOLLOWLOCATION => false,
        ]);
        if ($body !== null) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        }
        $text = curl_exec($ch);
        if ($text === false) {
            $err = curl_error($ch);
            curl_close($ch);
            throw new ConnectionException('MagicPay connection error: ' . $err);
        }
        $status = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        curl_close($ch);
        return [$status, (string) $text];
    }
}
