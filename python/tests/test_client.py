import hashlib
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from magicpay import (
    PRODUCTION_URL,
    SANDBOX_URL,
    MagicPay,
    MagicPayAPIError,
    compute_signature,
    compute_signature_v2,
)

# Shared cross-SDK test vectors (see ../../README.md)
V1_URL = "https://trdev.magicpay.ai/payment/v1/card-payments/1086?page=1&size=10"
V1_SIG = "a0a1b034e46f3690306e10ad629a72f0a5c7687068b0be53239d1feb6cf824c5"
V2_URL = "https://trdev.magicpay.ai/payment/v1/card-payments/3ds-complete"
V2_BODY = b'{"paymentId":123}'
V2_SIG = "ece3b0b7830f3b720257c097c2a6cc4d2dafc81cb937af758231c8fedb16b495"
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

LOGIN_OK = '{"data":{"merchantId":7,"status":"Success","token":{"accessToken":"jwt-login","expiresIn":3600}}}'
LOGIN_BAD = '{"errors":{"errorCode":"7005","errorDescription":"E-posta adresi ya da şifre hatalı"}}'


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses) or [(200, '{"data": {"id": 1}}')]
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body))
        return self.responses[min(len(self.calls), len(self.responses)) - 1]


def v2_expected(method, url, headers, body, key="k", secret="s"):
    return compute_signature_v2(method, url, body, key, secret, headers["x-timestamp"], headers["x-rnd-key"])


class SignatureTest(unittest.TestCase):
    def test_v1_vector(self):
        self.assertEqual(compute_signature(V1_URL, "test-api-key", "test-secret-key", "abc123"), V1_SIG)

    def test_v2_vector(self):
        sig = compute_signature_v2("POST", V2_URL, V2_BODY, "test-api-key", "test-secret-key", "1700000000", "abc123")
        self.assertEqual(sig, V2_SIG)
        # method is upper-cased and str bodies are UTF-8 encoded
        self.assertEqual(
            compute_signature_v2("post", V2_URL, V2_BODY.decode(), "test-api-key", "test-secret-key", "1700000000", "abc123"),
            V2_SIG,
        )

    def test_v2_empty_body_hash(self):
        self.assertEqual(hashlib.sha256(b"").hexdigest(), EMPTY_SHA)
        a = compute_signature_v2("GET", V1_URL, None, "k", "s", "1", "r")
        self.assertEqual(a, compute_signature_v2("GET", V1_URL, b"", "k", "s", "1", "r"))


class ClientTest(unittest.TestCase):
    def test_environment_urls(self):
        self.assertEqual(SANDBOX_URL, "https://trdev.magicpay.ai")
        self.assertEqual(PRODUCTION_URL, "https://tr.magicpay.ai")

    def test_v2_headers_by_default(self):
        t = Recorder()
        mp = MagicPay("k", "s", transport=t)
        res = mp.wallets.search_wallet_transactions(42, query={"page": 1, "size": 10, "x": None})
        self.assertEqual(res, {"data": {"id": 1}})
        method, url, headers, body = t.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "https://trdev.magicpay.ai/wallet/v1/wallets/42/wallet-transactions?page=1&size=10")
        self.assertIsNone(body)
        self.assertEqual(headers["x-api-key"], "k")
        self.assertEqual(headers["x-auth-version"], "V2")
        self.assertLessEqual(abs(int(headers["x-timestamp"]) - time.time()), 5)
        self.assertGreaterEqual(len(headers["x-rnd-key"]), 16)
        self.assertEqual(headers["x-signature"], v2_expected("GET", url, headers, b""))

    def test_rnd_key_changes_per_request(self):
        t = Recorder()
        mp = MagicPay("k", "s", transport=t)
        mp.payments.retrieve_payment(1)
        mp.payments.retrieve_payment(1)
        self.assertNotEqual(t.calls[0][2]["x-rnd-key"], t.calls[1][2]["x-rnd-key"])

    def test_v2_body_hash_uses_sent_bytes(self):
        t = Recorder()
        mp = MagicPay("k", "s", base_url="https://api.example.com/", transport=t)
        mp.payments.complete_3ds_payment({"paymentId": 123, "note": "ürün"})
        method, url, headers, body = t.calls[0]
        self.assertEqual((method, url), ("POST", "https://api.example.com/payment/v1/card-payments/3ds-complete"))
        self.assertEqual(body, '{"paymentId":123,"note":"ürün"}'.encode("utf-8"))
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["x-signature"], v2_expected("POST", url, headers, body))

    def test_http_base_url_is_signed_as_https(self):
        t = Recorder()
        MagicPay("k", "s", base_url="http://127.0.0.1:8080", transport=t).payments.retrieve_payment(5)
        method, url, headers, body = t.calls[0]
        self.assertEqual(url, "http://127.0.0.1:8080/payment/v1/card-payments/5")
        self.assertEqual(headers["x-signature"], v2_expected("GET", "https://127.0.0.1:8080/payment/v1/card-payments/5", headers, None))

    def test_v1_option(self):
        t = Recorder()
        mp = MagicPay("k", "s", transport=t, auth_version="V1")
        mp.payments.retrieve_payment(1086)
        method, url, headers, body = t.calls[0]
        self.assertEqual(headers["x-auth-version"], "V1")
        self.assertNotIn("x-timestamp", headers)
        self.assertEqual(headers["x-signature"], compute_signature(url, "k", "s", headers["x-rnd-key"]))
        with self.assertRaises(ValueError):
            MagicPay("k", "s", auth_version="V3")
        with self.assertRaises(ValueError):
            MagicPay("k", "s", signature_encoding="base64")  # base64 is V1-only
        MagicPay("k", "s", auth_version="V1", signature_encoding="base64")

    def test_post_without_body_and_array_response(self):
        t = Recorder((200, "{}"), (200, '["CREDIT_CARD", "Visa", "Garanti BBVA", "Bonus", "Credit"]'))
        mp = MagicPay("k", "s", transport=t)
        mp.payments.refresh_payguru_payment(77)
        method, url, headers, body = t.calls[0]
        self.assertEqual((method, url), ("POST", "https://trdev.magicpay.ai/payment/v1/payguru/payments/77/refresh"))
        self.assertIsNone(body)
        self.assertNotIn("Content-Type", headers)
        self.assertEqual(headers["x-signature"], v2_expected("POST", url, headers, b""))
        self.assertEqual(mp.installments.check_bin("435508")[2], "Garanti BBVA")
        self.assertTrue(t.calls[1][1].endswith("/payment/v1/card-payments/bank-name/435508"))

    def test_multi_path_params(self):
        t = Recorder()
        MagicPay("k", "s", transport=t).pos.change_pos_status(7, "PASSIVE")
        self.assertTrue(t.calls[0][1].endswith("/merchant/v1/merchant-poses/7/status/PASSIVE"))
        self.assertEqual(t.calls[0][0], "PUT")

    def test_bearer_token(self):
        t = Recorder()
        mp = MagicPay("k", "s", transport=t, access_token="jwt-1")
        mp.pos.list_pos()
        self.assertEqual(t.calls[0][2]["Authorization"], "Bearer jwt-1")
        mp.access_token = None
        mp.pos.list_pos()
        self.assertNotIn("Authorization", t.calls[1][2])

    def test_login_stores_token(self):
        t = Recorder((200, LOGIN_OK), (200, '{"data": []}'))
        mp = MagicPay("k", "s", transport=t)
        res = mp.login("user@example.com", "pw")
        self.assertEqual(res["data"]["merchantId"], 7)
        self.assertEqual(mp.access_token, "jwt-login")
        method, url, headers, body = t.calls[0]
        self.assertEqual((method, url), ("POST", "https://trdev.magicpay.ai/merchant/v1/authenticate"))
        self.assertEqual(json.loads(body), {"email": "user@example.com", "secretWord": "pw"})
        self.assertNotIn("Authorization", headers)
        mp.pos.list_pos(query={"isActivePos": "PASSIVE"})
        self.assertEqual(t.calls[1][2]["Authorization"], "Bearer jwt-login")
        self.assertTrue(t.calls[1][1].endswith("/merchant/v1/merchant-poses/?isActivePos=PASSIVE"))

    def test_login_errors_body_raises(self):
        t = Recorder((200, LOGIN_BAD))
        mp = MagicPay("k", "s", transport=t)
        with self.assertRaises(MagicPayAPIError) as cm:
            mp.login("user@example.com", "wrong")
        self.assertEqual(cm.exception.status, 200)
        self.assertEqual(cm.exception.error_code, "7005")
        self.assertIn("7005", str(cm.exception))
        self.assertIsNone(mp.access_token)

    def test_installments_use_query(self):
        t = Recorder()
        MagicPay("k", "s", transport=t).installments.retrieve_bin(query={"binNumber": "540667"})
        self.assertTrue(t.calls[0][1].endswith("/installment/v1/bins/?binNumber=540667"))

    def test_base_url_must_be_https(self):
        for bad in ("http://trdev.magicpay.ai", "ftp://x", "trdev.magicpay.ai"):
            with self.assertRaises(ValueError):
                MagicPay("k", "s", base_url=bad)
        for ok in ("http://127.0.0.1:1", "http://localhost", "http://[::1]:8080", PRODUCTION_URL):
            MagicPay("k", "s", base_url=ok)
        MagicPay("k", "s", base_url="http://trdev.magicpay.ai", allow_insecure=True)

    def test_path_params_reject_dot_segments(self):
        mp = MagicPay("k", "s", transport=Recorder())
        for bad in ("", ".", ".."):
            with self.assertRaises(ValueError):
                mp.payments.retrieve_payment(bad)
        mp.payments.retrieve_payment("a b/..")  # encoded as one segment
        self.assertTrue(mp._transport.calls[0][1].endswith("/card-payments/a%20b%2F.."))

    def test_redirect_status_is_an_error_and_token_is_redacted(self):
        t = Recorder((302, LOGIN_OK))
        mp = MagicPay("k", "s", transport=t)
        with self.assertRaises(MagicPayAPIError) as cm:
            mp.login("user@example.com", "pw")
        self.assertEqual(cm.exception.status, 302)
        self.assertNotIn("jwt-login", str(cm.exception))
        self.assertNotIn("jwt-login", cm.exception.raw)
        self.assertEqual(cm.exception.body["data"]["token"]["accessToken"], "***")
        self.assertIsNone(mp.access_token)

    def test_default_transport_does_not_follow_redirects(self):
        hits = []

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:9/elsewhere")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            mp = MagicPay("k", "s", base_url=f"http://127.0.0.1:{srv.server_address[1]}")
            with self.assertRaises(MagicPayAPIError) as cm:
                mp.payments.retrieve_payment(1)
            self.assertEqual(cm.exception.status, 302)
            self.assertEqual(hits, ["/payment/v1/card-payments/1"])
        finally:
            srv.shutdown()

    def test_error(self):
        t = Recorder((400, '{"message": "invalid card"}'))
        with self.assertRaises(MagicPayAPIError) as cm:
            MagicPay("k", "s", transport=t).payments.retrieve_payment(1)
        self.assertEqual(cm.exception.status, 400)
        self.assertIn("invalid card", str(cm.exception))

    def test_error_detail_errors(self):
        t = Recorder((400, '{"detail": {"errors": {"errorCode": "2006", "errorDescription": "bad signature"}}}'))
        with self.assertRaises(MagicPayAPIError) as cm:
            MagicPay("k", "s", transport=t).payments.retrieve_payment(1)
        self.assertEqual(cm.exception.error_code, "2006")
        self.assertIn("bad signature", str(cm.exception))

    def test_empty_errors_object_is_not_an_error(self):
        t = Recorder((200, '{"data": {"id": 1}, "errors": null}'), (200, '{"errors": {}}'))
        mp = MagicPay("k", "s", transport=t)
        self.assertEqual(mp.payments.retrieve_payment(1)["data"]["id"], 1)
        self.assertEqual(mp.payments.retrieve_payment(1), {"errors": {}})


if __name__ == "__main__":
    unittest.main()
