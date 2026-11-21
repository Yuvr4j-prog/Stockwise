"""Run a signup → upload → forecast → optimize → CSV export smoke test."""
from __future__ import annotations

import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta


class SmokeStepFailure(RuntimeError):
    pass


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/smoke_remote.py https://your-app.example.com")
        return 2
    base = sys.argv[1].rstrip("/")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def step(label: str, action):
        try:
            result = action()
        except Exception as exc:
            print(f"FAIL {label}: {exc}", file=sys.stderr)
            raise SmokeStepFailure from exc
        print(f"PASS {label}")
        return result

    def request(path: str, *, method: str = "GET", body: bytes | None = None,
                content_type: str = "application/json", headers: dict[str, str] | None = None,
                timeout: int = 25) -> tuple[int, bytes]:
        request_headers = {"Content-Type": content_type, **(headers or {})}
        req = urllib.request.Request(base + path, data=body, method=method, headers=request_headers)
        try:
            with opener.open(req, timeout=timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} returned {exc.code}: {detail}") from exc

    def wait_for_health(path: str) -> None:
            deadline = time.monotonic() + 90
            delay = 1
            last_problem = "no response"
            while time.monotonic() < deadline:
                try:
                    status, payload = request(path, timeout=8)
                    data = json.loads(payload)
                    if status == 200 and data.get("status") == "ok":
                        return
                    last_problem = f"HTTP {status}: {data}"
                except Exception as exc:
                    last_problem = str(exc)
                time.sleep(min(delay, max(0, deadline - time.monotonic())))
                delay = min(delay * 2, 15)
            raise RuntimeError(f"health did not recover within 90 seconds: {last_problem}")

    def signup() -> str:
        _, payload = request("/api/v1/auth/csrf")
        csrf_token = json.loads(payload)["csrf_token"]
        _, payload = request("/api/v1/auth/signup", method="POST",
                             body=json.dumps({"email": f"smoke-{int(time.time())}@example.com",
                                              "password": "Stockwise-smoke-51"}).encode(),
                             headers={"X-CSRF-Token": csrf_token})
        assert json.loads(payload)["id"]
        session_cookie = next((cookie for cookie in jar if cookie.name == "stockwise_session"), None)
        assert session_cookie is not None and session_cookie.has_nonstandard_attr("HttpOnly")
        return csrf_token

    weeks = [date.today() - timedelta(days=date.today().weekday()) - timedelta(weeks=offset)
             for offset in reversed(range(4))]
    labels = [f"{week.isocalendar().year}-W{week.isocalendar().week:02d}" for week in weeks]
    csv = ("sku,name,cost_price,profit_per_unit," + ",".join(labels) + "\n"
           "SMOKE-1,Smoke test rice,100,25,3,4,5,6\n").encode()
    boundary = "----StockWiseSmokeBoundary"
    multipart = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"smoke.csv\"\r\n"
                 f"Content-Type: text/csv\r\n\r\n").encode() + csv + f"\r\n--{boundary}--\r\n".encode()
    csrf = ""
    plan = {}

    try:
        step("process health check", lambda: wait_for_health("/api/v1/health"))
        step("database health check", lambda: wait_for_health("/api/v1/health/db"))
        csrf = step("signup and same-origin session cookie", signup)

        def preview_upload():
            _, payload = request("/api/v1/uploads/preview", method="POST", body=multipart,
                                 content_type=f"multipart/form-data; boundary={boundary}",
                                 headers={"X-CSRF-Token": csrf})
            assert json.loads(payload)["summary"]["sales_rows"] == 4
        step("upload preview", preview_upload)

        def commit_upload():
            _, payload = request("/api/v1/uploads/commit", method="POST", body=multipart,
                                 content_type=f"multipart/form-data; boundary={boundary}",
                                 headers={"X-CSRF-Token": csrf})
            assert json.loads(payload)["summary"]["product_rows"] == 1
        step("upload commit", commit_upload)

        def make_forecast():
            _, payload = request("/api/v1/forecasts?method=auto&window=3&alpha=0.4")
            result = next(row for row in json.loads(payload) if row["sku"] == "SMOKE-1")
            assert result["forecast"] > 0 and len(result["history"]) == 4
            return result
        step("forecast from uploaded history", make_forecast)

        def optimize():
            _, payload = request("/api/v1/plans/optimize", method="POST",
                                 body=json.dumps({"budget": 800, "risk_mode": "balanced", "storage_limit": 8,
                                                  "forecast_method": "auto", "window": 3, "alpha": 0.4}).encode(),
                                 headers={"X-CSRF-Token": csrf})
            result = json.loads(payload)
            assert result["id"] and float(result["total_spent"]) <= 800
            return result
        plan = step("plan optimization", optimize)

        def export_plan():
            _, payload = request(f"/api/v1/plans/{plan['id']}/export.csv")
            assert payload.startswith(b"sku,quantity,spend,expected_profit,reason")
        step("saved-plan CSV export", export_plan)
    except SmokeStepFailure:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
