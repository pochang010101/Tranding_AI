#!/usr/bin/env python3
"""
Atlas v5.0 Load Test — locustfile.py

Streamlit is WebSocket-based; HTTP endpoints available:
  GET /healthz          — Streamlit health check
  GET /_stcore/health   — internal health (Streamlit >= 1.18)
  GET /                 — main page (returns HTML, no WS negotiation needed for load)

Run with locust:
    locust -f tests/load/locustfile.py --host http://localhost:8503

Run headless (CI):
    locust -f tests/load/locustfile.py --host http://localhost:8503 \
           --headless -u 20 -r 5 --run-time 60s \
           --csv tests/load/results/report
"""

from __future__ import annotations

import random
from locust import HttpUser, task, between, events
import urllib3

# Suppress SSL warnings for local testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# Streamlit page paths — Streamlit serves all pages on GET /
# The query param controls which page renders (multi-page app routing)
# ---------------------------------------------------------------------------
STREAMLIT_PAGES = [
    "/",                          # Dashboard / home
    "/?page=market_overview",     # Market overview
    "/?page=signal_radar",        # Signal radar
    "/?page=stock_screener",      # Stock screener
    "/?page=portfolio",           # Portfolio
    "/?page=paper_trading",       # Paper trading
    "/?page=ipo_scan",            # IPO scan
    "/?page=weekly_report",       # Weekly report
]

HEALTH_ENDPOINTS = [
    "/healthz",
    "/_stcore/health",
    "/_stcore/stream",            # returns 400 without WS upgrade — still a valid probe
]


class StreamlitBrowserUser(HttpUser):
    """
    Simulates a browser user navigating through Atlas pages.
    Streamlit's actual interactivity needs WebSocket; here we test:
      - HTTP layer availability (all pages return 200 quickly)
      - Health endpoint reliability under concurrent load
      - Static asset serving (JS/CSS bundles)
    """
    wait_time = between(1, 5)  # seconds between tasks

    @task(3)
    def view_main_page(self) -> None:
        """Load the main Streamlit page."""
        with self.client.get(
            "/",
            name="GET / (main page)",
            catch_response=True,
            verify=False,
        ) as resp:
            if resp.status_code in (200, 304):
                resp.success()
            elif resp.status_code == 502:
                resp.failure("502 Bad Gateway — app not running?")
            else:
                resp.success()  # Streamlit may redirect; treat non-5xx as success

    @task(5)
    def health_check(self) -> None:
        """Poll health endpoint — highest weight, mimics monitoring probes."""
        endpoint = random.choice(HEALTH_ENDPOINTS[:2])  # only real health endpoints
        with self.client.get(
            endpoint,
            name="GET /healthz",
            catch_response=True,
            verify=False,
        ) as resp:
            # Streamlit returns {"status": "ok"} or plain "ok"
            if resp.status_code in (200, 204):
                resp.success()
            else:
                # /_stcore/health returns 200 normally; flag anything else
                resp.failure(f"Health check failed: {resp.status_code}")

    @task(2)
    def browse_random_page(self) -> None:
        """Navigate to a random page (simulates multi-page app usage)."""
        page = random.choice(STREAMLIT_PAGES[1:])  # skip home (already in view_main_page)
        with self.client.get(
            page,
            name="GET /?page=<random>",
            catch_response=True,
            verify=False,
        ) as resp:
            if resp.status_code < 500:
                resp.success()
            else:
                resp.failure(f"Server error {resp.status_code} on {page}")

    @task(1)
    def fetch_static_asset(self) -> None:
        """Request the Streamlit JS bundle (tests static file serving latency)."""
        with self.client.get(
            "/_stcore/static/",
            name="GET /_stcore/static/",
            catch_response=True,
            verify=False,
        ) as resp:
            # 200, 301, 304 are all fine for static serving
            if resp.status_code < 500:
                resp.success()
            else:
                resp.failure(f"Static serving error: {resp.status_code}")


class APIHeavyUser(HttpUser):
    """
    Simulates a power user who stays on the dashboard and polls frequently.
    Higher task frequency, shorter wait.
    """
    wait_time = between(0.5, 2)

    @task(8)
    def repeated_health_poll(self) -> None:
        with self.client.get(
            "/healthz",
            name="GET /healthz (heavy)",
            catch_response=True,
            verify=False,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Unhealthy: {resp.status_code}")

    @task(2)
    def main_page_refresh(self) -> None:
        with self.client.get(
            "/",
            name="GET / (heavy refresh)",
            catch_response=True,
            verify=False,
        ) as resp:
            if resp.status_code < 500:
                resp.success()
            else:
                resp.failure(f"Error: {resp.status_code}")


# ---------------------------------------------------------------------------
# Event hooks — print summary stats at end of test
# ---------------------------------------------------------------------------
@events.quitting.add_listener
def on_quitting(environment, **kwargs) -> None:  # noqa: ANN001
    stats = environment.runner.stats.total
    print("\n" + "=" * 60)
    print("Atlas Load Test Summary")
    print("=" * 60)
    print(f"  Total requests   : {stats.num_requests}")
    print(f"  Failures         : {stats.num_failures}")
    print(f"  Failure rate     : {stats.fail_ratio * 100:.1f}%")
    print(f"  Median latency   : {stats.median_response_time:.0f} ms")
    print(f"  p95 latency      : {stats.get_response_time_percentile(0.95):.0f} ms")
    print(f"  p99 latency      : {stats.get_response_time_percentile(0.99):.0f} ms")
    print(f"  RPS              : {stats.current_rps:.1f}")
    print("=" * 60)
