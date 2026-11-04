"""
REAL Integration Tests - No Mocks, No Placeholders.

These tests connect to actual external services:
- PostgreSQL (localhost:5435) with pgvector
- Ollama (localhost:11434) for embeddings
- Redis (localhost:6385) for Pub/Sub

Requirements:
1. Docker Compose must be running: docker-compose up -d postgres ollama redis
2. Ollama must have nomic-embed-text model: ollama pull nomic-embed-text

Run:
    pytest tests/integration_real/ -v --integration

Skip (if services unavailable):
    pytest tests/integration_real/ -v

Note: These tests modify REAL data. Use clean_test_data fixture for isolation.
"""

# List of services required for these tests
REQUIRED_SERVICES = {
    "postgres": {"host": "localhost", "port": 5435, "description": "PostgreSQL with pgvector"},
    "ollama": {"host": "localhost", "port": 11434, "description": "Ollama embeddings"},
    "redis": {"host": "localhost", "port": 6385, "description": "Redis Pub/Sub"},
}


def check_services():
    """Check if all required services are available."""
    import socket

    results = {}
    for name, config in REQUIRED_SERVICES.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((config["host"], config["port"]))
            sock.close()
            results[name] = result == 0
        except Exception:
            results[name] = False

    return results
