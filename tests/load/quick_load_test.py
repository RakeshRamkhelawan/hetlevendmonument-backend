"""
Quick Load Test for Sprint 3 Task 3.1
Lightweight version for immediate execution without full backend setup

This tests the core performance of the multi-tenant system with:
- 10 concurrent users (scalable to 50)
- 2-minute duration (quick verification)
- Mix of operations: health checks, API calls

Usage:
    # Run quick test (2 min, 10 users)
    locust -f tests/load/quick_load_test.py --headless --users 10 --spawn-rate 2 --run-time 2m --host http://localhost:8100  # Port updated from 8000 to 8100

    # Run full test (30 min, 50 users) - same as test_50_tenants.py
    locust -f tests/load/quick_load_test.py --headless --users 50 --spawn-rate 5 --run-time 30m --host http://localhost:8100  # Port updated from 8000 to 8100

    # Web UI for monitoring
    locust -f tests/load/quick_load_test.py --host http://localhost:8100  # Port updated from 8000 to 8100
"""

import json
import random
import time

from locust import HttpUser, between, events, task


class QuickMetrics:
    """Simple metrics tracker"""

    def __init__(self):
        self.response_times = []
        self.errors = []

    def add_response(self, response_time):
        self.response_times.append(response_time)

    def add_error(self, error):
        self.errors.append(error)

    def get_percentiles(self):
        if not self.response_times:
            return {"p50": 0, "p95": 0, "p99": 0}

        sorted_times = sorted(self.response_times)
        count = len(sorted_times)

        return {
            "p50": sorted_times[int(count * 0.50)],
            "p95": sorted_times[int(count * 0.95)],
            "p99": sorted_times[int(count * 0.99)],
            "avg": sum(sorted_times) / count,
            "min": min(sorted_times),
            "max": max(sorted_times),
            "count": count,
        }

    def get_error_rate(self):
        total = len(self.response_times) + len(self.errors)
        return (len(self.errors) / total * 100) if total > 0 else 0


# Global metrics
metrics = QuickMetrics()


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Capture all request metrics"""
    if exception:
        metrics.add_error(str(exception))
    else:
        metrics.add_response(response_time)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate report when test completes"""
    print("\n" + "=" * 80)
    print("📊 LOAD TEST RESULTS - Sprint 3 Task 3.1")
    print("=" * 80)

    percentiles = metrics.get_percentiles()
    error_rate = metrics.get_error_rate()

    print("\n🎯 Performance Metrics:")
    print(f"   Total Requests: {percentiles['count']}")
    print(f"   Average Latency: {percentiles['avg']:.2f} ms")
    print(f"   p50 Latency: {percentiles['p50']:.2f} ms (Target: <100ms)")
    print(f"   p95 Latency: {percentiles['p95']:.2f} ms (Target: <300ms)")
    print(f"   p99 Latency: {percentiles['p99']:.2f} ms (Target: <500ms)")
    print(f"   Min Latency: {percentiles['min']:.2f} ms")
    print(f"   Max Latency: {percentiles['max']:.2f} ms")
    print(f"   Error Rate: {error_rate:.4f}% (Target: <0.01%)")

    print("\n✅ Target Achievement:")
    print(f"   p95 < 300ms: {'✅ PASS' if percentiles['p95'] < 300 else '❌ FAIL'}")
    print(f"   p99 < 500ms: {'✅ PASS' if percentiles['p99'] < 500 else '❌ FAIL'}")
    print(f"   Error rate < 0.01%: {'✅ PASS' if error_rate < 0.01 else '❌ FAIL'}")

    print("\n" + "=" * 80)


class MultiTenantUser(HttpUser):
    """Simulates a multi-tenant user with realistic operations"""

    wait_time = between(0.5, 2)  # Wait 0.5-2 seconds between requests

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant_id = f"tenant_{random.randint(1000, 9999)}"
        self.user_id = f"user_{random.randint(1000, 9999)}"

    @task(10)  # 10 out of 20 = 50% of requests (reads)
    def health_check(self):
        """Health check endpoint - fastest operation"""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(6)  # 6 out of 20 = 30% of requests (reads)
    def get_root(self):
        """Root endpoint - API documentation"""
        with self.client.get("/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Root endpoint failed: {response.status_code}")

    # De twee taken hieronder eisten tot 2026-08-14 een 200. Sinds ADR-036 OP-124 is de
    # OpenAPI-oppervlakte buiten development dicht (4xx), dus tegen elke deployment
    # rapporteerden ze 100% failure -- 20% van het gegenereerde verkeer, wat het hele
    # loadrapport onbruikbaar maakte. Ze meten nu de afwijzingsroute door de ASGI-stack en
    # accepteren zowel open (development) als dicht (deployment). Een 5xx blijft een echte
    # fout, en een 2xx op een deployment wordt door de smoke- en architecture-guards betrapt,
    # niet hier -- een loadtest is geen securitypoort.
    @task(2)  # 2 out of 20 = 10% of requests (writes)
    def api_docs(self):
        """OpenAPI documentation endpoint (open in development, 4xx op een deployment)"""
        with self.client.get("/docs", catch_response=True) as response:
            if response.status_code < 500:
                response.success()
            else:
                response.failure(f"Docs endpoint failed: {response.status_code}")

    @task(2)  # 2 out of 20 = 10% of requests (metadata)
    def openapi_schema(self):
        """OpenAPI schema endpoint (open in development, 4xx op een deployment)"""
        with self.client.get("/openapi.json", catch_response=True) as response:
            if response.status_code < 500:
                response.success()
            else:
                response.failure(f"OpenAPI schema failed: {response.status_code}")


if __name__ == "__main__":
    print("Load test script ready!")
    print(
        "Run with: locust -f tests/load/quick_load_test.py --headless --users 10 --spawn-rate 2 --run-time 2m --host http://localhost:8100  # Port updated from 8000 to 8100"
    )
