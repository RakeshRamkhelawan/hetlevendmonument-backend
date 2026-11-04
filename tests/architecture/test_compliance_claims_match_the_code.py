"""Compliance-documenten beweren niet meer dan de code waarmaakt (ADR-036 OP-118 t/m OP-121).

**De bevinding, gemeten 2026-08-10/11.** Zeven documenten die voor een auditor bedoeld zijn,
claimden eigenschappen die de code niet had:

- `ai-act-risk-assessment.md`: "onweerlegbaar en tamper-proof", plus "periodieke
  integriteitscontroles" terwijl niets die controle inplande;
- `AI_ACT_SIGN_OFF_S9.md`: "Voorkomt silent tampering door aanvallers met DB-toegang" -- precies
  de aanvaller die WEL slaagt, want de hash is ongesleuteld;
- `pentest-report.md`: **PASS** op "Audit Log Tampering" tegen een malafide admin, en "de
  ChainVerifier detecteert het verwijderen van rijen" terwijl een verwijderde staart
  `is_valid=True` gaf;
- `information-security-policy.md` en `soc2/README.md`: een gestreamde kopie naar Log Analytics
  die niet bestaat;
- ADR-019 zelf: RLS op `audit_logs` (die tabel is er juist expliciet van uitgesloten).

**Wat deze guard doet.** Twee dingen die in code toetsbaar zijn:

1. De twee absolute termen mogen alleen nog voorkomen op een regel die ze INTREKT. Een nieuwe
   claim erbij zetten wordt geblokkeerd.
2. Een document mag niet beweren dat auditlogs naar Log Analytics stromen zolang er geen enkele
   exporter in `src/` bestaat. Dat tweede deel is aan de CODE gekoppeld: verschijnt er ooit een
   echte export, dan mag de claim weer.

**De grens van deze guard, eerlijk benoemd.** Markdown heeft geen AST, dus dit is per constructie
een tekstcontrole -- de faalvorm waar `.claude/rules/quality-gates.md` voor waarschuwt. Hij kan
niet zien of een zin een bewering of een citaat is; hij ziet alleen of de intrekkingsmarkering op
dezelfde regel staat. Dat is bewust: de alternatieven (een claim-register in YAML, of natuurlijke
taal parsen) zijn zwaarder dan het probleem en zouden zelf weer uit de pas gaan lopen met de
documenten.

**Mutatietest (2026-08-11, beide richtingen):** in `pentest-report.md` een kale regel
"De audit-trail is tamper-proof." toegevoegd -> ROOD. Een `azure-monitor`-exporter gesimuleerd in
`src/` en de Log-Analytics-claim teruggezet -> GROEN (de claim mag dan weer). En de andere kant:
de bestaande, correct ingetrokken regels -> blijven GROEN, anders zou "verwijder elke vermelding"
de enige manier zijn om deze guard te halen.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Documenten die naar een auditor gaan en dus geen onhoudbare claim mogen bevatten.
_COMPLIANCE_DOCS = (
    "docs/adr/019-audit-logging-compliance.md",
    "docs/compliance/ai-act-risk-assessment.md",
    "docs/compliance/AI_ACT_SIGN_OFF_S9.md",
    "docs/compliance/pentest-report.md",
    "docs/compliance/soc2/information-security-policy.md",
    "docs/compliance/soc2/README.md",
)

#: Termen die een absolute garantie beloven. "tamper-EVIDENT" mag wel -- dat is wat de keten doet;
#: "tamper-PROOF" belooft preventie, en dat doet hij niet.
_ABSOLUTE_TERMEN = ("tamper-proof", "onweerlegbaar", "cryptografisch gesloten")

#: De sectie waarin deze termen per definitie BESPROKEN worden in plaats van beweerd.
#: Structureel begrensd door de markdown-kopregels eromheen -- niet door magische woorden.
_UITLEGSECTIE = "Wat tamper-evident hier WEL en NIET betekent"


def _regels(pad: str) -> list[tuple[int, str]]:
    bestand = REPO_ROOT / pad
    if not bestand.exists():
        return []
    return list(enumerate(bestand.read_text(encoding="utf-8").splitlines(), start=1))


def _beweringen(pad: str) -> list[tuple[int, str]]:
    """De regels die iets BEWEREN, dus zonder de plekken waar een term wordt besproken.

    Drie structurele uitsluitingen, en bewust geen lijst met magische woorden. Een eerdere versie
    zocht naar "ingetrokken", "gecorrigeerd" en dergelijke, en betrapte toen ADR-019's EIGEN
    uitleg dat die termen niet van toepassing zijn -- drie valse positieven. Meer woorden
    toevoegen is dweilen; de grens is structureel:

    - een blockquote (`>`) is in deze documenten de correctienotitie;
    - `~~doorhaling~~` is markdown voor "dit gold, en geldt niet meer";
    - de uitlegsectie in ADR-019 bespreekt de termen per definitie.
    """
    binnen_uitleg = False
    niveau_uitleg = 0
    uit: list[tuple[int, str]] = []

    for nummer, regel in _regels(pad):
        gestript = regel.strip()

        if gestript.startswith("#"):
            niveau = len(gestript) - len(gestript.lstrip("#"))
            if _UITLEGSECTIE in gestript:
                binnen_uitleg, niveau_uitleg = True, niveau
                continue
            if binnen_uitleg and niveau <= niveau_uitleg:
                binnen_uitleg = False

        if binnen_uitleg or gestript.startswith(">") or "~~" in regel:
            continue

        uit.append((nummer, regel))
    return uit


def _log_analytics_export_bestaat() -> bool:
    """Stuurt er iets in `src/` daadwerkelijk logs naar Azure Monitor / Log Analytics?

    Bewust `git grep` en niet zelf de boom inlezen: een test die alle getrackte bestanden in
    Python leest heeft eerder een xdist-worker omgebracht (ADR-036 OP-19/OP-46).
    """
    resultaat = subprocess.run(
        [
            "git",
            "grep",
            "-l",
            "-I",
            "-E",
            r"configure_azure_monitor|OTLPLogExporter|azure\.monitor|LogsIngestionClient",
            "--",
            "src/",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultaat.returncode not in (0, 1):
        raise AssertionError(
            f"`git grep` faalde (rc={resultaat.returncode}): {resultaat.stderr.strip()!r}. Een "
            "guard die de returncode negeert leest een lege uitvoer als 'niets gevonden'."
        )
    return bool(resultaat.stdout.strip())


def test_the_scan_reads_the_documents_at_all() -> None:
    """Vangnet: zijn de documenten er nog, en zijn ze niet leeg?"""
    leeg = [pad for pad in _COMPLIANCE_DOCS if not _regels(pad)]

    assert not leeg, (
        f"Deze compliance-documenten zijn leeg of bestaan niet: {leeg}. Zolang de scan niets "
        "leest, bewaakt alles hieronder niets."
    )


def test_no_document_promises_an_absolute_guarantee() -> None:
    """ "tamper-evident" mag; "tamper-proof" belooft preventie die er niet is."""
    overtredingen: list[str] = []
    for pad in _COMPLIANCE_DOCS:
        for nummer, regel in _beweringen(pad):
            laag = regel.lower()
            if any(term in laag for term in _ABSOLUTE_TERMEN):
                overtredingen.append(f"{pad}:{nummer}: {regel.strip()[:100]}")

    assert not overtredingen, (
        "Deze regels beloven een absolute garantie die de code niet waarmaakt:\n"
        + "\n".join(f"  {o}" for o in overtredingen)
        + "\n\nDe keten is tamper-EVIDENT voor een aanvaller zonder schrijfrechten op de "
        "database. Hij is niet tamper-PROOF: de hash is ongesleuteld, dus wie de tabel kan "
        'schrijven kan hem herberekenen (ADR-036 OP-120). Zie ADR-019, "Wat tamper-evident hier '
        'WEL en NIET betekent".'
    )


def test_no_document_claims_a_log_analytics_stream_that_does_not_exist() -> None:
    """Deze claim is aan de CODE gekoppeld: bestaat de export, dan mag de bewering weer."""
    if _log_analytics_export_bestaat():
        return  # er is een echte exporter; dan is de claim houdbaar

    overtredingen: list[str] = []
    for pad in _COMPLIANCE_DOCS:
        for nummer, regel in _beweringen(pad):
            laag = regel.lower()
            if "log analytics" not in laag:
                continue
            # Alleen een BEWERING dat er iets heen gaat is een probleem; de workspace noemen mag.
            if any(woord in laag for woord in ("gestreamd", "weggeschreven", "voor audit-logs")):
                overtredingen.append(f"{pad}:{nummer}: {regel.strip()[:100]}")

    assert not overtredingen, (
        "Deze regels beweren dat auditlogdata naar Azure Log Analytics gaat, terwijl er in "
        "`src/` geen enkele exporter bestaat:\n"
        + "\n".join(f"  {o}" for o in overtredingen)
        + "\n\nDe workspace staat wel in `infra/modules/log-analytics.bicep`, maar er is geen "
        "`diagnosticSettings`, geen OpenTelemetry-logexport en geen azure-monitor-pakket. "
        "Auditlogdata staat uitsluitend in PostgreSQL (ADR-036 OP-119)."
    )


def test_the_adr_carries_the_full_qualification() -> None:
    """De afgeleide documenten verwijzen ernaar; dan moet hij er ook zijn.

    Zonder deze toets kan de kernparagraaf uit ADR-019 verdwijnen terwijl vijf andere documenten
    er nog naar wijzen -- en dan is de nuance weg terwijl alles groen blijft.
    """
    adr = (REPO_ROOT / "docs/adr/019-audit-logging-compliance.md").read_text(encoding="utf-8")

    assert "Wat tamper-evident hier WEL en NIET betekent" in adr, (
        "De paragraaf die vastlegt wat de keten wel en niet detecteert is verdwenen uit ADR-019. "
        "Vijf compliance-documenten verwijzen ernaar."
    )
    for verwacht in ("OP-120", "ongesleuteld", "Log Analytics"):
        assert verwacht in adr, (
            f"De kernparagraaf noemt {verwacht!r} niet meer. De drie grenzen die een auditor moet "
            "kennen zijn: de ongesleutelde hash, de ontbrekende externe kopie, en de kolommen "
            "buiten de hash."
        )
