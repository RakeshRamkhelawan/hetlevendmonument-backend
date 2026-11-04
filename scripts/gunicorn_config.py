"""
Gunicorn Configuration for SanskritiSetu Production

Context7 Best Practice Sources:
- OpenTelemetry Python: /open-telemetry/opentelemetry-python
  Pattern: post_fork hook for tracer reinitialization in worker processes
- Prometheus Python Client: /prometheus/client_python
  Pattern: Multi-process metrics collection via environment variables

CRITICAL: Without post_fork hook, OpenTelemetry traces break in Gunicorn workers
due to stale gRPC connections from parent process.
"""

import multiprocessing
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# ==================== WORKER CONFIGURATION ====================

# Number of worker processes (CPU cores * 2 + 1)
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# Worker class - async workers for FastAPI
worker_class = "uvicorn.workers.UvicornWorker"

# Timeout for worker processes (30s)
timeout = int(os.getenv("GUNICORN_TIMEOUT", 30))

# Graceful shutdown timeout
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Keep-alive timeout for connections
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))

# ==================== BINDING ====================

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# ==================== PROXY ====================

# Welke directe verbinding mag X-Forwarded-For / X-Forwarded-Proto zetten (plan nazorg, punt b;
# ADR-038). UvicornWorker geeft deze gunicorn-instelling door aan uvicorn
# (uvicorn/workers.py: "forwarded_allow_ips": self.cfg.forwarded_allow_ips), en uvicorn
# vervangt alleen voor die adressen `request.client.host` door het adres uit de header.
# Default hier gelijk aan die van gunicorn 26: 127.0.0.1 en ::1. Achter de Container
# Apps-ingress betekent dat: `request.client.host` is het adres van de ingress, dus SlowAPI
# (get_remote_address) zet alle anonieme bezoekers in EEN bucket.
# Zet FORWARDED_ALLOW_IPS op het subnet waar de ingress vandaan komt (CIDR mag, bijvoorbeeld
# "10.0.0.0/21"). NIET op "*" als de container ook buiten de ingress om bereikbaar is.
# Het adres van de klant voor limiet, SecurityMiddleware en auditlog bepaalt `afzender_adres`
# (src/core/shared/limiet_sleutel.py), los hiervan, met TRUSTED_PROXY_NETWORKS.
# Niet gemeten op staging: welk adres de ingress daar gebruikt, staat nog open.
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1,::1")

# ==================== LOGGING ====================

# Access log format with tenant context
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" '
    "response_time=%(M)s tenant_id=%(tenant_id)s"
)

# Log to stdout for Docker
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")

# ==================== PROMETHEUS MULTI-PROCESS SUPPORT ====================

# Directory for Prometheus multi-process metrics
# Required for MultiProcessCollector to aggregate metrics from all workers
prometheus_multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus_multiproc")

# Ensure directory exists
os.makedirs(prometheus_multiproc_dir, exist_ok=True)

# Set environment variable for prometheus_client
os.environ["PROMETHEUS_MULTIPROC_DIR"] = prometheus_multiproc_dir


# ==================== GUNICORN LIFECYCLE HOOKS ====================


def on_starting(server):
    """
    Called just before the master process is initialized.
    """
    server.log.info("Starting Gunicorn master process")
    server.log.info(f"Workers: {workers}, Worker class: {worker_class}")
    server.log.info(f"Binding to: {bind}")


def when_ready(server):
    """
    Called just after the server is started.
    """
    server.log.info("Gunicorn server ready to accept connections")


def pre_fork(server, worker):
    """
    Called just before a worker is forked.
    """
    server.log.info(f"Pre-fork: Worker {worker.age} about to fork")


def post_fork(server, worker):
    """
    Called just after a worker has been forked.

    CRITICAL: Reinitialize OpenTelemetry tracer in forked process.
    Without this, all workers share the same gRPC connection from the parent
    process, causing traces to be lost or corrupted.

    Context7 Pattern: /open-telemetry/opentelemetry-python
    Official documentation: https://opentelemetry-python.readthedocs.io/en/latest/examples/fork-process-model/README.html
    """
    server.log.info(f"Post-fork: Worker spawned (pid={worker.pid})")

    # Only initialize tracing if enabled
    if os.getenv("ENABLE_TRACING", "false").lower() == "true":
        try:
            # Create service resource
            resource = Resource.create(
                {
                    "service.name": "sanskritisetu-backend",
                    "service.version": os.getenv("APP_VERSION", "1.0.0"),
                    "deployment.environment": os.getenv("ENVIRONMENT", "production"),
                    "process.pid": worker.pid,
                }
            )

            # Create new tracer provider for this worker
            provider = TracerProvider(resource=resource)

            # Configure OTLP exporter (Jaeger gRPC endpoint)
            otlp_exporter = OTLPSpanExporter(
                endpoint=os.getenv("TRACE_ENDPOINT", "http://jaeger:4317"),
                insecure=True,  # Use TLS in production with proper certificates
            )

            # Add batch span processor
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

            # Set as global tracer provider for this process
            trace.set_tracer_provider(provider)

            server.log.info(f"OpenTelemetry tracer initialized for worker {worker.pid}")
        except Exception as e:
            server.log.error(f"Failed to initialize OpenTelemetry in worker {worker.pid}: {e}")


def worker_exit(server, worker):
    """
    Called just after a worker has been exited.
    Clean up resources.
    """
    server.log.info(f"Worker exiting (pid={worker.pid})")

    # Flush pending traces
    if os.getenv("ENABLE_TRACING", "false").lower() == "true":
        try:
            provider = trace.get_tracer_provider()
            if hasattr(provider, "shutdown"):
                provider.shutdown()
                server.log.info(f"Flushed traces for worker {worker.pid}")
        except Exception as e:
            server.log.error(f"Error flushing traces for worker {worker.pid}: {e}")


def on_exit(server):
    """
    Called just before the master process exits.
    """
    server.log.info("Gunicorn master process shutting down")

    # Clean up Prometheus metrics directory
    import shutil

    if os.path.exists(prometheus_multiproc_dir):
        try:
            shutil.rmtree(prometheus_multiproc_dir)
            server.log.info("Cleaned up Prometheus multiproc directory")
        except Exception as e:
            server.log.error(f"Error cleaning up Prometheus directory: {e}")


# ==================== SECURITY ====================

# Limit request line size (prevent DoS)
limit_request_line = 4096

# Limit request header size
limit_request_fields = 100
limit_request_field_size = 8190

# ==================== PERFORMANCE ====================

# Preload application code before forking workers
# Reduces memory usage via copy-on-write
preload_app = True

# Worker restart settings
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 1000))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 50))

# Worker tmp directory (for heartbeat files)
worker_tmp_dir = "/dev/shm"  # RAM-based tmpfs for faster I/O
