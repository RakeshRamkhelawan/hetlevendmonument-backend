"""Een side-effect-vrije bron voor de omgevingsvraag (ADR-036 OP-124).

Bewust NIET `from src.main import ENVIRONMENT`: die module heeft side effects bij import --
`validate_config_at_startup()` doet `sys.exit(1)` (`src/main.py:55-56`), `configure_logging()`
herbindt de loguru-sink, en `app = create_app()` bouwt een volledige applicatie. Een shim of een
losse service die alleen wil weten of hij in development draait, mag dat allemaal niet triggeren.

`src/main.py` gebruikt deze helper bewust NIET en houdt zijn eigen module-global: die wordt door
`tests/architecture/test_docs_disabled_in_prod.py` met `patch.object` gezet, en dat is precies wat
een reload onnodig maakt.
"""

import os


def is_development() -> bool:
    """True alleen als ENVIRONMENT exact 'development' is.

    De default is `production`, niet `development`: bij een ontbrekende variabele moeten de
    schema-endpoints DICHT staan. Fail-open op precies de storing die telt was OP-124.
    """
    return os.getenv("ENVIRONMENT", "production").lower() == "development"
