from typing import Any, Optional


def error_object(body: Any, top_level_only: bool = False) -> Optional[dict]:
    """The API's ``errors`` object: top-level ``errors`` or (HTTPException style) ``detail.errors``.

    Only a non-empty object counts.
    """
    if not isinstance(body, dict):
        return None
    errors = body.get("errors")
    if not (isinstance(errors, dict) and errors) and not top_level_only:
        detail = body.get("detail")
        errors = detail.get("errors") if isinstance(detail, dict) else None
    return errors if isinstance(errors, dict) and errors else None


class MagicPayError(Exception):
    """Base error for the MagicPay SDK."""


class MagicPayConnectionError(MagicPayError):
    """Network problem: DNS, TLS, timeout, connection refused..."""


class MagicPayAPIError(MagicPayError):
    """The API answered with an HTTP status >= 300 (redirects are not followed), or with a 2xx body
    carrying an ``errors`` object."""

    def __init__(self, status: int, body: Any, raw: Optional[str] = None) -> None:
        self.status = status
        self.body = body
        self.raw = raw
        message = None
        if isinstance(body, dict):
            message = body.get("message") or body.get("error")
            if not message and isinstance(body.get("detail"), str):
                message = body["detail"]
            errors = error_object(body)
            if not message and errors:
                desc = errors.get("errorDescription") or errors.get("error_description")
                message = f"{self.error_code}: {desc}" if self.error_code and desc else (desc or self.error_code)
            if not message and body.get("detail") is not None:
                message = str(body["detail"])
        super().__init__(f"MagicPay API error {status}: {message or raw or body}")

    @property
    def error_code(self) -> Optional[str]:
        """MagicPay error code from the ``errors`` object (e.g. "7005"), if any."""
        errors = error_object(self.body)
        if not errors:
            return None
        code = errors.get("errorCode") or errors.get("error_code")
        return None if code is None else str(code)
