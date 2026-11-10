import base64
import copy
import hashlib
import ipaddress
import hmac
import json
import secrets
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union
from urllib.parse import quote, urlencode, urlsplit

from . import __version__
from .errors import MagicPayAPIError, MagicPayConnectionError, error_object
from . import resources as res
from .resources import RESOURCE_CLASSES

#: Dev/test environment (default).
SANDBOX_URL = "https://trdev.magicpay.ai"
#: Live environment.
PRODUCTION_URL = "https://tr.magicpay.ai"

AUTH_V1 = "V1"
AUTH_V2 = "V2"

#: sha256 of an empty body, used by V2 when a request has no body.
EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()

# (method, url, headers, body_bytes, timeout) -> (status, response_text)
Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], Tuple[int, str]]


def signing_url(url: str) -> str:
    """The URL form the server verifies: a leading ``http://`` becomes ``https://``."""
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def compute_signature(url: str, api_key: str, secret_key: str, rnd_key: str, encoding: str = "hex") -> str:
    """Auth V1: SHA-256 over ``url + api_key + secret_key + rnd_key``."""
    digest = hashlib.sha256((url + api_key + secret_key + rnd_key).encode("utf-8")).digest()
    if encoding == "base64":
        return base64.b64encode(digest).decode("ascii")
    return digest.hex()


def compute_signature_v2(
    method: str,
    url: str,
    body: Optional[Union[bytes, str]],
    api_key: str,
    secret_key: str,
    timestamp: str,
    rnd_key: str,
) -> str:
    """Auth V2: lowercase hex HMAC-SHA256(secret_key, message) where message is
    ``METHOD\\nurl\\nsha256_hex(body)\\napi_key\\ntimestamp\\nrnd_key``.

    ``body`` must be exactly the bytes sent on the wire (``None`` or empty for no body).
    """
    if isinstance(body, str):
        body = body.encode("utf-8")
    body_hash = hashlib.sha256(body or b"").hexdigest()
    message = "\n".join((method.upper(), url, body_hash, api_key, str(timestamp), rnd_key))
    return hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def build_query(query: Optional[Mapping[str, Any]]) -> str:
    if not query:
        return ""
    pairs = []
    for key, value in query.items():
        if value is None:
            continue
        values = value if isinstance(value, (list, tuple, set)) else [value]
        for v in values:
            if isinstance(v, bool):
                v = "true" if v else "false"
            pairs.append((key, str(v)))
    return urlencode(pairs, quote_via=quote)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: the signed headers must not be replayed to another URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_base_url(base_url: str, allow_insecure: bool) -> None:
    parts = urlsplit(base_url)
    if not parts.hostname or parts.scheme not in ("https", "http"):
        raise ValueError(f"invalid base_url: {base_url!r}")
    if parts.scheme == "http" and not allow_insecure and not _is_loopback(parts.hostname):
        raise ValueError("base_url must use https (http is allowed only for loopback hosts or with allow_insecure=True)")


def _redact_token(parsed: Any, text: str) -> Tuple[Any, str]:
    """Remove a login access token from a body that is about to go into an exception."""
    if isinstance(parsed, dict):
        data = parsed.get("data")
        token = data.get("token") if isinstance(data, dict) else None
        value = token.get("accessToken") if isinstance(token, dict) else None
        if isinstance(value, str) and value:
            parsed = copy.deepcopy(parsed)
            parsed["data"]["token"]["accessToken"] = "***"
            text = text.replace(value, "***")
    return parsed, text


def _urllib_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise MagicPayConnectionError(str(e)) from e


class MagicPay:
    """MagicPay API client.

    >>> mp = MagicPay(api_key="...", secret_key="...")          # trdev, auth V2
    >>> mp.payments.retrieve_payment(1086)
    >>> mp.login("panel-user@example.com", "secret-word")       # Bearer endpoints
    >>> mp.pos.list_pos()
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str = SANDBOX_URL,
        timeout: float = 30.0,
        signature_encoding: str = "hex",
        transport: Optional[Transport] = None,
        access_token: Optional[str] = None,
        auth_version: str = AUTH_V2,
        allow_insecure: bool = False,
    ) -> None:
        if not api_key or not secret_key:
            raise ValueError("api_key and secret_key are required")
        if auth_version not in (AUTH_V1, AUTH_V2):
            raise ValueError("auth_version must be 'V1' or 'V2'")
        if signature_encoding not in ("hex", "base64"):
            raise ValueError("signature_encoding must be 'hex' or 'base64'")
        if auth_version == AUTH_V2 and signature_encoding != "hex":
            raise ValueError("signature_encoding applies to auth V1 only; V2 is always hex")
        self.api_key = api_key
        self.secret_key = secret_key
        _check_base_url(base_url, allow_insecure)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.signature_encoding = signature_encoding
        self.auth_version = auth_version
        #: Merchant-panel JWT sent as "Authorization: Bearer" (set by login()).
        self.access_token = access_token
        self._transport = transport or _urllib_transport

        for name, cls in RESOURCE_CLASSES.items():
            setattr(self, name, cls(self))

    # Type hints for IDEs
    payments: "res.PaymentsResource"
    wallets: "res.WalletsResource"
    users: "res.UsersResource"
    members: "res.MembersResource"
    api_members: "res.ApiMembersResource"
    installments: "res.InstallmentsResource"
    catalog: "res.CatalogResource"
    custom_links: "res.CustomLinksResource"
    magic_links: "res.MagicLinksResource"
    merchants: "res.MerchantsResource"
    payment_facilities: "res.PaymentFacilitiesResource"
    pos: "res.PosResource"
    submerchants: "res.SubmerchantsResource"
    reports: "res.ReportsResource"
    subscriptions: "res.SubscriptionsResource"
    api_keys: "res.ApiKeysResource"
    plugin: "res.PluginResource"

    def auth_headers(
        self,
        url: str,
        rnd_key: Optional[str] = None,
        method: str = "GET",
        body: Optional[bytes] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, str]:
        """Signature headers for one request. ``body`` must be the exact bytes that will be sent."""
        rnd = rnd_key or secrets.token_hex(16)
        url = signing_url(url)
        headers = {"x-api-key": self.api_key, "x-rnd-key": rnd, "x-auth-version": self.auth_version}
        if self.auth_version == AUTH_V2:
            ts = timestamp or str(int(time.time()))
            headers["x-timestamp"] = ts
            headers["x-signature"] = compute_signature_v2(
                method, url, body, self.api_key, self.secret_key, ts, rnd
            )
        else:
            headers["x-signature"] = compute_signature(
                url, self.api_key, self.secret_key, rnd, self.signature_encoding
            )
        return headers

    def login(self, email: str, secret_word: str) -> Any:
        """Log in as a merchant-panel user and keep the access token for Bearer endpoints.

        Raises MagicPayAPIError on bad credentials (the API answers HTTP 200 with an ``errors`` body).
        The token is stored on this client instance, so concurrent requests on the same client
        (other threads) switch to the new token immediately; use one client per panel user.
        """
        result = self.users.authenticate({"email": email, "secretWord": secret_word})
        token = None
        if isinstance(result, dict) and isinstance(result.get("data"), dict):
            token_obj = result["data"].get("token")
            if isinstance(token_obj, dict):
                token = token_obj.get("accessToken")
        if token:
            self.access_token = token
        return result

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Any] = None,
        query: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """Send a signed request. Use this for endpoints not wrapped by the SDK."""
        method = method.upper()
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        qs = build_query(query)
        if qs:
            url += ("&" if "?" in url else "?") + qs

        # Serialize once: the signed bytes and the sent bytes must be identical.
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        headers = {
            "Accept": "application/json",
            "User-Agent": f"magicpay-python/{__version__}",
            **self.auth_headers(url, method=method, body=data),
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if data is not None:
            headers["Content-Type"] = "application/json"

        status, text = self._transport(method, url, headers, data, self.timeout)
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = text
        # The API also reports some failures (e.g. bad login) as HTTP 200 + {"errors": {...}}.
        # 3xx is an error too: redirects are not followed (see _NoRedirect).
        if status >= 300 or (isinstance(parsed, dict) and error_object(parsed, top_level_only=True)):
            parsed, text = _redact_token(parsed, text)
            raise MagicPayAPIError(status, parsed, text)
        return parsed
