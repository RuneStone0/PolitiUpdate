"""One-time OAuth 2.0 PKCE authorization to obtain X API tokens.

Starts a local HTTPS server to catch the callback automatically — no copy-paste needed.

Usage:
    python -m src.bot.auth
"""

import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

import tweepy

from .config import X_CLIENT_ID, X_CLIENT_SECRET, X_REDIRECT_URI, X_TOKEN_FILE

SCOPES = [
    "tweet.read",
    "tweet.write",
    "users.read",
    "offline.access",
    # Needed by src/followers: X API v2's GET /2/users/:id/followers only
    # accepts OAuth 2.0 (App-only or user-context) — OAuth 1.0a is rejected
    # with a 401 regardless of API access tier. follows.write isn't strictly
    # required (follow/unfollow also work over OAuth 1.0a) but is requested
    # so the followers app can run entirely on this one OAuth 2.0 token.
    "follows.read",
    "follows.write",
]


def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


def _generate_self_signed_cert(host: str) -> tuple[str, str]:
    out_dir = tempfile.mkdtemp(prefix="pu_auth_")
    key_path = os.path.join(out_dir, "key.pem")
    cert_path = os.path.join(out_dir, "cert.pem")

    is_ip = all(p.isdigit() for p in host.split("."))
    san_type = "IP" if is_ip else "DNS"

    subprocess.run(
        [
            "openssl", "req", "-new", "-x509",
            "-keyout", key_path, "-out", cert_path,
            "-days", "1", "-nodes",
            "-subj", f"/CN={host}",
            "-addext", f"subjectAltName={san_type}:{host}",
        ],
        check=True,
        capture_output=True,
    )
    return cert_path, key_path


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        self.server.auth_code = params.get("code", [None])[0]
        self.server.auth_state = params.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<html><body><h1>Authorization complete</h1><p>You can close this window.</p></body></html>")

    def log_message(self, format, *args):
        pass


def main() -> None:
    if not X_CLIENT_ID or not X_CLIENT_SECRET:
        print("Error: Set X_CLIENT_ID and X_CLIENT_SECRET in .env first.")
        print("  Go to https://developer.x.com/en/portal → your App → Keys and tokens")
        sys.exit(1)

    parsed = urlparse(X_REDIRECT_URI)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5000

    oauth2 = tweepy.OAuth2UserHandler(
        client_id=X_CLIENT_ID,
        client_secret=X_CLIENT_SECRET,
        redirect_uri=X_REDIRECT_URI,
        scope=SCOPES,
    )

    auth_url = oauth2.get_authorization_url()

    cert_path, key_path = _generate_self_signed_cert(host)

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(cert_path, key_path)
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    server = HTTPServer((host, port), _CallbackHandler)
    server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
    server.timeout = 120
    server.auth_code = None
    server.auth_state = None

    print(f"\nStarting HTTPS server on {host}:{port} ...")
    print(f"Opening browser for authorization...")
    print(f"\nIf your browser warns about the certificate, click Advanced → Proceed.\n")
    webbrowser.open(auth_url)

    print("Waiting for authorization (Ctrl+C to cancel)...")
    try:
        while server.auth_code is None:
            server.handle_request()
    except KeyboardInterrupt:
        print("\nCancelled.")
        server.server_close()
        sys.exit(0)

    server.server_close()
    print("Authorization code received.")

    redirect_url = f"{X_REDIRECT_URI}?code={server.auth_code}&state={server.auth_state}"

    try:
        tokens = oauth2.fetch_token(redirect_url)
    except Exception as e:
        print(f"Error fetching tokens: {e}")
        sys.exit(1)

    token_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": tokens.get("expires_in", 7200),
        "obtained_at": int(time.time()),
        "scope": tokens.get("scope", " ".join(SCOPES)),
    }

    Path(X_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(X_TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nTokens saved to {X_TOKEN_FILE}")
    print("Your bot can now post to X using OAuth 2.0.")
    print()
    print("For Docker/Portainer deployment, add this env var:")
    print(f"  X_REFRESH_TOKEN={tokens['refresh_token']}")


if __name__ == "__main__":
    main()
