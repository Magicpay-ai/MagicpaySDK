import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from magicpay import SANDBOX_URL, MagicPay  # noqa: E402

API_KEY, SECRET = os.environ["MAGICPAY_API_KEY"], os.environ["MAGICPAY_SECRET_KEY"]
BASE = os.environ.get("MAGICPAY_BASE_URL") or SANDBOX_URL
scenarios = json.load(open(os.path.join(os.path.dirname(__file__), "scenarios.json"), encoding="utf-8"))
out = open(os.path.join(os.path.dirname(__file__), "out", "python.jsonl"), "w", encoding="utf-8")

records = []
def transport(method, url, headers, body, timeout):
    records.append({"method": method, "url": url, "headers": headers, "body": body.decode("utf-8") if body else None})
    return 200, "{}"

mp = MagicPay(API_KEY, SECRET, base_url=BASE, transport=transport)
for sc in scenarios:
    kwargs = {}
    if "body" in sc:
        kwargs["body"] = sc["body"]
    if "query" in sc:
        kwargs["query"] = sc["query"]
    getattr(getattr(mp, sc["resource"]), sc["method"])(*sc["args"], **kwargs)
    rec = records.pop()
    rec["name"] = sc["name"]
    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
print("python:", len(scenarios), "requests recorded")
