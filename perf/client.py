"""Local-only HTTP clients. No retries, shared cookies, proxy or redirects."""
import http.cookiejar
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18080"
MAX_BODY = 16 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Session:
    def __init__(self, base=BASE):
        if base != BASE:
            raise ValueError("only fixed loopback API permitted")
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                                 urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None
        self.last_headers = {}

    def request(self, method, path, body=None, headers=None):
        if not path.startswith("/api/") and path not in {"/redirect", "/cookie", "/echo", "/drip"}:
            raise ValueError("invalid local API path")
        if "\\" in path or "\r" in path or "\n" in path:
            raise ValueError("invalid local API path")
        extra = {"Origin": self.base, **(headers or {})}
        if self.csrf:
            extra["X-CSRFToken"] = self.csrf
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
            extra["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=extra)
        start = time.monotonic()
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.last_headers = dict(response.headers)
            raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ValueError("response body cap exceeded")
            return response.code, raw, (time.monotonic() - start) * 1000

    def json(self, method, path, body=None, headers=None):
        status, raw, _ = self.request(method, path, body, headers)
        if status != 200:
            raise ValueError(f"unexpected HTTP status {status}")
        return json.loads(raw)

    def login(self, actor):
        from perf import fixtures as f

        self.csrf = self.json("GET", "/api/auth/csrf")["csrf_token"]
        data = self.json("POST", "/api/auth/login", {
            "email": f"{f.username(actor)}@fitlog-perf.invalid", "password": f.PASSWORD})
        if data.get("id") != str(f.user_id(actor)):
            raise ValueError("login actor mismatch")
        self.csrf = self.json("GET", "/api/auth/csrf")["csrf_token"]
        if self.json("GET", "/api/auth/me").get("id") != str(f.user_id(actor)):
            raise ValueError("session actor mismatch")
