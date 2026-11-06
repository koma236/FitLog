"""Serial image measurement and separately isolated authentication burst."""
import hashlib
import json
import time
import uuid
from functools import partial

from perf import fixtures as f
from perf.client import Session
from perf.images import image_fixture, pixels
from perf.report import summarize
from perf.runner import bounded_jobs, observed


def image_job(events):
    try:
        sessions = [Session() for _ in range(5)]
        for actor, session in enumerate(sessions):
            observed(events, 0, lambda actor=actor, session=session: session.login(actor))
        fixtures = [(size, *image_fixture(size)) for size in (147, 590, 1320)]
        start = time.monotonic()
        for _ in range(2):
            for actor, session in enumerate(sessions):
                for size, raw, digest in fixtures:
                    if time.monotonic() - start > 120:
                        raise TimeoutError("image budget")
                    boundary = "fitlog-perf-fixed-boundary"
                    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="fixture.png"\r\n'
                            'Content-Type: image/png\r\n\r\n').encode() + raw + f"\r\n--{boundary}--\r\n".encode()
                    headers = {"X-Record-Owner": str(f.user_id(actor)), "X-Image-Operation": str(uuid.uuid4()),
                               "Content-Type": "multipart/form-data; boundary=" + boundary}
                    status, response, elapsed = observed(events, 0, partial(session.request,
                        "PUT", f"/api/posts/{f.post_id(actor)}/image", body, headers))
                    value = json.loads(response)
                    image = value.get("image") or {}
                    valid = (status == 200 and value.get("viewer_id") == str(f.user_id(actor))
                             and image.get("width") == size and image.get("height") == size
                             and image.get("content_type") == "image/png")
                    row = {"actor": actor, "route": f"image-{size}", "method": "PUT", "status": status,
                           "elapsed_ms": elapsed, "input_bytes": len(raw), "width": size, "height": size,
                           "input_sha256": hashlib.sha256(raw).hexdigest(), "error": None if valid else "content"}
                    events.put({"event": "end", "actor": 0, "row": row})
                    if not valid:
                        raise ValueError("image upload failed")
                    status, response, elapsed = observed(events, 0, partial(session.request, "GET", image["url"]))
                    width, height, rgb = pixels(response)
                    valid = status == 200 and (width, height) == (size, size) and hashlib.sha256(rgb).hexdigest() == digest
                    events.put({"event": "end", "actor": 0, "row": {
                        "actor": actor, "route": f"image-{size}", "method": "GET", "status": status,
                        "elapsed_ms": elapsed, "output_bytes": len(response), "error": None if valid else "content"}})
                    if not valid:
                        raise ValueError("image download mismatch")
        events.put({"event": "done", "actor": 0})
    except Exception:
        events.put({"event": "error", "actor": 0, "error": "image_failed"})


def auth_job(events):
    try:
        # Start near the beginning of a fixed UTC minute, without resetting counters.
        within = time.time() % 60
        if within > 10:
            time.sleep(62 - within)
        epoch = int(time.time() // 60)
        start = time.monotonic()
        for attempt in range(11):
            session = Session()
            session.csrf = observed(events, 0, partial(session.json, "GET", "/api/auth/csrf"))["csrf_token"]
            actor = attempt % 5
            status, _, elapsed = observed(events, 0, partial(session.request, "POST", "/api/auth/login", {
                "email": f"{f.username(actor)}@fitlog-perf.invalid", "password": f.PASSWORD}))
            expected = 200 if attempt < 10 else 429
            retry = session.last_headers.get("Retry-After", "")
            valid = (status == expected and int(time.time() // 60) == epoch
                     and time.monotonic() - start <= 20
                     and (attempt < 10 or retry.isdigit() and 1 <= int(retry) <= 60))
            events.put({"event": "end", "actor": 0, "row": {
                "actor": actor, "route": "auth-burst", "method": "POST", "status": status,
                "elapsed_ms": elapsed, "expected_status": expected, "error": None if valid else "contract"}})
        events.put({"event": "done", "actor": 0})
    except Exception:
        events.put({"event": "error", "actor": 0, "error": "auth_failed"})


def run_special(mode):
    result = bounded_jobs(image_job if mode == "image" else auth_job, [()], total=160)
    if mode == "image":
        summary = summarize(result["rows"], 60, minimum=1, latency_gate=False,
                            required={f"image-{s} {m}" for s in (147, 590, 1320) for m in ("PUT", "GET")})
    else:
        rows = result["rows"]
        summary = {"status": "pass" if len(rows) == 11 and all(not r["error"] for r in rows) else "fail",
                   "planned": 11, "completed": len(rows), "expected_429_count": sum(r["status"] == 429 for r in rows)}
    if result["errors"] or not result["workers_stopped"]:
        summary["status"] = "fail"
    return {**result, "summary": summary}
