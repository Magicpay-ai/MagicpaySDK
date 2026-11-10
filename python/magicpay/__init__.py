"""MagicPay Python SDK."""

__version__ = "0.1.0"

from .client import (  # noqa: E402
    AUTH_V1,
    AUTH_V2,
    PRODUCTION_URL,
    SANDBOX_URL,
    MagicPay,
    compute_signature,
    compute_signature_v2,
)
from .errors import MagicPayAPIError, MagicPayConnectionError, MagicPayError  # noqa: E402

__all__ = [
    "MagicPay",
    "SANDBOX_URL",
    "PRODUCTION_URL",
    "AUTH_V1",
    "AUTH_V2",
    "compute_signature",
    "compute_signature_v2",
    "MagicPayError",
    "MagicPayAPIError",
    "MagicPayConnectionError",
]
