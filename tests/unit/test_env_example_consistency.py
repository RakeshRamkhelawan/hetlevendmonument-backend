"""
Valideert dat .env.example bestanden consistente configuratie hebben.
"""

import pathlib

ROOT = pathlib.Path(__file__).parents[2]


class TestSrcEnvExample:
    def test_happy_path_database_url_uses_asyncpg(self):
        env_example = (ROOT / "src" / ".env.example").read_text()
        db_url_lines = [
            line for line in env_example.splitlines() if line.startswith("DATABASE_URL=")
        ]
        assert db_url_lines, "DATABASE_URL niet gevonden in src/.env.example"
        db_url = db_url_lines[0]
        assert "asyncpg" in db_url, f"DATABASE_URL gebruikt geen asyncpg: {db_url!r}"

    def test_redis_password_comment_present(self):
        env_example = (ROOT / ".env.example").read_text()
        assert "REDIS_PASSWORD" in env_example


class TestDockerComposeRedis:
    def test_redis_service_has_requirepass_instruction(self):
        compose = (ROOT / "docker-compose.yml").read_text()
        assert "requirepass" in compose or "REDIS_PASSWORD" in compose
