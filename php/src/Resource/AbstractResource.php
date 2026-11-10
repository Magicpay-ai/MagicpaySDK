<?php

declare(strict_types=1);

namespace MagicPay\Resource;

use MagicPay\MagicPayClient;

abstract class AbstractResource
{
    protected MagicPayClient $client;

    public function __construct(MagicPayClient $client)
    {
        $this->client = $client;
    }

    /**
     * URL-encode one path segment; '', '.' and '..' are rejected (they would change the path).
     *
     * @param string|int $value
     */
    protected static function p($value): string
    {
        $text = (string) $value;
        if ($text === '' || $text === '.' || $text === '..') {
            throw new \InvalidArgumentException("invalid path parameter: '" . $text . "'");
        }
        return rawurlencode($text);
    }
}
