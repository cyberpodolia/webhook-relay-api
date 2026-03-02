import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import count

MODE = os.getenv("RECEIVER_MODE", "fast").strip().lower()
PORT = int(os.getenv("RECEIVER_PORT", "8080"))
SLOW_MS = int(os.getenv("RECEIVER_SLOW_MS", "1200"))
FAIL_EVERY = max(1, int(os.getenv("RECEIVER_FAIL_EVERY", "4")))

_counter = count(1)
_lock = threading.Lock()
_metrics = {"requests_total": 0, "requests_failed_total": 0}


class ReceiverHandler(BaseHTTPRequestHandler):
    server_version = "PerfReceiver/1.0"

    def _json_response(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, failed: bool) -> None:
        with _lock:
            _metrics["requests_total"] += 1
            if failed:
                _metrics["requests_failed_total"] += 1

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json_response(200, {"status": "ok", "mode": MODE})
            return
        if self.path == "/metrics":
            with _lock:
                req_total = _metrics["requests_total"]
                req_failed = _metrics["requests_failed_total"]
            payload = (
                "# TYPE receiver_requests_total counter\n"
                f'receiver_requests_total{{mode="{MODE}"}} {req_total}\n'
                "# TYPE receiver_requests_failed_total counter\n"
                f'receiver_requests_failed_total{{mode="{MODE}"}} {req_failed}\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._json_response(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/ingest":
            self._json_response(404, {"error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        req_num = next(_counter)

        if MODE == "slow":
            time.sleep(SLOW_MS / 1000.0)

        should_fail = MODE == "flaky" and req_num % FAIL_EVERY == 0
        if should_fail:
            self._record(failed=True)
            self._json_response(
                503,
                {
                    "status": "error",
                    "mode": MODE,
                    "request_number": req_num,
                    "message": "deterministic failure",
                },
            )
            return

        self._record(failed=False)
        self._json_response(
            200,
            {
                "status": "ok",
                "mode": MODE,
                "request_number": req_num,
                "bytes": len(body),
            },
        )

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), ReceiverHandler)
    print(f"receiver listening on {PORT} mode={MODE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
