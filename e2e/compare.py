#!/usr/bin/env python3
"""Check that all SDKs produced the same request for every scenario, and re-verify each
SDK's signature with the server's algorithm.

Compared across SDKs: method, URL (host/path/query; Rust is recorded over http://), JSON body,
and the x-* / authorization headers except the per-request values x-rnd-key, x-timestamp and
x-signature. Those are instead checked per record: x-signature must equal the V2 HMAC computed
from the recorded method, https:// URL, exact body bytes and recorded x-timestamp / x-rnd-key
(or the V1 hash when x-auth-version is V1).
"""
import hashlib
import hmac
import json
import os
import sys
import time
from urllib.parse import urlsplit

E2E = os.path.dirname(os.path.abspath(__file__))
API_KEY, SECRET = os.environ["MAGICPAY_API_KEY"], os.environ["MAGICPAY_SECRET_KEY"]
SDKS = ["python", "dotnet", "rust", "php"]
VOLATILE = {"x-rnd-key", "x-timestamp", "x-signature"}
EXPECTED_VERSION = os.environ.get("MAGICPAY_AUTH_VERSION", "V2")


def load(sdk):
    with open(os.path.join(E2E, "out", f"{sdk}.jsonl"), encoding="utf-8") as f:
        return {r["name"]: r for r in map(json.loads, f)}


def https(u):
    """The server verifies the https:// form of the URL."""
    return "https://" + u[len("http://"):] if u.startswith("http://") else u


def norm_url(u):
    s = urlsplit(u)
    return s.netloc + s.path + ("?" + s.query if s.query else "")


def norm_body(b):
    return json.loads(b) if b else None


def lower(headers):
    return {k.lower(): v for k, v in headers.items()}


def compared_headers(headers):
    return {k: v for k, v in lower(headers).items()
            if (k.startswith("x-") or k == "authorization") and k not in VOLATILE}


def expected_signature(r, h):
    url = https(r["url"])
    if h.get("x-auth-version") == "V1":
        return hashlib.sha256((url + API_KEY + SECRET + h["x-rnd-key"]).encode("utf-8")).hexdigest()
    body = (r["body"] or "").encode("utf-8")
    message = "\n".join((r["method"].upper(), url, hashlib.sha256(body).hexdigest(),
                         API_KEY, h["x-timestamp"], h["x-rnd-key"]))
    return hmac.new(SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


data = {s: load(s) for s in SDKS}
problems = 0
rnd_seen = set()


def problem(msg):
    global problems
    problems += 1
    print(msg)


for name in data["python"]:
    ref = data["python"][name]
    for sdk in SDKS[1:]:
        r = data[sdk].get(name)
        if not r:
            problem(f"MISSING {sdk} {name}")
            continue
        for field, fn in (("method", str), ("url", norm_url), ("body", norm_body), ("headers", compared_headers)):
            if fn(r[field]) != fn(ref[field]):
                problem(f"DIFF {name} {field}: python={fn(ref[field])!r} {sdk}={fn(r[field])!r}")
    for sdk in SDKS:
        r = data[sdk].get(name)
        if not r:
            continue
        h = lower(r["headers"])
        if h.get("x-api-key") != API_KEY or h.get("x-auth-version") != EXPECTED_VERSION:
            problem(f"BAD AUTH HEADERS {sdk} {name}: version={h.get('x-auth-version')!r}")
            continue
        if EXPECTED_VERSION == "V2":
            ts = h.get("x-timestamp", "")
            if not ts.isdigit() or abs(int(ts) - time.time()) > 3600:
                problem(f"BAD x-timestamp {sdk} {name}: {ts!r}")
                continue
        if not h.get("x-rnd-key") or h["x-rnd-key"] in rnd_seen:
            problem(f"MISSING/REUSED x-rnd-key {sdk} {name}")
        rnd_seen.add(h.get("x-rnd-key"))
        if h.get("x-signature") != expected_signature(r, h):
            problem(f"BAD SIGNATURE {sdk} {name}")
        if r["body"] and "application/json" not in h.get("content-type", ""):
            problem(f"MISSING JSON CONTENT-TYPE {sdk} {name}")
print(f"{len(data['python'])} scenarios x {len(SDKS)} SDKs ({EXPECTED_VERSION}) — {problems} problem(s)")
sys.exit(1 if problems else 0)
