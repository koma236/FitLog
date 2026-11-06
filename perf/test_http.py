import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from perf.client import Session
from perf.runner import bounded_jobs


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.invalid")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if self.path == "/cookie":
            self.send_header("Set-Cookie", "member=one; Path=/")
        self.end_headers()
        if self.path == "/drip":
            try:
                for _ in range(100):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(.05)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.wfile.write(json.dumps({"cookie": self.headers.get("Cookie", "")}).encode())


def drip_job(queue, base):
    queue.put({"event": "start", "actor": 0, "at": time.monotonic()})
    Session(base).request("GET", "/drip")


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 18080), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        from perf.runtime import ensure_port_free
        ensure_port_free()

    def test_redirect_never_followed(self):
        status, _, _ = Session().request("GET", "/redirect")
        self.assertEqual(status, 302)

    def test_cookie_jars_are_isolated(self):
        first, second = Session(), Session()
        first.request("GET", "/cookie")
        self.assertEqual(first.json("GET", "/echo")["cookie"], "member=one")
        self.assertEqual(second.json("GET", "/echo")["cookie"], "")

    def test_external_or_relative_escape_rejected(self):
        for base in ("https://example.invalid", "http://127.0.0.1:9999"):
            with self.assertRaises(ValueError):
                Session(base)
        for path in ("https://example.invalid", "//example.invalid", "/\\evil"):
            with self.assertRaises(ValueError):
                Session().request("GET", path)

    def test_slow_body_cannot_outlive_whole_request_deadline(self):
        start = time.monotonic()
        result = bounded_jobs(drip_job, [("http://127.0.0.1:18080",)], deadline=.3, total=3)
        self.assertEqual(result["errors"], ["request_deadline"])
        self.assertLess(time.monotonic() - start, 2)
        self.assertTrue(result["workers_stopped"])
