"""MagicPay SDK demo store (local, single user).

Run: uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
"""
import ipaddress
import logging
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))  # the SDK, not installed
sys.path.insert(0, str(HERE))

from fastapi import FastAPI, Form, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from starlette.middleware.trustedhost import TrustedHostMiddleware  # noqa: E402

from magicpay import SANDBOX_URL, MagicPay  # noqa: E402
from magicpay.errors import MagicPayAPIError, MagicPayConnectionError, MagicPayError  # noqa: E402

import sdklog  # noqa: E402

logger = logging.getLogger("magicpay_demo")

# --------------------------------------------------------------------------------------------
# Config (environment variables only)
# --------------------------------------------------------------------------------------------

API_KEY = os.environ.get("MAGICPAY_API_KEY", "").strip()
SECRET_KEY = os.environ.get("MAGICPAY_SECRET_KEY", "").strip()
BASE_URL = (os.environ.get("MAGICPAY_BASE_URL") or SANDBOX_URL).strip()
MERCHANT_NAME = (os.environ.get("MAGICPAY_MERCHANT_NAME") or "Demo Mağaza").strip()
PUBLIC_URL = (os.environ.get("DEMO_PUBLIC_URL") or "http://127.0.0.1:8000").strip().rstrip("/")


def _is_loopback_host(host: Optional[str]) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_public_host = urlsplit(PUBLIC_URL).hostname
if not _is_loopback_host(_public_host):
    # This demo holds API keys and shows the SDK log: it must never be reachable from outside.
    raise SystemExit("DEMO_PUBLIC_URL must point at a loopback address (127.0.0.1 or localhost); "
                     "this demo must not be exposed with --host 0.0.0.0 or a tunnel.")

MIN_AMOUNT = Decimal("1.00")
MAX_AMOUNT = Decimal("50000.00")
DEFAULT_AMOUNT = Decimal("1250.00")
CALLBACK_URL = "https://example.com/callback"  # the server cannot reach localhost; we confirm server-side

PRODUCT_NAME = "Bakır cezve, 2 fincanlık"
PRODUCT_TEXT = "Gaziantep'te elde dövülmüş, içi kalaylı bakır cezve. Ahşap saplı, 250 ml."
# EsnekPOS public successful test card (Halkbank Paraf, Troy); any future expiry and CVC.
TEST_CARD = {"number": "9792100000000001", "name": "Test Kart", "exp": "12/30", "cvc": "000"}

# paymentStatus values meaning "the bank has not decided yet"
PENDING_STATUSES = frozenset({"INIT_THREEDS", "CALLBACK_THREEDS", "WAITING", "OTP_WAITING"})
# paymentStatus values that end a payment as not paid
FAILED_STATUSES = frozenset({"FAILURE", "CANCEL"})

sdklog.register_secret(API_KEY)
sdklog.register_secret(SECRET_KEY)

LOG = sdklog.SdkLog()
CONFIG_ERROR: Optional[str] = None
CLIENTS: Dict[str, MagicPay] = {}

if not API_KEY or not SECRET_KEY:
    CONFIG_ERROR = ("MagicPay API anahtarı tanımlı değil. Ortam değişkenlerine MAGICPAY_API_KEY ve "
                    "MAGICPAY_SECRET_KEY ekleyip uygulamayı yeniden başlatın.")
else:
    try:
        for _version in ("V2", "V1"):
            CLIENTS[_version] = MagicPay(API_KEY, SECRET_KEY, base_url=BASE_URL, auth_version=_version,
                                         transport=sdklog.logging_transport(LOG))
    except ValueError:
        CLIENTS.clear()
        CONFIG_ERROR = ("MAGICPAY_BASE_URL geçerli bir https adresi değil. Değişkeni düzeltip "
                        "uygulamayı yeniden başlatın.")

ENV_HOST = urlsplit(BASE_URL).hostname or BASE_URL
IS_SANDBOX = BASE_URL.rstrip("/") == SANDBOX_URL
GENERIC_ERROR = ("İşlem tamamlanamadı. SDK kaydında son satırı açıp hatayı inceleyin, "
                 "ardından tekrar deneyin.")

# --------------------------------------------------------------------------------------------
# In-memory state (single-user local demo; nothing is written to disk, no card data is kept)
# --------------------------------------------------------------------------------------------

ORDERS: Dict[str, Dict[str, Any]] = {}
RETURN_TOKENS: Dict[str, str] = {}  # redirectUrl token -> order id (single use, see bank_return)
INSTALLMENT_CACHE: Dict[str, List[Dict[str, Any]]] = {}  # amount -> options, from the last lookup
FORM_NONCES: Dict[str, Optional[str]] = {}  # pay form nonce -> "" (unused), "*" (in progress) or order id
STATE_LOCK = threading.Lock()
ORDER_ID_RE = re.compile(r"^DEMO\d{14}[0-9A-F]{6}$")
MAX_NONCES = 200


class UnexpectedSdkError(MagicPayError):
    """Anything other than a MagicPayError raised while calling the SDK (already logged)."""


# --------------------------------------------------------------------------------------------
# App, security headers, CSRF guard
# --------------------------------------------------------------------------------------------

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_allowed_hosts = sorted({"127.0.0.1", "localhost", _public_host})
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
templates = Jinja2Templates(directory=str(HERE / "templates"))

PAGE_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
# The bank's auto-submitting form, served as-is. Sandboxed (opaque origin, so it cannot use our
# origin), inline onload allowed, and it may only submit/navigate the top-level page to the bank.
BANK_CSP = ("sandbox allow-scripts allow-forms allow-top-navigation; default-src 'none'; "
            "script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; "
            "frame-ancestors 'none'; base-uri 'none'; object-src 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Content-Security-Policy", PAGE_CSP)
        response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


def same_origin(request: Request, require: bool) -> bool:
    """Origin/Referer must point at this app's own host. ``require``: a missing header fails too."""
    if request.headers.get("sec-fetch-site") == "cross-site":
        return False
    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    if origin is not None:
        parts = urlsplit(origin)
        return origin != "null" and parts.scheme in ("http", "https") and parts.netloc == host
    referer = request.headers.get("referer")
    if referer:
        return urlsplit(referer).netloc == host
    return not require


FORBIDDEN_TEXT = "İstek bu uygulamanın sayfasından gelmedi. Sayfayı yenileyip işlemi oradan tekrar yapın."


def forbidden_json() -> JSONResponse:
    return JSONResponse({"message": FORBIDDEN_TEXT}, status_code=403)


def not_configured_json() -> JSONResponse:
    return JSONResponse({"message": CONFIG_ERROR}, status_code=503)


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------

def sdk(method_path: str, trigger: str, *args, version: str = "V2"):
    """Call an SDK method by its dotted name; the log records the name and the UI trigger.

    Raises only MagicPayError subclasses: anything unexpected becomes UnexpectedSdkError (logged
    without its message, which could contain response data)."""
    target: Any = CLIENTS[version]
    for part in method_path.split("."):
        target = getattr(target, part)
    token = sdklog.set_call(method_path, trigger)
    try:
        return target(*args)
    except MagicPayError:
        raise
    except Exception as exc:
        logger.error("unexpected error in %s: %s", method_path, type(exc).__name__)
        raise UnexpectedSdkError(type(exc).__name__) from None
    finally:
        sdklog.reset_call(token)


def int_param(value: Optional[str], default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(str(value)), high))
    except (TypeError, ValueError):
        return default


def q2(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt_tl(value) -> str:
    text = f"{q2(value):,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".") + " TL"


def amount_input(value: Decimal) -> str:
    """Amount as typed in the demo field: 1.250,00"""
    return fmt_tl(value)[:-3]


def parse_amount(text: Optional[str]) -> Optional[Decimal]:
    s = (text or "").strip().replace(" ", "").removesuffix("TL")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d{1,2})?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+(,\d{1,2})?", s):
        s = s.replace(",", ".")
    elif not re.fullmatch(r"\d+\.\d{1,2}", s):
        return None
    try:
        value = q2(s)
    except InvalidOperation:
        return None
    return value if MIN_AMOUNT <= value <= MAX_AMOUNT else None


AMOUNT_ERROR = f"Tutarı {fmt_tl(MIN_AMOUNT)} ile {fmt_tl(MAX_AMOUNT)} arasında girin."


def installment_label(n: int) -> str:
    return "Tek çekim" if n <= 1 else f"{n} taksit"


def installment_summary(n: int, monthly: Decimal) -> str:
    return "Tek çekim" if n <= 1 else f"{n} taksit, aylık {fmt_tl(monthly)}"


def option(n: int, monthly: Decimal, total: Decimal) -> Dict[str, Any]:
    return {"n": n, "label": installment_label(n), "monthly": str(q2(monthly)), "total": str(q2(total)),
            "monthlyText": fmt_tl(monthly), "totalText": fmt_tl(total),
            "summary": installment_summary(n, monthly),
            "payText": f"{fmt_tl(total)} öde" if n <= 1 else f"{n} taksitle {fmt_tl(total)} öde"}


def normalize_installments(result: Any, amount: Decimal) -> List[Dict[str, Any]]:
    data = sdklog.unwrap(result)
    items = data.get("installments") if isinstance(data, dict) else (data if isinstance(data, list) else None)
    options: Dict[int, Dict[str, Any]] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        try:
            n = int(item.get("installment") or item.get("installmentNumber") or 0)
            total = q2(str(item.get("totalPrice")))
            monthly = q2(str(item.get("monthlyPrice"))) if item.get("monthlyPrice") is not None else q2(total / n)
        except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
            continue
        if n >= 1 and total > 0:
            options[n] = option(n, monthly, total)
    if 1 not in options:
        options[1] = option(1, amount, amount)
    return [options[k] for k in sorted(options)]


STATUS_LABELS = {
    "SUCCESS": ("Başarılı", "onay"),
    "FAILURE": ("Başarısız", "ret"),
    "OTP_WAITING": ("3D bekleniyor", "bekleme"),
    "INIT_THREEDS": ("3D bekleniyor", "bekleme"),
    "CALLBACK_THREEDS": ("3D bekleniyor", "bekleme"),
    "WAITING": ("Banka yanıtı bekleniyor", "bekleme"),
    "REFUNDED": ("İade edildi", "notr"),
    "PARTIALLY_REFUNDED": ("Kısmen iade edildi", "notr"),
    "CANCEL": ("İptal edildi", "notr"),
}


def status_view(status: Optional[str]) -> Dict[str, str]:
    label, tone = STATUS_LABELS.get(status or "", (status or "Bilinmiyor", "soluk"))
    return {"code": status or "", "label": label, "tone": tone}


def clock(dt: datetime) -> str:
    return dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%d.%m %H:%M")


def get_order(order_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not order_id or not ORDER_ID_RE.match(order_id):
        return None
    order = ORDERS.get(order_id)
    return order if order and not order.get("placeholder") else None


def advice_for(code: Optional[str], message: Optional[str], connection: bool = False) -> str:
    if connection:
        return "MagicPay'e ulaşılamadı. Bir dakika sonra tekrar deneyin; kartınızdan para çekilmedi."
    text = (message or "").lower()
    if code in ("51", "1051") or "limit" in text or "bakiye" in text or "yetersiz" in text:
        return "Başka bir kartla ya da daha düşük tutarla tekrar deneyin."
    if code == "1042" or "3d" in text:
        return "Bankanın gönderdiği SMS kodunu doğru girdiğinizden emin olup tekrar deneyin."
    return "Kart bilgilerini kontrol edip tekrar deneyin."


def base_context(active: str) -> Dict[str, Any]:
    return {
        "merchant_name": MERCHANT_NAME,
        "env_host": ENV_HOST,
        "is_sandbox": IS_SANDBOX,
        "config_error": CONFIG_ERROR,
        "active": active,
        "log_state": LOG.snapshot(0),
    }


def render(request: Request, name: str, active: str, status_code: int = 200, **ctx) -> HTMLResponse:
    context = base_context(active)
    context.update(ctx)
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def message_page(request: Request, title: str, text: str, status_code: int) -> HTMLResponse:
    return render(request, "mesaj.html", "", status_code=status_code, page_title=f"{title} - {MERCHANT_NAME}",
                  title=title, text=text)


def is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


# --------------------------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------------------------

def new_form_nonce() -> str:
    nonce = secrets.token_urlsafe(16)
    with STATE_LOCK:
        FORM_NONCES[nonce] = ""
        while len(FORM_NONCES) > MAX_NONCES:
            FORM_NONCES.pop(next(iter(FORM_NONCES)))
    return nonce


def store_page(request: Request, amount: Decimal, installment: int = 1, values: Optional[Dict[str, str]] = None,
               errors: Optional[Dict[str, str]] = None, form_error: Optional[str] = None,
               status_code: int = 200) -> HTMLResponse:
    card = values or {"number": TEST_CARD["number"], "name": TEST_CARD["name"],
                      "exp": TEST_CARD["exp"], "cvc": TEST_CARD["cvc"]}
    digits = re.sub(r"\D", "", card.get("number", ""))
    card_display = " ".join(digits[i:i + 4] for i in range(0, len(digits), 4))
    return render(request, "magaza.html", "magaza", status_code=status_code,
                  page_title=f"Ödeme - {MERCHANT_NAME}", product_name=PRODUCT_NAME, product_text=PRODUCT_TEXT,
                  amount=str(amount), amount_text=fmt_tl(amount), amount_input=amount_input(amount),
                  default_option=option(1, amount, amount), installment=installment,
                  card_number=card_display, card_name=card.get("name", ""), card_exp=card.get("exp", ""),
                  card_cvc=card.get("cvc", ""), errors=errors or {}, form_error=form_error,
                  min_amount=str(MIN_AMOUNT), max_amount=str(MAX_AMOUNT), amount_error=AMOUNT_ERROR,
                  form_nonce=new_form_nonce())


@app.get("/", response_class=HTMLResponse)
def store(request: Request, tutar: Optional[str] = None, taksit: Optional[str] = None):
    amount = parse_amount(tutar) if tutar else None
    return store_page(request, amount or DEFAULT_AMOUNT, int_param(taksit, 1, 1, 36))


@app.get("/api/taksitler")
def api_installments(request: Request, tutar: str = "", tetikleyen: str = "acilis"):
    if not same_origin(request, require=False):
        return forbidden_json()
    if CONFIG_ERROR:
        return not_configured_json()
    amount = parse_amount(tutar)
    if amount is None:
        return JSONResponse({"message": AMOUNT_ERROR}, status_code=422)
    trigger = "Tutarı uygula" if tetikleyen == "uygula" else "Sayfa açılışı"
    try:
        result = sdk("installments.list_checkout_installments", trigger, {"amount": float(amount), "currency": "TRY"})
    except MagicPayError:
        return JSONResponse({"message": "Taksit seçenekleri alınamadı.", "amountText": fmt_tl(amount),
                             "fallback": option(1, amount, amount)}, status_code=502)
    options = normalize_installments(result, amount)
    with STATE_LOCK:
        INSTALLMENT_CACHE[str(amount)] = options
    return {"amount": str(amount), "amountText": fmt_tl(amount), "amountInput": amount_input(amount),
            "options": options}


CARD_TYPES = {"CREDIT": "kredi", "DEBIT": "banka", "PREPAID": "ön ödemeli"}
SCHEMES = {"VISA": "Visa", "MASTERCARD": "Mastercard", "MASTER_CARD": "Mastercard", "MASTER": "Mastercard",
           "TROY": "Troy", "AMEX": "Amex", "AMERICAN_EXPRESS": "Amex"}


@app.get("/api/bin")
def api_bin(request: Request, bin: str = ""):
    if not same_origin(request, require=False):
        return forbidden_json()
    if CONFIG_ERROR:
        return not_configured_json()
    if not re.fullmatch(r"\d{6}", bin):
        return JSONResponse({"message": "BIN 6 haneli olmalı."}, status_code=422)
    try:
        result = sdk("installments.retrieve_bin", "Kart numarasının ilk 6 hanesi", {"binNumber": bin})
    except MagicPayError:
        return JSONResponse({"message": "Kart bilgisi alınamadı."}, status_code=502)
    item = result[0] if isinstance(result, list) and result else sdklog.unwrap(result)
    bank = item.get("bankName") if isinstance(item, dict) else None
    if not bank:
        return {"found": False}
    raw_type = str(item.get("cardType") or "").upper()
    raw_scheme = str(item.get("cardAssociation") or "").upper()
    return {"found": True, "bank": bank, "cardType": CARD_TYPES.get(raw_type, raw_type.lower() or None),
            "scheme": SCHEMES.get(raw_scheme, raw_scheme.title() or None)}


def validate_card(number: str, name: str, exp: str, cvc: str):
    errors: Dict[str, str] = {}
    digits = re.sub(r"[\s-]", "", number)
    if not re.fullmatch(r"\d{16}", digits):
        errors["number"] = "Kart numarası 16 hane olmalı. Eksik haneleri tamamlayın."
    if not name.strip() or len(name.strip()) > 60:
        errors["name"] = "Kart üzerindeki ismi girin."
    month = year = None
    m = re.fullmatch(r"\s*(\d{2})\s*/?\s*(\d{2})\s*", exp)
    if not m or not 1 <= int(m.group(1)) <= 12:
        errors["exp"] = "Son kullanma tarihini AA/YY biçiminde girin, örneğin 12/30."
    else:
        month, year = m.group(1), "20" + m.group(2)
        now = datetime.now()
        if (int(year), int(month)) < (now.year, now.month):
            errors["exp"] = "Bu kartın süresi dolmuş. Kartın üzerindeki tarihi girin."
    if not re.fullmatch(r"\d{3}", cvc.strip()):
        errors["cvc"] = "Güvenlik kodu kartın arkasındaki 3 hanedir."
    return errors, digits, month, year


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "127.0.0.1"


def reserve_order_id() -> str:
    """A unique bankOrderId, reserved (placeholder) before the SDK call so it is never reused."""
    with STATE_LOCK:
        while True:
            order_id = "DEMO" + datetime.now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(3).upper()
            if order_id not in ORDERS:
                ORDERS[order_id] = {"id": order_id, "placeholder": True}
                return order_id


def claim_nonce(nonce: str) -> Optional[str]:
    """Mark a pay-form nonce as in progress. Returns None if claimed, else what it already maps to
    ("*" in progress, an order id, or "?" for unknown/expired)."""
    with STATE_LOCK:
        if nonce not in FORM_NONCES:
            return "?"
        current = FORM_NONCES[nonce]
        if current:
            return current
        FORM_NONCES[nonce] = "*"
        return None


@app.post("/odeme")
def pay(request: Request, card_number: str = Form(""), card_name: str = Form(""), card_exp: str = Form(""),
        card_cvc: str = Form(""), tutar: str = Form(""), taksit: str = Form("1"), banka: str = Form(""),
        form_nonce: str = Form("")):
    if not same_origin(request, require=True):
        return message_page(request, "İstek reddedildi", FORBIDDEN_TEXT, 403)
    amount = parse_amount(tutar) or DEFAULT_AMOUNT
    n = int_param(taksit, 1, 1, 36)
    values = {"number": card_number[:30], "name": card_name[:60], "exp": card_exp[:7], "cvc": ""}
    if CONFIG_ERROR:
        return store_page(request, amount, n, values, form_error=CONFIG_ERROR, status_code=503)
    if parse_amount(tutar) is None:
        return store_page(request, amount, n, values, form_error=AMOUNT_ERROR, status_code=422)
    errors, digits, month, year = validate_card(card_number, card_name, card_exp, card_cvc)
    if errors:
        return store_page(request, amount, n, values, errors=errors, status_code=422)

    # double submit guard: one payment per rendered form
    claimed = claim_nonce(form_nonce)
    if claimed == "?":
        return store_page(request, amount, n, values, status_code=409,
                          form_error="Bu ödeme formunun süresi doldu. Güvenlik kodunu yeniden girip ödemeyi tekrar başlatın.")
    if claimed == "*":
        return message_page(request, "Ödeme zaten başlatılıyor",
                            "Bu form için ödeme isteği gönderildi. Siparişler sayfasından durumu izleyin.", 409)
    if claimed:
        return RedirectResponse(f"/odeme/yonlendir?siparis={claimed}", status_code=303)

    with STATE_LOCK:
        options = INSTALLMENT_CACHE.get(str(amount)) or []
    chosen = next((o for o in options if o["n"] == n), None)
    if chosen is None:
        if n != 1:
            with STATE_LOCK:
                FORM_NONCES[form_nonce] = ""
            return store_page(request, amount, 1, values, status_code=409,
                              form_error="Seçtiğiniz taksit bu tutar için artık yok. Taksiti yeniden seçip tekrar deneyin.")
        chosen = option(1, amount, amount)
    total = Decimal(chosen["total"])

    order_id = reserve_order_id()
    token = secrets.token_urlsafe(24)
    body = {
        "price": float(amount), "paidPrice": float(total), "installment": n, "currency": "TRY",
        "paymentGroup": "PRODUCT", "paymentChannel": "Online", "clientIp": client_ip(request),
        "redirectUrl": f"{PUBLIC_URL}/odeme/donus/{token}", "callbackUrl": CALLBACK_URL,
        "bankOrderId": order_id,
        "card": {"cardHolderName": card_name.strip(), "cardNumber": digits, "expireMonth": month,
                 "expireYear": year, "cvc": card_cvc.strip()},
        "items": [{"name": PRODUCT_NAME, "price": float(amount)}],
    }
    card_masked = sdklog.mask_card(digits)
    del digits, card_cvc, card_number  # do not keep card data around longer than the call
    retry_qs = urlencode({"tutar": amount_input(amount), "taksit": n})

    def give_up():
        with STATE_LOCK:
            ORDERS.pop(order_id, None)
            FORM_NONCES.pop(form_nonce, None)

    try:
        result = sdk("payments.init_3ds_payment", "Ödeme butonu", body)
    except MagicPayConnectionError:
        give_up()
        return result_failure_page(request, total, chosen, None, None, None, retry_qs, connection=True)
    except MagicPayAPIError as exc:
        give_up()
        code, msg = sdklog.extract_error(exc.body)
        return result_failure_page(request, total, chosen, code, msg, None, retry_qs)
    except MagicPayError:
        give_up()
        return result_failure_page(request, total, chosen, None, GENERIC_ERROR, None, retry_qs)
    finally:
        body = None
    data = sdklog.unwrap(result)
    html = data.get("htmlContent") if isinstance(data, dict) else None
    payment_id = data.get("paymentId") if isinstance(data, dict) else None
    if not html or payment_id is None:
        give_up()
        return result_failure_page(request, total, chosen, None, GENERIC_ERROR, None, retry_qs)

    with STATE_LOCK:
        ORDERS[order_id] = {
            "id": order_id, "payment_id": payment_id, "token": token, "token_used": False,
            "lock": threading.Lock(), "created": datetime.now(),
            "amount": amount, "total": total, "installment": n, "monthly": Decimal(chosen["monthly"]),
            "summary": chosen["summary"], "card_masked": card_masked, "bank": banka.strip()[:60] or None,
            "status": data.get("paymentStatus") or "OTP_WAITING", "outcome": None, "html": html,
            "note": None, "refund_note": None, "refund_conversation": None,
        }
        RETURN_TOKENS[token] = order_id
        FORM_NONCES[form_nonce] = order_id
    return RedirectResponse(f"/odeme/yonlendir?siparis={order_id}", status_code=303)


@app.get("/odeme/yonlendir", response_class=HTMLResponse)
def redirect_page(request: Request, siparis: str = ""):
    order = get_order(siparis)
    if order is None:
        return message_page(request, "Sipariş bulunamadı",
                            "Bu sipariş bu oturumda oluşturulmadı. Mağazadan yeni bir ödeme başlatın.", 404)
    if order["outcome"] is not None or order["token_used"]:
        return RedirectResponse(f"/odeme/sonuc?siparis={order['id']}", status_code=303)
    return render(request, "yonlendir.html", "magaza", page_title=f"Banka doğrulaması - {MERCHANT_NAME}",
                  order=order, total_text=fmt_tl(order["total"]),
                  back_qs=urlencode({"tutar": amount_input(order["amount"]), "taksit": order["installment"]}))


@app.get("/odeme/banka/{order_id}")
def bank_page(request: Request, order_id: str):
    order = get_order(order_id)
    if order is None or not order.get("html"):
        return message_page(request, "Banka sayfası artık yok",
                            "Bu ödemenin banka adımı tamamlandı ya da sipariş bulunamadı. Siparişler sayfasından "
                            "durumu sorgulayın.", 404)
    return HTMLResponse(order["html"], headers={
        "Content-Security-Policy": BANK_CSP, "Referrer-Policy": "strict-origin-when-cross-origin"})


def set_final(order: Dict[str, Any], status: str, code: Optional[str] = None, message: Optional[str] = None) -> None:
    order["status"] = status
    order["html"] = None
    if status == "SUCCESS":
        order["outcome"] = {"state": "success"}
    else:
        order["outcome"] = {"state": "failure", "code": code, "message": message, "advice": advice_for(code, message)}


def set_pending(order: Dict[str, Any], note: Optional[str]) -> None:
    order["outcome"] = {"state": "pending", "note": note}


def complete_order(order: Dict[str, Any], trigger: str) -> None:
    """Ask MagicPay for the truth (3ds-complete). Call with order["lock"] held.

    Only an explicit SUCCESS / FAILURE / CANCEL ends the payment; everything else (pending, HTTP
    errors without a payment status, connection problems) leaves it pending for a requery."""
    try:
        result = sdk("payments.complete_3ds_payment", trigger, {"paymentId": order["payment_id"]})
    except MagicPayConnectionError:
        set_pending(order, "MagicPay'e ulaşılamadı; ödemenin sonucu henüz bilinmiyor. Bir dakika sonra durumu "
                           "sorgulayın.")
        return
    except MagicPayAPIError as exc:
        body = exc.body
        status = sdklog.payment_status_of(body)
        code, msg = sdklog.extract_error(body)
        if status in FAILED_STATUSES and not sdklog.is_pending(body):
            set_final(order, status, code, msg)
            return
        if not status and code and exc.status == 400 and not sdklog.is_pending(body):
            # A bank-side failure (e.g. 1042) may come without paymentStatus: read the stored
            # status from MagicPay instead of guessing, and end the payment only if it is final.
            try:
                status = sdklog.payment_status_of(
                    sdk("payments.retrieve_payment", trigger, order["payment_id"]))
            except MagicPayError:
                status = None
            except Exception:  # noqa: BLE001 - never a 500 page in the demo
                status = None
            if status in FAILED_STATUSES:
                set_final(order, status, code, msg)
                return
        if status:
            order["status"] = status
        if sdklog.is_pending(body) or status in PENDING_STATUSES:
            diag = body.get("paymentDiagnosis") if isinstance(body, dict) else None
            diag_msg = diag.get("message") if isinstance(diag, dict) else None
            set_pending(order, f'MagicPay\'in notu: "{diag_msg}"' if diag_msg else None)
        else:
            set_pending(order, f"MagicPay kesin bir sonuç vermedi (HTTP {exc.status}). Birkaç saniye sonra "
                               "durumu sorgulayın.")
        return
    except MagicPayError:
        set_pending(order, GENERIC_ERROR)
        return
    status = sdklog.payment_status_of(result)
    if status == "SUCCESS" or (status in FAILED_STATUSES and not sdklog.is_pending(result)):
        code, msg = sdklog.extract_error(result)
        set_final(order, status, code, msg)
    else:
        if status:
            order["status"] = status
        set_pending(order, None)


@app.api_route("/odeme/donus/{token}", methods=["GET", "POST"])
def bank_return(request: Request, token: str):
    # The bank's ?status=... is only a hint; the answer of 3ds-complete is what counts.
    order_id = RETURN_TOKENS.get(token) if re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token) else None
    order = get_order(order_id)
    if order is None:
        return message_page(request, "Ödeme bulunamadı",
                            "Bu dönüş adresi bu sunucunun başlattığı bir ödemeye ait değil. Mağazadan yeni "
                            "bir ödeme başlatın.", 404)
    result_url = f"/odeme/sonuc?siparis={order['id']}"
    with order["lock"]:
        # single use: a refresh or a second concurrent return only goes to the result page
        if order["token_used"]:
            return RedirectResponse(result_url, status_code=303)
        order["token_used"] = True
        order["html"] = None  # the bank step is over; drop the bank form (it carries the card number)
        if CONFIG_ERROR:
            return message_page(request, "Ödeme doğrulanamadı", CONFIG_ERROR, 503)
        complete_order(order, "Bankadan dönüş")
    return RedirectResponse(result_url, status_code=303)


def result_failure_page(request: Request, total: Decimal, chosen: Dict[str, Any], code: Optional[str],
                        message: Optional[str], order_id: Optional[str], retry_qs: str,
                        connection: bool = False) -> HTMLResponse:
    return render(request, "sonuc.html", "magaza", page_title=f"Ödeme alınamadı - {MERCHANT_NAME}",
                  state="failure", product_name=PRODUCT_NAME, total_text=fmt_tl(total), summary=chosen["summary"],
                  payment_id=None, order_id=order_id, status=status_view("FAILURE"),
                  code=code, message=message, advice=advice_for(code, message, connection),
                  connection=connection, retry_qs=retry_qs, pending_note=None)


@app.get("/odeme/sonuc", response_class=HTMLResponse)
def result_page(request: Request, siparis: str = ""):
    order = get_order(siparis)
    if order is None:
        return message_page(request, "Sipariş bulunamadı",
                            "Bu sipariş bu oturumda oluşturulmadı. Mağazadan yeni bir ödeme başlatın.", 404)
    outcome = order["outcome"]
    if outcome is None:
        if not order["token_used"]:
            return RedirectResponse(f"/odeme/yonlendir?siparis={order['id']}", status_code=303)
        outcome = {"state": "pending", "note": None}  # another request is completing it right now
    state = outcome["state"]
    titles = {"success": "Ödeme alındı", "failure": "Ödeme alınamadı", "pending": "Ödeme onayı bekleniyor"}
    retry_qs = urlencode({"tutar": amount_input(order["amount"]), "taksit": order["installment"]})
    return render(request, "sonuc.html", "magaza", page_title=f"{titles[state]} - {MERCHANT_NAME}",
                  state=state, product_name=PRODUCT_NAME, total_text=fmt_tl(order["total"]),
                  summary=order["summary"], payment_id=order["payment_id"], order_id=order["id"],
                  status=status_view(order["status"]), code=outcome.get("code"), message=outcome.get("message"),
                  advice=outcome.get("advice"), connection=False, retry_qs=retry_qs,
                  pending_note=outcome.get("note") if state == "pending" else None)


@app.post("/odeme/sonuc/sorgula")
def result_requery(request: Request, siparis: str = Form("")):
    if not same_origin(request, require=True):
        return message_page(request, "İstek reddedildi", FORBIDDEN_TEXT, 403)
    order = get_order(siparis)
    if order is None:
        return message_page(request, "Sipariş bulunamadı",
                            "Bu sipariş bu oturumda oluşturulmadı. Mağazadan yeni bir ödeme başlatın.", 404)
    if CONFIG_ERROR:
        return message_page(request, "Durum sorgulanamadı", CONFIG_ERROR, 503)
    with order["lock"]:
        outcome = order["outcome"]
        if outcome is None or outcome["state"] == "pending":  # final outcomes are never re-queried
            order["token_used"] = True
            order["html"] = None
            complete_order(order, "Durumu sorgula")
    return RedirectResponse(f"/odeme/sonuc?siparis={order['id']}", status_code=303)


# --------------------------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------------------------

def order_row(order: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": order["id"], "paymentId": order["payment_id"], "time": clock(order["created"]),
            "totalText": fmt_tl(order["total"]), "status": status_view(order["status"]),
            "refundable": order["status"] == "SUCCESS", "note": order["note"], "refundNote": order["refund_note"]}


@app.get("/siparisler", response_class=HTMLResponse)
def orders_page(request: Request):
    with STATE_LOCK:
        rows = [order_row(o) for o in reversed(list(ORDERS.values())) if not o.get("placeholder")]
    return render(request, "siparisler.html", "siparisler", page_title=f"Siparişler - {MERCHANT_NAME}", rows=rows)


@app.post("/api/siparisler/{order_id}/sorgula")
def api_order_query(request: Request, order_id: str):
    if not same_origin(request, require=True):
        return forbidden_json()
    if CONFIG_ERROR:
        return not_configured_json()
    order = get_order(order_id)
    if order is None:
        return JSONResponse({"message": "Sipariş bulunamadı."}, status_code=404)
    with order["lock"]:
        try:
            result = sdk("payments.retrieve_payment", "Durumu sorgula", order["payment_id"])
        except MagicPayAPIError as exc:
            if sdklog.payment_status_of(exc.body):  # e.g. a declined payment reported with an errors object
                result = exc.body
            else:
                code, msg = sdklog.extract_error(exc.body)
                text = (f'Durum alınamadı: "{msg}"' + (f" (kod {code})." if code else ".")) if msg else GENERIC_ERROR
                return JSONResponse({"message": text}, status_code=502)
        except MagicPayError:
            return JSONResponse({"message": GENERIC_ERROR}, status_code=502)
        now = datetime.now().strftime("%H:%M")
        new_status = sdklog.payment_status_of(result) or order["status"]
        if new_status == order["status"]:
            order["note"] = f"Son sorgu {now}: durum aynı."
        else:
            order["note"] = f'Son sorgu {now}: durum "{status_view(new_status)["label"]}" olarak güncellendi.'
        # keep the result page in step with what MagicPay now says
        if new_status == "SUCCESS" or (new_status in FAILED_STATUSES and order["status"] != "SUCCESS"):
            code, msg = sdklog.extract_error(result)
            set_final(order, new_status, code, msg)
        else:
            order["status"] = new_status
        return order_row(order)


def _refund_id(result: Any) -> Optional[str]:
    for obj in (result, sdklog.unwrap(result)):
        if isinstance(obj, dict):
            for key in ("refundId", "refund_id", "id", "paymentRefundId"):
                if obj.get(key) not in (None, ""):
                    return str(obj[key])
    return None


@app.post("/api/siparisler/{order_id}/iade")
def api_order_refund(request: Request, order_id: str):
    if not same_origin(request, require=True):
        return forbidden_json()
    if CONFIG_ERROR:
        return not_configured_json()
    order = get_order(order_id)
    if order is None:
        return JSONResponse({"message": "Sipariş bulunamadı."}, status_code=404)
    with order["lock"]:
        if order["status"] != "SUCCESS":
            return JSONResponse({"message": "Yalnızca başarılı ödemeler iade edilebilir. Durumu sorgulayıp tekrar "
                                            "deneyin."}, status_code=409)
        if not order["refund_conversation"]:  # stable per order, so a retry is the same refund
            order["refund_conversation"] = f"demo-refund-{order['payment_id']}-{secrets.token_hex(6)}"
        body = {"paymentId": order["payment_id"], "conversationId": order["refund_conversation"],
                "refundDestinationType": "PROVIDER"}
        try:
            result = sdk("payments.refund_payment", "İadeyi onayla", body)
        except MagicPayConnectionError:
            return JSONResponse({"message": "İade yapılamadı: MagicPay'e ulaşılamadı. Durumu sorgulayıp tekrar "
                                            "deneyin."}, status_code=502)
        except MagicPayAPIError as exc:
            code, msg = sdklog.extract_error(exc.body)
            msg = msg or "Banka bir açıklama göndermedi."
            text = f'İade yapılamadı: "{msg}"' + (f" (kod {code})" if code else "") + ". Durumu sorgulayıp tekrar deneyin."
            return JSONResponse({"message": text}, status_code=422)
        except MagicPayError:
            return JSONResponse({"message": GENERIC_ERROR}, status_code=502)
        data = sdklog.unwrap(result)
        message = str(data.get("message") or "") if isinstance(data, dict) else ""
        cancelled = "cancel" in message.lower()
        order["status"] = "CANCEL" if cancelled else "REFUNDED"
        refund_id = _refund_id(result)
        notes = []
        if refund_id:
            notes.append(f"İade no {refund_id}")
        if cancelled:
            notes.append("Ödeme gün sonundan önce iade edildiği için iptal olarak işlendi.")
        order["refund_note"] = ". ".join(notes) if notes else None
        return order_row(order)


# --------------------------------------------------------------------------------------------
# Connection check
# --------------------------------------------------------------------------------------------

TEST_BIN = TEST_CARD["number"][:6]
CHECKS = [
    {"id": "taksit", "label": "Taksit seçenekleri", "method": "installments.list_checkout_installments",
     "args": [{"amount": 100, "currency": "TRY"}], "v1": True},
    {"id": "bin", "label": "BIN sorgusu", "method": "installments.retrieve_bin",
     "args": [{"binNumber": TEST_BIN}], "v1": True},
    {"id": "bin-banka", "label": "Kart bankası sorgusu (imza gerekmez)", "method": "installments.check_bin",
     "args": [TEST_BIN], "v1": True},
    {"id": "pos", "label": "POS kimlikleri", "method": "pos.list_pos_ids", "args": [], "v1": True},
    {"id": "link-taksit", "label": "Ödeme linki taksitleri", "method": "magic_links.list_available_installments",
     "args": [], "v1": True},
    {"id": "anahtar", "label": "API anahtarları", "method": "api_keys.list_api_credentials", "args": [], "v1": True},
    {"id": "uye", "label": "Üyeler", "method": "api_members.list_members", "args": [{"page": 1, "size": 5}],
     "v1": True},
    {"id": "eklenti-banka", "label": "Eklenti bankaları", "method": "plugin.list_banks", "args": [], "v1": False},
    {"id": "eklenti-pos", "label": "Eklenti POS listesi", "method": "plugin.list_poses", "args": [], "v1": False},
]
CHECKS_BY_ID = {c["id"]: c for c in CHECKS}


@app.get("/baglanti", response_class=HTMLResponse)
def connection_page(request: Request):
    total = sum(2 if c["v1"] else 1 for c in CHECKS)
    return render(request, "baglanti.html", "baglanti", page_title=f"Bağlantı kontrolü - {MERCHANT_NAME}",
                  checks=CHECKS, total_checks=total)


@app.post("/api/baglanti/kontrol")
async def api_connection_check(request: Request):
    if not same_origin(request, require=True):
        return forbidden_json()
    if CONFIG_ERROR:
        return not_configured_json()
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"message": "Geçersiz istek."}, status_code=422)
    check = CHECKS_BY_ID.get(str(payload.get("check")))
    version = payload.get("version")
    if check is None or version not in ("V2", "V1") or (version == "V1" and not check["v1"]):
        return JSONResponse({"message": "Geçersiz kontrol."}, status_code=422)
    return await run_in_threadpool(_run_check, check, version)


def _run_check(check: Dict[str, Any], version: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        sdk(check["method"], "Bağlantı kontrolü", *check["args"], version=version)
    except MagicPayAPIError as exc:
        ms = round((time.perf_counter() - t0) * 1000)
        code, msg = sdklog.extract_error(exc.body)
        detail = f"HTTP {exc.status}" + (f", kod {code}" if code else "") + (f": {msg}" if msg else ".")
        return {"ok": False, "ms": ms, "detail": sdklog.scrub_text(detail)[:300]}
    except MagicPayConnectionError:
        return {"ok": False, "ms": round((time.perf_counter() - t0) * 1000), "detail": "MagicPay'e ulaşılamadı."}
    except MagicPayError:
        return {"ok": False, "ms": round((time.perf_counter() - t0) * 1000), "detail": GENERIC_ERROR}
    return {"ok": True, "ms": round((time.perf_counter() - t0) * 1000)}


# --------------------------------------------------------------------------------------------
# Log
# --------------------------------------------------------------------------------------------

@app.get("/api/log")
def api_log(request: Request, after: Optional[str] = None):
    if not same_origin(request, require=False):
        return forbidden_json()
    return LOG.snapshot(int_param(after, 0, 0, 10 ** 12))


@app.post("/api/log/temizle")
def api_log_clear(request: Request):
    if not same_origin(request, require=True):
        return forbidden_json()
    LOG.clear()
    return LOG.snapshot(0)


# --------------------------------------------------------------------------------------------
# Errors: never a raw framework page
# --------------------------------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        if is_api(request):
            return JSONResponse({"message": "Bulunamadı."}, status_code=404)
        return message_page(request, "Sayfa bulunamadı", "Bu adreste bir sayfa yok. Üstteki menüden devam edin.", 404)
    if is_api(request):
        return JSONResponse({"message": "İstek işlenemedi."}, status_code=exc.status_code)
    return message_page(request, "İstek işlenemedi", "Bu istek bu sayfada kullanılamıyor. Üstteki menüden "
                                                    "devam edin.", exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if is_api(request):
        return JSONResponse({"message": "Geçersiz istek."}, status_code=422)
    return message_page(request, "Geçersiz istek", "Adresteki ya da formdaki bir değer okunamadı. Mağazadan "
                                                  "yeniden başlayın.", 400)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.error("unhandled error on %s: %s", request.url.path, type(exc).__name__)
    if is_api(request):
        return JSONResponse({"message": GENERIC_ERROR}, status_code=500)
    return message_page(request, "İşlem tamamlanamadı", GENERIC_ERROR, 500)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
