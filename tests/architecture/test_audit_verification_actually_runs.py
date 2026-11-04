"""De ketenverificatie wordt daadwerkelijk ingepland en gealarmeerd (ADR-036 OP-109).

**De bevinding.** `AuditTrailVerificationJob` bestaat, `run_audit_verification` staat als
dramatiq-actor geregistreerd, en de job heeft een `DEFAULT_SCHEDULE`. Maar `scheduler.py` plande
hem niet in: twaalf `add_job(...)`-regels en geen daarvan was deze. Gevolg: de auditketen werd
NOOIT automatisch nagerekend. Manipulatie werd alleen opgemerkt als een mens toevallig een van de
drie admin-endpoints aanriep.

Datzelfde gold voor `check_hash_chain_integrity_actor` (de raad-keten). Dat stond NIET in OP-109
en is bij het uitzoeken van OP-118/119/120 gevonden: het is het enige pad dat de bestaande
Prometheus-teller bij PERIODIEKE verificatie ophoogt. Zonder inplanning bestond de alertregel
`CouncilHashChainBreak` wel, maar kon hij alleen vuren op schrijf-tijd-detectie.

**Waarom dit voor de sleutel-discussie uitmaakt.** Een sterkere hash op een keten die niemand
nakijkt, verandert de detectiekans niet. Dit is daarom stap 2 van vijf, voor het anker en voor de
HMAC.

**Waarom een metric en niet alleen een logregel.** Een `logger.error` in een worker is geen
alarm; er komt geen melding wanneer iets NIET gebeurt. De bestaande raad-keten heeft die les al
verwerkt (`copilot_hash_chain_breaks_total` + `infra/prometheus/alerts/copilot-council.yml`), en
de `audit_logs`-keten had helemaal geen metric.

**Mutatietest (2026-08-10, beide richtingen):** de `add_job`-regel voor `run_audit_verification`
weggehaald -> ROOD. Het `id=` veranderd naar een andere naam -> ROOD (de guard toetst de
letterlijke naam, niet "er is een job bijgekomen"). De metric-registratie weggehaald -> ROOD.
En de andere kant: een ongerelateerde job toevoegen aan de scheduler -> blijft GROEN.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEDULER = REPO_ROOT / "src/workers/scheduler.py"
METRICS = REPO_ROOT / "src/core/observability/audit_chain_metrics.py"
ALERTS = REPO_ROOT / "infra/prometheus/alerts/audit-chain.yml"

#: De verificatie-actors die ingepland MOETEN zijn, met wat ze bewaken.
_VEREISTE_JOBS = {
    "run_audit_verification": "de ADR-019-hashketen in audit_logs",
    "check_hash_chain_integrity": "de raad-keten in council_decisions",
}


def _geplande_job_ids() -> set[str]:
    """De `id=`-waarden van elke `add_job(...)` in de scheduler, via de AST.

    Bewust de AST en niet de bestandstekst: een naam komt in dat bestand ook voor in de
    runner-methode, in een logregel en in een import. Een substring-toets blijft groen nadat de
    PLANNING zelf is verwijderd -- zo is deze guardfamilie eerder betrapt.
    """
    boom = ast.parse(SCHEDULER.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        if not (isinstance(doel, ast.Attribute) and doel.attr == "add_job"):
            continue
        for sleutelwoord in knoop.keywords:
            if sleutelwoord.arg == "id" and isinstance(sleutelwoord.value, ast.Constant):
                if isinstance(sleutelwoord.value.value, str):
                    ids.add(sleutelwoord.value.value)
    return ids


def test_the_scan_finds_scheduled_jobs_at_all() -> None:
    """Vangnet: loopt de AST-scan leeg, dan bewaakt de test hieronder niets."""
    gevonden = _geplande_job_ids()

    assert len(gevonden) >= 10, (
        f"Slechts {len(gevonden)} `add_job(id=...)`-aanroepen gevonden: {sorted(gevonden)}. Is de "
        "aanroepvorm veranderd (bijvoorbeeld een variabele in plaats van een letterlijke string)? "
        "Dan meet deze guard niets meer."
    )


def test_the_chain_verification_is_scheduled() -> None:
    """Een verificatie die nergens draait, verifieert niets."""
    gepland = _geplande_job_ids()
    ontbreekt = sorted(naam for naam in _VEREISTE_JOBS if naam not in gepland)

    assert not ontbreekt, (
        f"Deze verificatiejobs staan in geen enkele `add_job(...)`: {ontbreekt}.\n\n"
        + "\n".join(f"  {naam}: bewaakt {_VEREISTE_JOBS[naam]}" for naam in ontbreekt)
        + "\n\nZonder inplanning wordt de keten alleen nagerekend als een mens toevallig een "
        "admin-endpoint aanroept. Elke versterking van de hash zelf is dan zinloos: er is niemand "
        "die kijkt (ADR-036 OP-109)."
    )


def test_a_metric_exists_for_the_audit_log_chain() -> None:
    """De uitkomst moet een alarm kunnen worden, niet alleen een logregel.

    Er komt geen melding wanneer iets NIET gebeurt -- dat is de terugkerende faalvorm in dit
    project. Een teller die op nul hoort te staan is het enige dat een alertregel kan aangrijpen.
    """
    assert METRICS.exists(), (
        f"{METRICS.relative_to(REPO_ROOT)} bestaat niet. De raad-keten heeft wel een teller "
        "(`copilot_hash_chain_breaks_total`), de audit_logs-keten niet -- terwijl dat de keten is "
        "waar het art.-14-bewijs in staat."
    )

    bron = METRICS.read_text(encoding="utf-8")
    boom = ast.parse(bron)
    aangemaakt = {
        knoop.func.attr if isinstance(knoop.func, ast.Attribute) else getattr(knoop.func, "id", "")
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Call)
    }

    assert "_get_or_create_counter" in aangemaakt, (
        "Er wordt geen teller aangemaakt via het bestaande idempotente patroon "
        "(`src/core/observability/metrics.py::_get_or_create_counter`). Een kale `Counter(...)` "
        "klapt om bij een tweede import in dezelfde registry."
    )


def test_an_alert_fires_on_that_metric() -> None:
    """Een teller zonder alertregel is een getal dat niemand ziet."""
    assert ALERTS.exists(), (
        f"{ALERTS.relative_to(REPO_ROOT)} bestaat niet. Zonder alertregel blijft een verhoogde "
        "teller onopgemerkt tot iemand toevallig een dashboard opent."
    )

    import yaml

    regels = yaml.safe_load(ALERTS.read_text(encoding="utf-8")) or {}
    uitdrukkingen = [
        regel.get("expr", "")
        for groep in (regels.get("groups") or [])
        for regel in (groep.get("rules") or [])
    ]

    assert any("audit_chain" in expr for expr in uitdrukkingen), (
        f"Geen enkele alertregel grijpt aan op een `audit_chain`-teller. Gevonden: {uitdrukkingen}"
    )
