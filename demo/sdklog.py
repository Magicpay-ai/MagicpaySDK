"""SDK request log ("fiş rulosu"): a logging transport for the MagicPay client, masking and an
in-memory store.

Everything is masked here, before it is stored, so no raw card data or secret ever reaches the
store, the templates or the browser.
"""
import contextvars
import json
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

from magicpay.client import _urllib_transport

# --------------------------------------------------------------------------------------------
# Which SDK method / UI action caused the call (set by the route right before calling the SDK)
# --------------------------------------------------------------------------------------------

_call_ctx: contextvars.ContextVar = contextvars.ContextVar("magicpay_demo_call", default=None)


def set_call(method_name: str, trigger: str):
    return _call_ctx.set({"method": method_name, "trigger": trigger})


def reset_call(token) -> None:
    _call_ctx.reset(token)


# Endpoints the API serves without authentication (the SDK still sends headers; the log says
# "İmzasız" because the server does not check them).
UNSIGNED_PATH_PREFIXES = ("/payment/v1/card-payments/bank-name/",)

# --------------------------------------------------------------------------------------------
# Masking
# --------------------------------------------------------------------------------------------

LONG_STRING_LIMIT = 300
LONG_STRING_KEEP = 60

_CARD_KEYS = {"cardnumber", "pan", "cardno", "creditcardnumber", "cardpan"}
_FULL_MASK_KEYS = {"cvc", "cvv", "cvv2", "cvc2", "expiremonth", "expireyear", "expiry",
                   "expiredate", "expirationdate", "cardexpiry"}
# Masked when the normalized key name CONTAINS one of these.
_SECRET_PARTS = ("secret", "password", "token", "signature", "storekey", "apikey",
                 "authorization", "rndkey", "privatekey", "credential", "clientid", "email",
                 "phone", "gsm", "tckn", "identity", "iban", "hash", "cardholder", "holdername")
# Masked when the normalized key name EQUALS one of these (too short to match as a substring).
_SECRET_EXACT = {"key", "value", "sign", "mail", "surname", "contactname", "contactsurname"}
# The bank's 3D form carries the card number; the log shows a placeholder instead.
_PLACEHOLDER_KEYS = {"htmlcontent": "(banka formu, gizlendi)"}
HIDDEN = "(gizlendi)"

# Responses that list account data are shown through an allowlist, not a blacklist: anything
# not named here is replaced by HIDDEN, so a new field the API starts returning never leaks.
ALLOWLIST_PATHS = {
    "/api/merchant/v1/api-credentials": {"id", "name", "status", "isActive", "is_active"},
    "/api/v1/members": {"id", "status", "isActive", "is_active"},
}
_ALLOWLIST_COMMON = {"items", "data", "page", "size", "totalSize", "total", "totalPages", "count",
                     "success", "errors", "errorCode", "error_code", "errorDescription",
                     "error_description", "error_message", "error_message_detail", "errorGroup",
                     "error_group", "detail", "message"}

# Our own bank-return token inside redirect URLs.
_RETURN_TOKEN = re.compile(r"(/odeme/donus/)[^/?#\s\"'<>]+")

# Card-number-like digit runs inside free text (e.g. the PAN in the bank's 3D form HTML).
_PAN_RUN = re.compile(r"(?<![0-9A-Za-z])\d{15,19}(?![0-9])")
_PAN_GROUPED = re.compile(r"(?<![0-9A-Za-z])\d{4}(?:[ -]\d{4}){2,3}(?:[ -]\d{1,3})?(?![0-9])")

_secret_values: List[str] = []


def register_secret(value: Optional[str]) -> None:
    """Values (API key, secret key) that must never appear in the log, wherever they show up."""
    if value and len(value) >= 8 and value not in _secret_values:
        _secret_values.append(value)


def _norm(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def mask_card(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 12:
        return "*" * max(len(value), 4)
    return digits[:6] + "*" * (len(digits) - 10) + digits[-4:]


def _tr_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def scrub_text(text: str) -> str:
    for secret in _secret_values:
        if secret in text:
            text = text.replace(secret, "****")
    text = _RETURN_TOKEN.sub(lambda m: m.group(1) + "****", text)
    text = _PAN_GROUPED.sub(lambda m: mask_card(m.group()), text)
    return _PAN_RUN.sub(lambda m: mask_card(m.group()), text)


def is_secret_key(name: Any) -> bool:
    n = _norm(name)
    return n in _SECRET_EXACT or any(part in n for part in _SECRET_PARTS)


def allowlist_view(value: Any, allowed: set, path: str = "", paths: Optional[List[str]] = None) -> Any:
    """Keep only allowlisted keys (recursing into lists and allowed containers); hide the rest."""
    if paths is None:
        paths = []
    keep = allowed | _ALLOWLIST_COMMON
    if isinstance(value, list):
        return [allowlist_view(v, allowed, _pointer(path, i), paths) for i, v in enumerate(value)]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in keep:
                out[k] = allowlist_view(v, allowed, _pointer(path, k), paths)
            else:
                out[k] = HIDDEN
                paths.append(_pointer(path, k))
        return out
    return value


def _truncate(text: str) -> str:
    if len(text) <= LONG_STRING_LIMIT:
        return text
    rest = len(text) - LONG_STRING_KEEP
    return f"{text[:LONG_STRING_KEEP]}… ({_tr_int(rest)} karakter daha, kısaltıldı)"


def _pointer(path: str, key: Any) -> str:
    return f"{path}/{str(key).replace('~', '~0').replace('/', '~1')}"


def _mask(value: Any, key: Any, path: str, paths: List[str]) -> Any:
    if value == HIDDEN:  # already hidden by an allowlist view
        return value
    if key is not None and value is not None and not isinstance(value, bool):
        n = _norm(key)
        if n in _CARD_KEYS and isinstance(value, (str, int)):
            paths.append(path)
            return mask_card(str(value))
        if n in _FULL_MASK_KEYS and isinstance(value, (str, int, float)):
            paths.append(path)
            return "*" * max(len(str(value)), 2)
        if n in _PLACEHOLDER_KEYS:
            paths.append(path)
            return _PLACEHOLDER_KEYS[n]
        if is_secret_key(key):
            paths.append(path)
            return "****"
    if isinstance(value, dict):
        return {k: _mask(v, k, _pointer(path, k), paths) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v, None, _pointer(path, i), paths) for i, v in enumerate(value)]
    if isinstance(value, str):
        scrubbed = scrub_text(value)
        if scrubbed != value:
            paths.append(path)
        return _truncate(scrubbed)
    return value


def mask_json(value: Any) -> Tuple[Any, List[str]]:
    """Recursively masked copy of ``value`` and the JSON pointers of the masked values."""
    paths: List[str] = []
    return _mask(value, None, "", paths), paths


def mask_headers(headers: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    out: Dict[str, str] = {}
    paths: List[str] = []
    for name, value in headers.items():
        n = _norm(name)
        pointer = _pointer("", name)
        if n == "xapikey" or any(part in n for part in _SECRET_PARTS):
            out[name] = "****"
            paths.append(pointer)
        else:
            out[name] = scrub_text(value)
    return out, paths


# --------------------------------------------------------------------------------------------
# Reading MagicPay error bodies (both shapes, camelCase and snake_case)
# --------------------------------------------------------------------------------------------

def unwrap(body: Any) -> Any:
    """Many responses put the object under ``data``; return the inner object if so."""
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body


def payment_status_of(body: Any) -> Optional[str]:
    for obj in (body, unwrap(body)):
        if isinstance(obj, dict) and isinstance(obj.get("paymentStatus"), str):
            return obj["paymentStatus"]
    return None


def is_pending(body: Any) -> bool:
    return any(isinstance(o, dict) and o.get("pending") is True for o in (body, unwrap(body)))


def extract_error(body: Any) -> Tuple[Optional[str], Optional[str]]:
    """(error code, readable message) from a MagicPay error body, or (None, None)."""
    if not isinstance(body, dict):
        return None, (body.strip()[:200] or None) if isinstance(body, str) else None
    errors = body.get("errors")
    if not (isinstance(errors, dict) and errors):
        detail = body.get("detail")
        errors = detail.get("errors") if isinstance(detail, dict) else None
    code = message = None
    if isinstance(errors, dict) and errors:
        raw_code = errors.get("errorCode", errors.get("error_code"))
        code = None if raw_code in (None, "") else str(raw_code)
        message = (errors.get("errorDescription") or errors.get("error_description")
                   or errors.get("errorMessage") or errors.get("error_message"))
        detail_text = errors.get("errorMessageDetail") or errors.get("error_message_detail")
        if isinstance(detail_text, str) and detail_text and detail_text != message:
            message = f"{message.rstrip('.')}. {detail_text}" if message else detail_text
    if not message:
        for key in ("detail", "message", "error"):
            if isinstance(body.get(key), str) and body[key]:
                message = body[key]
                break
    return code, (str(message) if message else None)


# --------------------------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------------------------

class SdkLog:
    def __init__(self, max_entries: int = 300) -> None:
        self._lock = threading.Lock()
        self._entries: List[Dict[str, Any]] = []  # oldest first
        self._seq = 0
        self._generation = 1
        self._cleared = False
        self._max = max_entries

    def add(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            entry["seq"] = self._seq
            self._entries.append(entry)
            if len(self._entries) > self._max:
                del self._entries[: len(self._entries) - self._max]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._generation += 1
            self._cleared = True

    def snapshot(self, after: int = 0) -> Dict[str, Any]:
        with self._lock:
            return {
                "generation": self._generation,
                "cleared": self._cleared,
                "count": len(self._entries),
                "lastSeq": self._seq,
                "entries": [e for e in self._entries if e["seq"] > after],
            }

    def last_for(self, method_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for entry in reversed(self._entries):
                if entry["method"] == method_name:
                    return entry
        return None


def _build_entry(method: str, url: str, headers: Dict[str, str], body: Optional[bytes],
                 status: Optional[int], text: Optional[str], error: Optional[BaseException],
                 started: datetime, duration_ms: int) -> Dict[str, Any]:
    ctx = _call_ctx.get() or {}
    parts = urlsplit(url)
    path = parts.path
    query = dict(parse_qsl(parts.query, keep_blank_values=True)) or None
    allowed = ALLOWLIST_PATHS.get(path.rstrip("/"))

    if path.startswith(UNSIGNED_PATH_PREFIXES):
        auth = "none"
    else:
        auth = headers.get("x-auth-version") or "none"

    if method.upper() == "GET" or body is None:
        request_obj = query
    else:
        try:
            request_obj = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            request_obj = body.decode("utf-8", errors="replace")

    response_obj: Any = None
    if text:
        try:
            response_obj = json.loads(text)
        except ValueError:
            response_obj = text

    method_name = ctx.get("method") or "client.request"
    kind = "ok"
    error_line = None
    bank_reject = False
    if error is not None:
        kind = "error"
        reason = "zaman aşımı, 30 sn" if "timed out" in str(error).lower() else "bağlantı kurulamadı"
        error_line = f"MagicPay'e ulaşılamadı ({reason})."
    elif status is not None and status >= 300:
        kind = "error"
        code, msg = extract_error(response_obj)
        msg = msg or f"HTTP {status} yanıtı"
        error_line = f"Hata {code}: {msg}" if code else f"Hata: {msg}"
    elif payment_status_of(response_obj) == "FAILURE":
        kind = "error"
        bank_reject = True
        code, msg = extract_error(response_obj)
        msg = msg or "Banka bir açıklama göndermedi."
        error_line = f'Banka reddetti: "{msg}"' + (f" (kod {code})" if code else "")
    else:
        code, msg = extract_error(response_obj)
        if code or (isinstance(response_obj, dict) and response_obj.get("errors")):
            kind = "error"
            error_line = f"Hata {code}: {msg}" if code else f"Hata: {msg}"

    req_masked, req_paths = mask_json(request_obj)
    if allowed is not None and isinstance(response_obj, (dict, list)):
        view_paths: List[str] = []
        response_obj = allowlist_view(response_obj, allowed, "", view_paths)
        res_masked, res_paths = mask_json(response_obj)
        res_paths = sorted(set(res_paths) | set(view_paths))
    else:
        res_masked, res_paths = mask_json(response_obj)
    hdr_masked, hdr_paths = mask_headers(headers)
    if error_line:
        error_line = _truncate(scrub_text(error_line))

    status_text = f"HTTP {status}" if status is not None else "HTTP yanıtı yok"
    prefix = "Hatalı SDK çağrısı" if kind == "error" else "Yeni SDK çağrısı"
    return {
        "method": method_name,
        "trigger": ctx.get("trigger") or "",
        "time": started.strftime("%H:%M:%S"),
        "httpMethod": method.upper(),
        "path": scrub_text(path),
        "query": scrub_text(parts.query or ""),
        "auth": auth,
        "status": status,
        "ms": duration_ms,
        "headers": hdr_masked,
        "headersMasked": hdr_paths,
        "request": req_masked,
        "requestMasked": req_paths,
        "response": res_masked,
        "responseMasked": res_paths,
        "kind": kind,
        "bankReject": bank_reject,
        "errorLine": error_line,
        "announce": f"{prefix}: {method_name}, {status_text}.",
    }


def logging_transport(log: SdkLog, base=_urllib_transport):
    """Wrap an SDK transport so that every request lands in ``log`` (masked)."""

    def transport(method, url, headers, body, timeout):
        started = datetime.now()
        t0 = time.perf_counter()
        status = text = error = None
        try:
            status, text = base(method, url, headers, body, timeout)
            return status, text
        except Exception as exc:  # MagicPayConnectionError and anything unexpected
            error = exc
            raise
        finally:
            duration = round((time.perf_counter() - t0) * 1000)
            try:
                log.add(_build_entry(method, url, dict(headers), body, status, text, error,
                                     started, duration))
            except Exception:  # the log must never break a payment
                pass

    return transport
