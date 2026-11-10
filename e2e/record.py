#!/usr/bin/env python3
"""Record the signed requests every SDK produces for scenarios.json (no network to MagicPay needed).

    python3 e2e/record.py            # php, composer, dotnet and cargo on PATH
    python3 e2e/record.py --docker   # run the PHP/.NET/Rust recorders in Docker instead

Credentials come only from the environment (MAGICPAY_API_KEY / MAGICPAY_SECRET_KEY); they are
passed to containers by name (`docker run -e NAME`), never on the command line.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

E2E = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(E2E)
OUT = os.path.join(E2E, "out")
os.makedirs(OUT, exist_ok=True)
for k in ("MAGICPAY_API_KEY", "MAGICPAY_SECRET_KEY"):
    if not os.environ.get(k):
        sys.exit(f"{k} is not set")
DOCKER = "--docker" in sys.argv[1:] or os.environ.get("MAGICPAY_E2E_DOCKER") == "1"
SANDBOX_URL = "https://trdev.magicpay.ai"
BASE = os.environ.get("MAGICPAY_BASE_URL") or SANDBOX_URL
env = dict(os.environ, DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1", MAGICPAY_BASE_URL=BASE)


def run(cmd, cwd=ROOT, extra=None):
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, env=dict(env, **(extra or {})), check=True)


def docker(image, workdir, command, volumes=(), extra_env=None):
    """Run `command` (sh -c) in `image` with the repo mounted at /w."""
    extra_env = extra_env or {}
    cmd = ["docker", "run", "--rm", "-v", f"{ROOT}:/w", "-w", workdir]
    for v in volumes:
        cmd += ["-v", v]
    for name in ["MAGICPAY_API_KEY", "MAGICPAY_SECRET_KEY", "MAGICPAY_BASE_URL",
                 "DOTNET_NOLOGO", "DOTNET_CLI_TELEMETRY_OPTOUT"] + list(extra_env):
        cmd += ["-e", name]  # value is taken from the environment, not the command line
    cmd += [image, "sh", "-c", command]
    run(cmd, extra=dict(extra_env, MSYS_NO_PATHCONV="1"))


# Python
run([sys.executable, os.path.join(E2E, "record_python.py")])

# PHP
if DOCKER:
    docker("composer:2", "/w/php", "composer dump-autoload -q && php /w/e2e/record_php.php")
else:
    run(["composer", "dump-autoload", "-q"], cwd=os.path.join(ROOT, "php"))
    run(["php", os.path.join(E2E, "record_php.php")])

# .NET
if DOCKER:
    docker("mcr.microsoft.com/dotnet/sdk:8.0", "/w/e2e/dotnet",
           "dotnet run --project . -p:TargetFrameworks=net8.0",
           volumes=["magicpay-nuget:/root/.nuget/packages"])
else:
    run(["dotnet", "run", "--project", os.path.join(E2E, "dotnet"), "-p:TargetFrameworks=net8.0"] +
        (["--no-restore"] if os.environ.get("DOTNET_NO_RESTORE") else []))

# Rust: local recording proxy; the SDK is pointed at the http:// form of the base URL through it
# (it must still sign the https:// form, which compare.py checks).
records = []
names = json.load(open(os.path.join(E2E, "scenarios.json"), encoding="utf-8"))


class Proxy(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else None
        records.append({"method": self.command, "url": self.path,
                        "headers": {k: v for k, v in self.headers.items()}, "body": body})
        payload = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

    def log_message(self, *a):
        pass


srv = HTTPServer(("0.0.0.0" if DOCKER else "127.0.0.1", 0), Proxy)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
rust_env = {"MAGICPAY_RECORD_PROXY": f"http://{'host.docker.internal' if DOCKER else '127.0.0.1'}:{port}",
            "SCENARIOS": "/w/e2e/scenarios.json" if DOCKER else os.path.join(E2E, "scenarios.json"),
            "MAGICPAY_RUST_BASE_URL": "http://" + BASE.split("://", 1)[1],
            "NO_PROXY": "", "no_proxy": "", "HTTP_PROXY": "", "http_proxy": ""}
try:
    if DOCKER:
        docker("rust:1.82", "/w/rust", "cargo run -q --example e2e_record",
               volumes=["magicpay-cargo-registry:/usr/local/cargo/registry", "magicpay-rust-target:/w/rust/target"],
               extra_env=rust_env)
    else:
        run(["cargo", "run", "-q", "--example", "e2e_record"], cwd=os.path.join(ROOT, "rust"), extra=rust_env)
finally:
    srv.shutdown()
assert len(records) == len(names), (len(records), len(names))
with open(os.path.join(OUT, "rust.jsonl"), "w", encoding="utf-8") as f:
    for sc, rec in zip(names, records):
        rec["name"] = sc["name"]
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print("rust:", len(records), "requests recorded")
