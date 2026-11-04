"""Elke opgeruimde categorie wijst naar de JUISTE tabel (ADR-036 OP-115, Fase D).

**De bevinding, gemeten 2026-08-10.** `retention_cleanup_job.py` ruimt vijf categorieen op:
`USER_DATA`, `ACTIVITY_LOGS`, `AI_INTERACTIONS`, `DOCUMENTS` en `ANALYTICS`. Geen van de vijf
staat in `table_mapping` in `RetentionCleanupService._get_table_info`. Ze vallen dus alle vijf
door naar de default -- en die wijst naar `audit_logs`.

Twee gevolgen:

1. **GDPR-retentie voor die vijf soorten data draait NIET.** Gebruikersdata, activiteitenlogs,
   AI-interacties, documenten en analytics worden nooit opgeruimd, terwijl de job wel meldt dat
   hij dat doet. Dat is een art.-5(1)(e)-gat.
2. **Een latente vernietigingsroute naar de auditketen.** De default richt
   `DELETE FROM audit_logs` op de tabel waar dit hele OP-108-traject over gaat. Vandaag inert:
   alle vijf krijgen via `get_default_policy` de terugvalregel van 2555 dagen (7 jaar), en zo
   oud is niets. Maar wie ooit een kortere termijn voor `ANALYTICS` instelt, verwijdert
   auditregels -- en een verwijderde rij breekt de keten door AFWEZIGHEID, wat geen enkele
   hash-fix kan repareren.

**Wat er op 2026-08-30 is veranderd (ADR-036 OP-115, golf 2).** De stille default is weg.
`_get_table_info` gooit nu `RetentieDoeltabelOntbreekt` voor een categorie zonder doeltabel, en
de opruimjob rapporteert die als OVERGESLAGEN in plaats van als geslaagd. Ook zijn `FINANCIAL`
en `HEALTH` uit de afbeelding gehaald: die wezen expliciet naar `audit_logs`, dus voor die twee
was de vernietigingsroute naar de auditketen niet latent maar de actieve configuratie.

Wat NIET is opgelost, en bewust niet: welke tabel en datumkolom elk van deze zeven categorieen
zou moeten krijgen. Dat is een inhoudelijke keuze (waar staan financiele en medische gegevens?)
en geen opruimwerk. Tot die keuze er is, ruimt het systeem voor die categorieen aantoonbaar
NIETS op -- zichtbaar in de jobuitvoer, in plaats van verstopt achter een succesmelding.

**Waarom dit een GROENE guard is en geen rode test.** Repareren betekent voor zeven categorieen
een doeltabel EN een datumkolom kiezen, plus `_RETENTION_ALLOWED_TABLES` uitbreiden. Dat is een
eigen wijziging met eigen tests. Een opzettelijk rode test zou hier de merge van iedereen
blokkeren (de testgate is sinds 2026-07-31 blokkerend) voor een bevinding die bewust naar een
latere fase gaat -- precies waar `.claude/rules/quality-gates.md` de uitzonderingsvorm voor
beschrijft.

**Mutatietest (2026-08-10, beide richtingen):**
- Een zesde, niet-gemapte categorie aan de job toegevoegd -> ROOD op `test_no_new_unmapped_category`.
- `USER_DATA` alsnog aan `table_mapping` toegevoegd -> ROOD op de staleness-test.
- LEGITIEM: een categorie toegevoegd die WEL gemapt is (`AUDIT_LOG`) -> GROEN.

**Mutatietest op de nieuwe toets (2026-08-30, beide richtingen):**
- De oude `table_mapping.get(category, {...})`-vorm teruggezet -> ROOD op
  `test_the_silent_fallback_to_audit_logs_is_gone`.
- Weer weggehaald -> GROEN.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "src/core/governance/retention_cleanup.py"
JOB = REPO_ROOT / "src/core/jobs/retention_cleanup_job.py"

#: Categorieen die de geplande job opruimt terwijl er geen doeltabel voor bestaat, met datum en
#: reden. Ze vallen door naar de default (`audit_logs`).
KNOWN_UNMAPPED_CATEGORIES: dict[str, str] = {
    "USER_DATA": (
        "2026-08-10 -- valt door naar de default (audit_logs). Er is geen `users`-retentie, "
        "terwijl PERSONAL_DATA daar wel op wijst. ADR-036 OP-115, Fase D, P2."
    ),
    "ACTIVITY_LOGS": (
        "2026-08-10 -- geen doeltabel gekozen; valt door naar audit_logs. OP-115, Fase D, P2."
    ),
    "AI_INTERACTIONS": (
        "2026-08-10 -- geen doeltabel; AI_DECISION wijst wel naar `ai_decisions`, deze niet. "
        "OP-115, Fase D, P2."
    ),
    "DOCUMENTS": (
        "2026-08-10 -- geen doeltabel gekozen; valt door naar audit_logs. OP-115, Fase D, P2."
    ),
    "ANALYTICS": (
        "2026-08-10 -- geen doeltabel gekozen; valt door naar audit_logs. OP-115, Fase D, P2."
    ),
    "FINANCIAL": (
        "2026-08-30 -- wees tot vandaag EXPLICIET naar audit_logs (`# Fallback to audit_logs`). "
        "Die regel is verwijderd; welke tabel financiele gegevens draagt is een openstaande "
        "keuze. OP-115, Fase D, P2."
    ),
    "HEALTH": (
        "2026-08-30 -- idem: wees expliciet naar audit_logs. Verwijderd; doeltabel voor "
        "medische gegevens is een openstaande keuze. OP-115, Fase D, P2."
    ),
}


def _categorieen_in_de_job() -> set[str]:
    """De categorieen die de opruimjob DAADWERKELIJK doorloopt.

    **Vervangen op 2026-09-17, en de reden hoort hier te staan.** Hier stond een AST-scan
    die elke `DataCategory.X`-vermelding in `retention_cleanup_job.py` verzamelde. Dat
    werkte zolang die job een HANDMATIGE lijst van vijf had -- en precies die lijst bleek
    het probleem: geen van de vijf had een bewaartermijn of een doeltabel, dus de job ruimde
    aantoonbaar NOOIT iets op (ADR-036 OP-253).

    De job leidt zijn categorieen nu af uit "heeft beleid EN doeltabel". Een AST-scan op
    vermeldingen meet daarmee niets meer: hij zou alleen nog de namen in
    `_NIET_AUTOMATISCH` vinden -- de twee categorieen die juist bewust NIET worden
    opgeruimd. Dat is het tegenovergestelde van wat deze guard hoort te meten.

    Daarom nu de echte bron: de afgeleide lijst zelf, over alle jurisdicties.
    """
    from src.core.governance.retention_cleanup import RetentionJurisdiction
    from src.core.jobs.retention_cleanup_job import te_verwerken_categorieen

    gevonden: set[str] = set()
    for jurisdictie in RetentionJurisdiction:
        gevonden |= {categorie.name for categorie in te_verwerken_categorieen(jurisdictie)}
    return gevonden


def _gemapte_categorieen() -> set[str]:
    """De `DataCategory.X`-sleutels van `table_mapping` in `_get_table_info`, via de AST.

    Bewust de SLEUTELS van die ene dict en niet elke `DataCategory`-vermelding in het bestand:
    de enum-definitie zelf staat er ook in, en die zou de guard leegmaken.
    """
    boom = ast.parse(SERVICE.read_text(encoding="utf-8"))
    for knoop in ast.walk(boom):
        if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if knoop.name != "_get_table_info":
            continue
        for binnen in ast.walk(knoop):
            if not isinstance(binnen, ast.Assign):
                continue
            doelen = [t.id for t in binnen.targets if isinstance(t, ast.Name)]
            if "table_mapping" not in doelen or not isinstance(binnen.value, ast.Dict):
                continue
            return {
                sleutel.attr
                for sleutel in binnen.value.keys
                if isinstance(sleutel, ast.Attribute)
                and isinstance(sleutel.value, ast.Name)
                and sleutel.value.id == "DataCategory"
            }
    return set()


def test_the_scan_finds_both_sides() -> None:
    """Vangnet: loopt een van beide scans leeg, dan bewaakt de rest niets."""
    job = _categorieen_in_de_job()
    gemapt = _gemapte_categorieen()

    assert len(job) >= 1, (
        f"De opruimjob doorloopt {len(job)} categorieen: {sorted(job)}. Bij NUL doet hij elke "
        "nacht niets en meldt hij toch 'completed: true, total_records_deleted: 0' -- de "
        "toestand waarin hij tot 2026-09-17 verkeerde (ADR-036 OP-253). De ondergrens is hier "
        "bewust 1 en niet 5: sinds die dag is de lijst AFGELEID uit 'heeft beleid EN "
        "doeltabel', dus hij krimpt en groeit mee met de werkelijkheid in plaats van met een "
        "handmatige opsomming."
    )
    assert len(gemapt) >= 5, (
        f"Slechts {len(gemapt)} sleutels gevonden in `table_mapping`: {sorted(gemapt)}. Is de "
        "dict hernoemd of verplaatst? Dan lijkt ALLES ongemapt en is de uitzonderingslijst "
        "opeens de hele waarheid."
    )


def test_no_new_unmapped_category() -> None:
    """Een nieuwe categorie zonder doeltabel is geblokkeerd."""
    ongemapt = _categorieen_in_de_job() - _gemapte_categorieen()
    nieuw = sorted(ongemapt - set(KNOWN_UNMAPPED_CATEGORIES))

    assert not nieuw, (
        f"Deze categorieen worden opgeruimd maar hebben geen doeltabel: {nieuw}.\n\n"
        "Ze vallen door naar de default in `_get_table_info`, en die wijst naar `audit_logs`. "
        "Gevolg: de data die je denkt op te ruimen blijft staan, EN de opruimactie richt zich "
        "op de auditketen. Een verwijderde auditregel breekt die keten door AFWEZIGHEID -- daar "
        "helpt geen enkele hash-reparatie tegen (ADR-036 OP-115).\n\n"
        "Voeg een doeltabel + datumkolom toe aan `table_mapping` (en de tabel aan "
        "`_RETENTION_ALLOWED_TABLES`), of zet de categorie met datum en reden in "
        "KNOWN_UNMAPPED_CATEGORIES."
    )


def test_known_unmapped_categories_is_not_stale() -> None:
    """Een categorie die inmiddels WEL gemapt is MOET uit de lijst."""
    gemapt = _gemapte_categorieen()
    opgelost = sorted(naam for naam in KNOWN_UNMAPPED_CATEGORIES if naam in gemapt)

    assert not opgelost, (
        f"Deze categorieen staan in KNOWN_UNMAPPED_CATEGORIES maar hebben inmiddels een "
        f"doeltabel: {opgelost}. Haal ze uit de lijst; anders verbergt die lijst de dag waarop "
        "OP-115 daadwerkelijk is opgelost."
    )


def test_the_silent_fallback_to_audit_logs_is_gone() -> None:
    """`_get_table_info` mag geen default meer hebben die naar `audit_logs` wijst.

    Dit is de kern van OP-115 en de enige regel die zonder inhoudelijke keuze te handhaven is.
    Een `dict.get(category, {...})` is de vorm die het probleem maakte: hij geeft een ANTWOORD
    op een vraag die niet beantwoord is. De uitzonderingslijst hierboven mag groeien; deze
    terugval mag niet terugkomen.
    """
    boom = ast.parse(SERVICE.read_text(encoding="utf-8"))
    overtreders: list[str] = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if knoop.name != "_get_table_info":
            continue
        for binnen in ast.walk(knoop):
            if not isinstance(binnen, ast.Call):
                continue
            doel = binnen.func
            if not isinstance(doel, ast.Attribute) or doel.attr != "get":
                continue
            if isinstance(doel.value, ast.Name) and doel.value.id == "table_mapping":
                if len(binnen.args) > 1:
                    overtreders.append(f"regel {binnen.lineno}: table_mapping.get(..., default)")

    assert not overtreders, (
        "De stille terugval in `_get_table_info` is terug:\n  "
        + "\n  ".join(overtreders)
        + "\n\nEen niet-gemapte categorie krijgt daarmee weer een doeltabel toegewezen die "
        "niemand heeft gekozen -- tot 2026-08-30 was dat `audit_logs`, de auditketen zelf. "
        "Gebruik `table_mapping[category]` en laat een ontbrekende sleutel "
        "`RetentieDoeltabelOntbreekt` opleveren; `retention_cleanup_job.py` vangt die op en "
        "rapporteert de categorie als overgeslagen (ADR-036 OP-115)."
    )
