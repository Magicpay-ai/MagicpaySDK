from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:  # pragma: no cover
    from .client import MagicPay


def path_param(value: Any) -> str:
    """URL-encode a single path segment. Empty, ``.`` and ``..`` are rejected (they would change the path)."""
    text = str(value)
    if text in ("", ".", ".."):
        raise ValueError(f"invalid path parameter: {text!r}")
    return quote(text, safe="")


class Resource:
    def __init__(self, client: "MagicPay") -> None:
        self._client = client
