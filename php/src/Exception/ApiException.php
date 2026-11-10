<?php

declare(strict_types=1);

namespace MagicPay\Exception;

/** The API answered with an HTTP status >= 300 (redirects are not followed), or with a 2xx body carrying an "errors" object. */
final class ApiException extends MagicPayException
{
    private int $status;
    /** @var array<string, mixed>|null */
    private ?array $body;
    private string $rawBody;

    /** @param array<string, mixed>|null $body */
    public function __construct(int $status, ?array $body, string $rawBody)
    {
        $msg = self::message($body) ?? $rawBody;
        parent::__construct('MagicPay API error ' . $status . ': ' . (is_string($msg) ? $msg : json_encode($msg)), $status);
        $this->status = $status;
        $this->body = $body;
        $this->rawBody = $rawBody;
    }

    public function getStatus(): int
    {
        return $this->status;
    }

    /** @return array<string, mixed>|null */
    public function getBody(): ?array
    {
        return $this->body;
    }

    public function getRawBody(): string
    {
        return $this->rawBody;
    }

    /** MagicPay error code from the "errors" object (e.g. "7005"), if any. */
    public function getErrorCode(): ?string
    {
        $errors = self::errorObject($this->body);
        $code = $errors['errorCode'] ?? $errors['error_code'] ?? null;
        return $code === null ? null : (string) $code;
    }

    /**
     * Top-level "errors" or (HTTPException style) "detail.errors"; non-empty arrays only.
     *
     * @param array<string, mixed>|null $body
     * @return array<string, mixed>|null
     */
    private static function errorObject(?array $body): ?array
    {
        foreach ([$body['errors'] ?? null, $body['detail']['errors'] ?? null] as $errors) {
            if (is_array($errors) && $errors !== [] && !\MagicPay\MagicPayClient::isList($errors)) {
                return $errors;
            }
        }
        return null;
    }

    /**
     * @param array<string, mixed>|null $body
     * @return mixed
     */
    private static function message(?array $body)
    {
        if ($body === null) {
            return null;
        }
        $msg = $body['message'] ?? $body['error'] ?? null;
        if ($msg === null && isset($body['detail']) && is_string($body['detail'])) {
            $msg = $body['detail'];
        }
        $errors = self::errorObject($body);
        if ($msg === null && $errors !== null) {
            $code = $errors['errorCode'] ?? $errors['error_code'] ?? null;
            $desc = $errors['errorDescription'] ?? $errors['error_description'] ?? null;
            if ($desc !== null && !is_string($desc)) {
                $desc = json_encode($desc);
            }
            $msg = ($code !== null && $desc !== null) ? $code . ': ' . $desc : ($desc ?? $code);
        }
        return $msg ?? $body['detail'] ?? null;
    }
}
