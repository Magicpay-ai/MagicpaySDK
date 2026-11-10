"""Live test of the Python SDK against the MagicPay test environment (trdev).

Keys come from environment variables, never from this file:

    MAGICPAY_API_KEY, MAGICPAY_SECRET_KEY   test (trdev) API key pair from the merchant panel
    MAGICPAY_BASE_URL                       optional, default https://trdev.magicpay.ai

Commands:

    python examples/live_test.py smoke            read-only calls with V2 and V1 signatures
    python examples/live_test.py pay [amount]     start a 3D payment, open the bank page in the browser
    python examples/live_test.py status [id]      retrieve the payment
    python examples/live_test.py complete [id]    3ds-complete
    python examples/live_test.py refund [id]      refund the whole payment

Without an id the last payment started with `pay` is used. The card is EsnekPOS's public
successful test card; on the EsnekPOS test page the approval password is already filled in
(123456): just press ONAYLA. Pressing VAZGEÇ, or changing the password, gives a failed payment.
"""
import json
import os
import pathlib
import sys
import time
import webbrowser

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

from magicpay import MagicPay, SANDBOX_URL  # noqa: E402
from magicpay.errors import MagicPayError  # noqa: E402

LAST = HERE / ".last_payment"
PAGE = HERE / "3ds.html"
TEST_CARD = {  # EsnekPOS public test card (Halkbank Paraf, Troy); any expiry and CVV
    "cardHolderName": "Test Kart",
    "cardNumber": "9792100000000001",
    "expireMonth": "12",
    "expireYear": "2030",
    "cvc": "000",
}


def client(auth_version="V2"):
    key, secret = os.environ.get("MAGICPAY_API_KEY"), os.environ.get("MAGICPAY_SECRET_KEY")
    if not key or not secret:
        sys.exit("Set MAGICPAY_API_KEY and MAGICPAY_SECRET_KEY (test keys) first.")
    return MagicPay(key, secret, base_url=os.environ.get("MAGICPAY_BASE_URL", SANDBOX_URL),
                    auth_version=auth_version)


def show(label, fn, *args):
    try:
        result = fn(*args)
        print(f"OK    {label}")
        return result, True
    except MagicPayError as e:
        body = json.dumps(getattr(e, "body", None), ensure_ascii=False)[:400]
        print(f"FAIL  {label}: HTTP {getattr(e, 'status', '')} {getattr(e, 'error_code', '')} {body}")
        return None, False


def payment_id(args):
    if args:
        return int(args[0])
    if not LAST.exists():
        sys.exit("No payment id given and no previous `pay` run.")
    return int(LAST.read_text())


def smoke():
    failed = 0
    for version in ("V2", "V1"):
        mp = client(version)
        for label, fn, args in (
            ("list_checkout_installments", mp.installments.list_checkout_installments, ({"amount": 100, "currency": "TRY"},)),
            ("retrieve_bin", mp.installments.retrieve_bin, ({"binNumber": "540667"},)),
            ("check_bin", mp.installments.check_bin, ("540667",)),
            ("list_pos_ids", mp.pos.list_pos_ids, ()),
            ("list_available_installments", mp.magic_links.list_available_installments, ()),
            ("list_api_credentials", mp.api_keys.list_api_credentials, ()),
            ("list_members", mp.api_members.list_members, ({"page": 1, "size": 5},)),
        ):
            failed += not show(f"{version} {label}", fn, *args)[1]
    mp = client("V2")
    failed += not show("V2 plugin.list_banks", mp.plugin.list_banks)[1]
    failed += not show("V2 plugin.list_poses", mp.plugin.list_poses)[1]
    print("all passed" if not failed else f"{failed} failed")
    return 1 if failed else 0


def pay(args):
    amount = float(args[0]) if args else 10.0
    order = f"SDKTEST{int(time.time())}"
    result, ok = show("init_3ds_payment", client().payments.init_3ds_payment, {
        "price": amount, "paidPrice": amount, "installment": 1, "currency": "TRY",
        "paymentGroup": "PRODUCT", "paymentChannel": "Online", "clientIp": "85.105.1.1",
        "redirectUrl": "https://example.com/return", "callbackUrl": "https://example.com/callback",
        "bankOrderId": order, "card": TEST_CARD,
        "items": [{"name": "Test item", "price": amount}],
    })
    if not ok:
        return 1
    data = result.get("data", result)
    LAST.write_text(str(data["paymentId"]))
    PAGE.write_text(data["htmlContent"], encoding="utf-8")
    print(f"order {order}, paymentId {data['paymentId']}, status {data.get('paymentStatus')}")
    print("Bank page opened in the browser: press ONAYLA (password is prefilled).")
    print("You land on example.com/return?status=...; then run `complete`.")
    webbrowser.open(PAGE.as_uri())
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    if cmd == "smoke":
        return smoke()
    if cmd == "pay":
        return pay(args)
    mp = client()
    if cmd == "status":
        result, ok = show("retrieve_payment", mp.payments.retrieve_payment, payment_id(args))
    elif cmd == "complete":
        result, ok = show("complete_3ds_payment", mp.payments.complete_3ds_payment, {"paymentId": payment_id(args)})
    elif cmd == "refund":
        pid = payment_id(args)
        result, ok = show("refund_payment", mp.payments.refund_payment, {
            "paymentId": pid, "conversationId": f"refund-{pid}-{int(time.time())}",
            "refundDestinationType": "PROVIDER"})
    else:
        print(__doc__)
        return 1
    if ok:
        data = result.get("data", result) if isinstance(result, dict) else result
        status = data.get("paymentStatus") or data.get("status") if isinstance(data, dict) else None
        print(f"paymentStatus: {status}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
