"""Five persistent actor processes with a parent-enforced whole-request deadline."""
import contextlib
import json
import multiprocessing
import queue
import signal
import threading
import time
import urllib.error
from urllib.parse import urlencode

from perf import fixtures as f
from perf.client import Session
from perf.report import summarize

REQUIRED = {"all GET", "following GET", "detail GET", "user GET", "search GET",
            "update PUT", "like POST", "like DELETE"}


@contextlib.contextmanager
def cleanup_signals():
    """Defer repeated host interrupts until ownership has a known final state."""
    deferred, handlers = [], {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, lambda number, frame: deferred.append(number))
    try:
        yield deferred
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def bounded_jobs(target, arguments, *, deadline=5, total=1800):
    events, workers = None, []
    active, done, errors, rows = {}, set(), [], []
    began = time.monotonic()
    try:
        context = multiprocessing.get_context("spawn")
        events = context.Queue()
        for args in arguments:
            worker = context.Process(target=target, args=(events, *args))
            workers.append(worker)  # Track before start, including a partially started process.
            # spawn creates the OS child before Process._popen becomes visible. Do not
            # interrupt that registration window and then infer absence from pid=None.
            with cleanup_signals() as starting_signals:
                worker.start()
            if starting_signals:
                raise KeyboardInterrupt("interrupt during worker registration")
        while len(done) < len(workers):
            try:
                event = events.get(timeout=.02)
            except queue.Empty:
                event = None
            if event:
                actor = event["actor"]
                if event["event"] == "start":
                    active[actor] = event
                elif event["event"] == "end":
                    active.pop(actor, None)
                    if "row" in event:
                        rows.append(event["row"])
                elif event["event"] == "done":
                    active.pop(actor, None)
                    done.add(actor)
                elif event["event"] == "error":
                    errors.append(event["error"])
                    break
            now = time.monotonic()
            expired = [event for event in active.values() if now - event["at"] > deadline]
            if expired:
                for event in expired:
                    if event.get("measured"):
                        rows.append({"actor": event["actor"], "route": event["route"],
                                     "method": event["method"], "status": 0,
                                     "elapsed_ms": (now - event["at"]) * 1000, "error": "timeout"})
                errors.append("request_deadline")
                break
            if now - began > total:
                errors.append("run_deadline")
                break
            if any(p.exitcode not in {None, 0} for p in workers):
                errors.append("worker_exit")
                break
            # A worker that exits without a final event must not leave the parent waiting forever.
            if all(not p.is_alive() for p in workers) and not event:
                errors.append("missing_worker_completion")
                break
    except BaseException as error:
        errors.append("worker_start_or_run_" + type(error).__name__)
    finally:
        stopped = True
        with cleanup_signals() as deferred:
            for worker in workers:
                try:
                    if worker.pid is None:
                        # start() may have created a child before raising. Without a
                        # registered handle there is no evidence that it has stopped.
                        stopped = False
                    else:
                        if worker.is_alive():
                            worker.terminate()
                        worker.join(timeout=2)
                        if worker.is_alive():
                            worker.kill()
                            worker.join(timeout=2)
                        stopped = stopped and not worker.is_alive()
                except BaseException:
                    stopped = False  # Continue attempting the other workers; never infer success.
            if events is not None:
                try:
                    events.close()
                    events.join_thread()
                except BaseException:
                    stopped = False
        if deferred:
            errors.append("interrupt_during_worker_cleanup")
        if not stopped:
            errors.append("worker_cleanup_unconfirmed")
    return {"rows": rows, "errors": errors, "workers_stopped": stopped}


def observed(events, actor, operation):
    events.put({"event": "start", "actor": actor, "at": time.monotonic()})
    try:
        return operation()
    finally:
        events.put({"event": "end", "actor": actor})


class Actor:
    def __init__(self, actor, scenario):
        self.actor, self.scenario = actor, scenario
        self.session = Session()
        self.cursor = {}
        self.liked = False

    def operation(self, slot, events=None, measured=False):
        actor = self.actor
        headers = {}
        body = None
        page = 0
        method = "GET"
        index = actor  # actor-specific post; no other worker mutates it.
        if slot in {0, 1, 2, 3}:
            route = "all" if slot < 2 else "following"
            page = slot % 2
            query = {"limit": "20"}
            if page:
                query["cursor"] = self.cursor[route]
            path = f"/api/timeline/{route}?{urlencode(query)}"
        elif slot in {4, 5}:
            route, path = "detail", f"/api/posts/{f.post_id(index)}"
        elif slot == 6:
            route, path = "user", f"/api/users/{f.username(actor)}/posts?limit=20"
        elif slot == 7:
            route, path = "search", "/api/users/search?q=perf_member&limit=20"
        elif slot == 8:
            route, method, path = "update", "PUT", f"/api/posts/{f.post_id(index)}"
            body = f.payload(self.scenario)
            headers = {"X-Record-Owner": str(f.user_id(actor))}
        else:
            route, method, path = "like", "DELETE" if self.liked else "POST", f"/api/posts/{f.post_id(index)}/like"
            body, headers = b"", {"X-Social-Owner": str(f.user_id(actor))}
        start = time.monotonic()
        if events is not None:
            events.put({"event": "start", "actor": actor, "at": start,
                        "route": route, "method": method, "measured": measured})
        status, error = 0, None
        elapsed = None
        try:
            status, raw, elapsed = self.session.request(method, path, body, headers)
            if status != 200:
                error = "http"
            else:
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("response must be an object")
                if route in {"all", "following", "user"}:
                    f.check_listing(value, actor, route, page, self.scenario)
                    if route != "user" and not page:
                        self.cursor[route] = value["next_cursor"]
                elif route in {"detail", "update"}:
                    f.check_post(value, index, actor, self.scenario, self.liked)
                elif route == "search":
                    f.check_search(value, actor)
                else:
                    enabled = method == "POST"
                    if (value.get("viewer_id") != str(f.user_id(actor))
                            or value.get("post_id") != str(f.post_id(index))
                            or value.get("is_liked") is not enabled
                            or value.get("like_count") != (3 if enabled else 2)):
                        raise ValueError("like content mismatch")
                    self.liked = enabled
        except (ValueError, KeyError, TypeError):
            error = "content"
        except (OSError, urllib.error.URLError):
            error = "transport"
        return {"actor": actor, "route": route, "method": method, "status": status,
                "elapsed_ms": elapsed if elapsed is not None else (time.monotonic() - start) * 1000,
                "error": error}


def actor_job(events, actor, scenario, mode, epoch):
    try:
        client = Actor(actor, scenario)
        observed(events, actor, lambda: client.session.login(actor))
        smoke_start = time.monotonic()
        # Smoke ends in the documented unliked state (POST followed by DELETE).
        for slot in [*range(10), 9]:
            row = observed(events, actor, lambda slot=slot: client.operation(slot))
            if row["error"] or time.monotonic() - smoke_start > 30:
                raise ValueError("smoke_failed")
            if mode == "smoke":
                events.put({"event": "end", "actor": actor, "row": row})
        if mode == "load":
            if time.monotonic() >= epoch:
                raise ValueError("setup_deadline")
            # 30 warmup slots followed by exactly 300 measured slots.
            for frame in range(330):
                scheduled = epoch + frame
                delay = scheduled - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -1:
                    continue  # Explicitly missing from the planned denominator; never caught up.
                row = observed(events, actor, lambda frame=frame: client.operation(frame % 10, events, frame >= 30))
                if frame >= 30:
                    events.put({"event": "end", "actor": actor, "row": row})
        events.put({"event": "done", "actor": actor})
    except Exception:
        # Never emit exception text: it may contain URLs, cookies or response content.
        events.put({"event": "error", "actor": actor, "error": "actor_failed"})
        return


def run_load(scenario, mode="load"):
    epoch = time.monotonic() + 25
    result = bounded_jobs(actor_job, [(a, scenario, mode, epoch) for a in range(5)], total=370)
    summary = summarize(result["rows"], 1500 if mode == "load" else 55,
                        required=REQUIRED, minimum=50 if mode == "load" else 1,
                        latency_gate=mode == "load")
    if result["errors"] or not result["workers_stopped"]:
        summary["status"] = "fail"
    return {**result, "summary": summary}
