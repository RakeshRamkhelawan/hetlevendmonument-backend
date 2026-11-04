"""De zes schrijvers zetten de algoritme-markering, en alleen als er een sleutel is (OP-120).

**De ontwerpbeslissing die deze tests vastleggen.** Als de schrijvers onvoorwaardelijk HMAC
zouden gebruiken, gooit `audit_chain_key()` buiten een ontwikkelomgeving een `RuntimeError` zodra
`AUDIT_CHAIN_HMAC_KEY` niet gewired is. Die fout wordt door `log_event` opgevangen (degraded
mode), en dan wordt ELKE auditregel stil ongehasht weggeschreven. Dat is erger dan de toestand
van voor de omschakeling: geen enkele verificatie meer, zonder dat iemand het merkt.

Daarom schakelen de schrijvers alleen om als er een ECHTE sleutel is. Geen ephemere sleutel voor
de keten: die is per proces anders, en dan verifieert dezelfde rij na een worker-recycle
(ADR-011) niet meer -- dat leest als manipulatie terwijl er niets is gebeurd.

**Is dat niet fail-open?** Gedeeltelijk, en bewust. Wie de omgevingsvariabele wegneemt, zet
nieuwe rijen terug op sleutelloze SHA-256. Dat is precies waarvoor het knippunt bestaat: een rij
NA `chain_epoch_id` zonder markering is een afwijking, ook als de hash klopt. De degradatie is
dus zichtbaar in plaats van stil -- en dat is het verschil met de variant hierboven.

**Mutatietest (2026-08-11, beide richtingen):** de markering weggehaald bij een schrijver -> ROOD.
De sleutelcontrole weggehaald zodat er altijd HMAC wordt gebruikt -> ROOD op de test die eist dat
een ONgeconfigureerde omgeving op legacy blijft. En de andere kant: met sleutel -> markering
gezet; zonder sleutel -> geen markering en gewoon een werkende SHA-256-keten.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.core.governance import audit_chain_key as sleutelmodule
from src.core.governance.audit_chain_key import ALGORITHM_NAME
from src.core.governance.models import AuditLog

_STERKE_SLEUTEL = "s" + "leutelmateriaal-voor-de-auditketen-2026" * 2


def _verse_module(**env: str):
    """Herlaad de sleutelcache met deze omgeving actief."""
    return patch.dict(os.environ, env, clear=True)


class TestTheWritersOnlySwitchWhenThereIsAKey:
    def setup_method(self) -> None:
        sleutelmodule.reset_key_cache()

    def teardown_method(self) -> None:
        sleutelmodule.reset_key_cache()

    def test_with_a_key_the_entry_is_marked(self) -> None:
        entry = AuditLog(tenant_id=1, action="a", resource="b")

        with _verse_module(ENVIRONMENT="production", AUDIT_CHAIN_HMAC_KEY=_STERKE_SLEUTEL):
            sleutelmodule.reset_key_cache()
            sleutelmodule.mark_entry(entry)

        assert entry.hash_algorithm == ALGORITHM_NAME, (
            "De markering wordt niet gezet terwijl er een sleutel is. Dan blijft de keten "
            "ongesleuteld en verandert OP-120 niets."
        )

    def test_without_a_key_the_entry_stays_on_legacy(self) -> None:
        """De belangrijkste test: geen sleutel betekent GEEN markering, niet een harde fout.

        Zou de schrijver hier omschakelen, dan gooit `audit_chain_key()` in productie een
        RuntimeError, vangt `log_event` die op, en wordt elke auditregel ongehasht weggeschreven.
        """
        entry = AuditLog(tenant_id=1, action="a", resource="b")

        with _verse_module(ENVIRONMENT="production"):
            sleutelmodule.reset_key_cache()
            sleutelmodule.mark_entry(entry)

        assert entry.hash_algorithm is None, (
            "Zonder sleutel wordt de rij toch als gesleuteld gemarkeerd. In productie gooit de "
            "sleutelmodule dan een RuntimeError bij het hashen, vangt log_event die op, en "
            "belandt ELKE auditregel ongehasht in de tabel -- stil."
        )

    def test_an_ephemeral_development_key_is_not_used_for_the_chain(self) -> None:
        """Een sleutel per proces zou elke keten na een herstart als gebroken laten lezen."""
        entry = AuditLog(tenant_id=1, action="a", resource="b")

        with _verse_module(ENVIRONMENT="development"):
            sleutelmodule.reset_key_cache()
            sleutelmodule.mark_entry(entry)

        assert entry.hash_algorithm is None, (
            "In development zonder sleutel wordt de rij gemarkeerd. De ephemere sleutel is per "
            "proces anders, dus na een worker-recycle (ADR-011) verifieert dezelfde rij niet "
            "meer -- dat leest als manipulatie terwijl er niets is gebeurd."
        )

    def test_a_weak_key_is_refused_rather_than_silently_used(self) -> None:
        """Fail-closed op een te zwakke sleutel, net als `redaction.py` doet."""
        entry = AuditLog(tenant_id=1, action="a", resource="b")

        with _verse_module(ENVIRONMENT="production", AUDIT_CHAIN_HMAC_KEY="kort"):
            sleutelmodule.reset_key_cache()
            with pytest.raises(RuntimeError, match="te zwak"):
                sleutelmodule.mark_entry(entry)


def test_every_writer_marks_the_entry() -> None:
    """Alle zes schrijfpaden moeten de markering zetten voordat ze hashen.

    Toetst de AST en niet de bestandstekst: een naam in een comment of docstring zou een
    tekstzoektocht al tevreden stellen, en dat is de faalvorm uit `.claude/rules/quality-gates.md`
    die in dit project herhaaldelijk is opgetreden.
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    schrijvers = {
        "src/core/governance/audit.py",
        "src/core/governance/services/audit_service.py",
        "src/core/governance/ai_transparency_service.py",
        "src/core/governance/cookie_consent.py",
        "src/core/governance/dsar_service.py",
        "src/core/security/security_audit_service.py",
    }

    ontbreekt: list[str] = []
    for pad in sorted(schrijvers):
        boom = ast.parse((repo / pad).read_text(encoding="utf-8"))
        roept_aan = any(
            isinstance(knoop, ast.Call)
            and (
                getattr(knoop.func, "attr", "") == "mark_entry"
                or getattr(knoop.func, "id", "") == "mark_entry"
            )
            for knoop in ast.walk(boom)
        )
        if not roept_aan:
            ontbreekt.append(pad)

    assert not ontbreekt, (
        f"Deze schrijvers zetten de algoritme-markering niet: {ontbreekt}.\n\n"
        "Een rij zonder markering valt in de sleutelloze legacy-tak. Zolang een van de zes dat "
        "doet, blijft er een pad waarlangs nieuwe rijen ongesleuteld binnenkomen -- en na het "
        "knippunt melden die zichzelf als afwijking."
    )
