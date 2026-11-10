<?php

declare(strict_types=1);

namespace MagicPay\Http;

interface HttpClientInterface
{
    /**
     * @param array<string, string> $headers
     * @return array{0: int, 1: string} [status code, response body]
     * @throws \MagicPay\Exception\ConnectionException
     */
    public function send(string $method, string $url, array $headers, ?string $body): array;
}
