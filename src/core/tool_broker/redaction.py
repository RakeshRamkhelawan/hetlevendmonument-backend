"""Pseudonimisering van tool-payloads voordat ze in bewarende sinks belanden (ADR-036 OP-27).

Een tool-payload is bij agent-gedreven uitvoering de `json.loads` van een `TOOL_CALL`-directive
en dus door een taalmodel geschreven: elke sleutelnaam en elke waarde is aanvallerbeinvloed.

**ZEVEN bewarende plekken, met per plek de gemeten stand (2026-08-05).** Deze opsomming stond
tot ronde 7 op VIJF, en dat was twee keer onjuist: OP-33 en OP-47 hebben er sindsdien twee
toegevoegd. De blinde review betrapte dat deze docstring -- de plek die de beslissing bezit --
niet was bijgewerkt terwijl de ADR dat wel was.

| # | Plek | Stand |
| - | ---- | ----- |
| 1 | event bus | LATENT: `git grep "event_publisher="` over `src/` is leeg |
| 2 | leeropslag, `observation_data` | LATENT, zelfde reden |
| 3 | ADR-019 auditketen, `tool_input` | LIVE, geredigeerd (F7, 2026-10-26: elke broker-maker krijgt `audit_session_factory=`) |
| 4 | proces-globale uitvoeringsgeschiedenis (`api/v1/tool_broker_shared.py`) | LIVE, geredigeerd |
| 5 | HITL-ticket via `tool_broker/router.py` | NIET GESERVEERD: nul importeurs (OP-37) |
| 6 | `council_decisions.action_params` + `OfficerVerdictRow.evidence` | LIVE, geredigeerd (OP-33) |
| 7 | `hitl_tickets.payload` via `copilot/service.py:528` | LIVE en RAUW -- OP-47, open |

De machinaal bewarende plekken gaan door deze module. **Het HITL-ticket bewust niet:** wie een
actie goedkeurt moet zien wat hij goedkeurt (AI Act art. 14).

**Let op waar dat schrijfpad echt loopt.** Deze docstring wees het naar `tool_broker/router.py`;
dat bestand heeft nul importeurs en wordt niet geserveerd. Het live pad is
`copilot/service.py:528` -> `hitl_repository.create_hitl_request` -> `self.create(payload=...)`,
en dat is nummer 7 hierboven -- de plek die de art.-14-uitzondering krijgt EN geen wisroute heeft
(OP-36). Wie hier las dat de uitzondering over een niet-geserveerde router gaat, concludeerde dat
de live write buiten scope viel. Zo bleef OP-47 vijf rondes onzichtbaar.

**Pseudonimiseren en niet blanken -- een PRODUCT-afweging, geen wetsplicht.** Een eerdere versie
van deze docstring stelde dat AI Act art. 19 de invoer die tot het resultaat leidde als verplicht
logveld noemt. Bij de bron nagemeten is dat onjuist: art. 12(3) eist invoer-logging alleen voor
Annex III punt 1(a) (biometrische identificatie) en dit systeem valt onder punt 4
(personeelsbeheer); art. 19 noemt invoer niet en gaat over bewaartermijn. Waarden leesbaar houden
was dus nooit verplicht.

De keyed digest blijft de keuze, om drie redenen die wel standhouden: het log blijft forensisch
bruikbaar (wie de waarde kent kan de digest narekenen), herhaling van dezelfde waarde blijft
zichtbaar zonder de waarde te kennen, en art. 12(2) vraagt logging die risico-identificatie en
toezicht mogelijk maakt. Let op de prijs: een pseudonym VERWIJDERT het persoonsgegeven niet -- het
blijft een persoonsgegeven onder de AVG, dus art. 5 en art. 17 gelden er onverkort voor (ADR-036
OP-32). Blanken zou die prijs niet hebben.

**Keyed en niet een naakte SHA-256.** Een hash van een e-mailadres heeft lage entropie en is
met een woordenboekaanval terug te rekenen; die blijft dus een persoonsgegeven. HMAC met een
sleutel die alleen de server kent maakt er pseudonimisering van (AVG art. 4(5)).

**Niet `SECRET_KEY`.** Die heeft een gepubliceerde default en is buiten productie optioneel;
wie hem kent kan elke digest terugrekenen.

---

**Deze module vertrouwt de payload op geen enkel punt** -- en dat is een correctie op de eerste
versie, die hem op twee plekken wel vertrouwde. Beide zijn door Gate 2 aangetoond door code te
draaien:

*De tenant komt van de AANROEPER, niet uit de payload.* `tenant_id` is een verplichte
keyword-parameter. In de eerste versie viel de scope terug op `payload.get("tenant_id",
"unscoped")`; twee aanroepers van `execute_tool` geven geen context mee, dus daar deelden alle
tenants een scope en kon het model zijn eigen scope kiezen. Nu is "geen tenant" niet
representeerbaar: de parameter kan niet worden weggelaten en wordt gevalideerd.

*Wat leesbaar blijft volgt uit de WIRING, niet uit een NAAM.* De aanroeper geeft in
`broker_keys` op welke sleutels hij zelf uit de executiecontext heeft geinjecteerd. De eerste
versie had daarvoor een vaste lijst van acht namen, waarvan de broker er in dit pad twee zet --
de overige zes kon het model zelf verzinnen, en `_requested_by` is elders letterlijk
`current_user.email`. Een naamlijst kan niet onderscheiden wie een sleutel schreef; de wiring
kan dat wel.

*Niet idempotent, met opzet.* Een eerdere `_is_already_pseudonymised()` controleerde of een
waarde de VORM `{"hmac": ...}` had zonder naar de inhoud te kijken, en liet daarmee
`{"hmac": "<e-mailadres>"}` verbatim passeren. De functie wordt per uitvoering precies eenmaal
op de rauwe payload toegepast, dus idempotentie was nooit nodig -- alleen de controle die het
lek veroorzaakte. `tests/architecture/test_tool_payloads_are_pseudonymised.py` dwingt af dat
elke sink de uitkomst van EEN aanroep krijgt.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
from collections.abc import Callable, Mapping
from functools import lru_cache
from typing import Any, NamedTuple, TypeAlias, get_args

logger = logging.getLogger(__name__)

#: Omgevingsvariabele met de pseudonimiseringssleutel.
#:
#: Buiten `EPHEMERAL_KEY_ENVIRONMENTS` is hij verplicht en faalt een tool-aanroep zonder hem.
#: Hij staat ook in `config_validator.PRODUCTION_REQUIRED_VARS`, zodat een productie- of
#: staging-proces faalt bij het OPSTARTEN in plaats van bij de eerste tool-aanroep. Die
#: boot-check is bewust pas toegevoegd nadat de sleutel in beide CD-workflows en de
#: blue/green-compose was geprovisioneerd: eerder had hij een luide deploy-fout verplaatst naar
#: een stille toolstoring.
KEY_ENV_VAR = "TOOL_PAYLOAD_PSEUDONYM_KEY"

#: Domeinscheiding, zodat dezelfde sleutel elders niet dezelfde digests oplevert. Dient ook als
#: vaste scrypt-salt in `pseudonymisation_key()`.
#:
#: **v2 sinds 2026-08-04**, omdat de AFLEIDING is gewijzigd (enkele SHA-256 -> scrypt). Digests
#: van voor en na die wijziging zijn onvergelijkbaar; zou het domein `:v1` blijven, dan lijken ze
#: uit dezelfde reeks te komen en zou iemand kunnen concluderen dat twee verschillende digests
#: twee verschillende WAARDEN zijn terwijl het dezelfde waarde onder een andere afleiding is.
#: Deze bump was gratis omdat er nog niets was gedeployed -- na de eerste productie-digest is een
#: wijziging hier een breaking change die de koppelbaarheid over de grens sloopt.
_HMAC_DOMAIN = b"sanskritisetu:tool-payload:v2"

Shape: TypeAlias = Callable[[object], bool]


def _bounded_int(maximum: int) -> Shape:
    """Een geheel getal tussen 0 en `maximum`. `bool` is een int in Python; die hier niet.

    De grens komt van de TOOL en is geen zelfgekozen rond getal -- zie de verwijzingen bij
    `PAYLOAD_POLICY`. Een ruimere grens dan de tool accepteert zou een waarde leesbaar maken die
    de tool daarna alsnog weigert.
    """

    def check(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum

    # De vorm benoemt zichzelf (ADR-036 OP-51, ronde 7). `test_tool_policy_matches_the_tools.py`
    # moet weten welke leesbare waarden een BEREIK zijn en welke een OPSOMMING, want alleen een
    # bereik heeft een geregistreerde herkomst nodig. Dat leidde het eerder af uit de aanwezigheid
    # van de vrije variabele `maximum` in de closure -- een classificatie op een NAAM. Een nieuwe
    # vormsoort (`_bounded_str_len(maxlen)`, `_int_range(lo, hi)`) heeft die naam niet, werd
    # daardoor niet gezien, en de guard bleef groen. Dezelfde vorm-versus-herkomst-fout als in het
    # filter zelf, alleen dan in de guard.
    check.shape_kind = "range"  # type: ignore[attr-defined]
    return check


def _one_of(values: Callable[[], frozenset[str]]) -> Shape:
    """Lidmaatschap van een OPGESOMDE verzameling, lui opgehaald bij de bron.

    Dit is de correctie uit ronde 4. Een patroon voor "een korte code" kan `pending` niet
    onderscheiden van `Jansen`, `123456782` of `j_jansen` -- exact hetzelfde bezwaar waarom
    `role` niet leesbaar mag blijven. En het is niet nodig: de geldige waarden staan al
    gedeclareerd. Lidmaatschap daarvan is een MEETBARE eis; een vormpatroon is een gok bovenop
    een bron van waarheid die al bestaat. Lui, zodat deze module bij het laden geen
    importafhankelijkheid op een domeinmodule krijgt.
    """

    def check(value: object) -> bool:
        return isinstance(value, str) and value in values()

    check.shape_kind = "enumeration"  # type: ignore[attr-defined]  # zie `_bounded_int` (OP-51)

    return check


@lru_cache(maxsize=1)
def _task_statuses() -> frozenset[str]:
    """De geldige taakstatussen, uit de declaratie in `domains/tasks/schemas.py`."""
    from src.domains.tasks.schemas import TaskStatusLiteral

    return frozenset(get_args(TaskStatusLiteral))


@lru_cache(maxsize=1)
def _task_priorities() -> frozenset[str]:
    """De geldige taakprioriteiten, uit dezelfde declaratie."""
    from src.domains.tasks.schemas import TaskPriorityLiteral

    return frozenset(get_args(TaskPriorityLiteral))


@lru_cache(maxsize=1)
def _employee_training_statuses() -> frozenset[str]:
    """De geldige statussen van een toegewezen training, uit de modeldeclaratie.

    Bij de bron opgehaald en niet hier opgesomd: `hr_trainings_repository` toetst aan diezelfde
    tuple, en twee kopieen lopen uit de pas zodra er een status bijkomt. Dan zou een geldige
    waarde hier gedigest worden en ziet niemand meer WELKE status is toegewezen.
    """
    from src.core.models.hr_training_models import EMPLOYEE_TRAINING_STATUSES

    return frozenset(EMPLOYEE_TRAINING_STATUSES)


@lru_cache(maxsize=1)
def _receivable_statuses() -> frozenset[str]:
    """De geldige debiteurstatussen, uit de modeldeclaratie (dezelfde als de CHECK)."""
    from src.core.models.receivable_models import RECEIVABLE_STATUSES

    return frozenset(RECEIVABLE_STATUSES)


@lru_cache(maxsize=1)
def _reminder_kinds() -> frozenset[str]:
    """De soorten brief, uit het sjabloon dat ze rendert."""
    from src.core.tool_broker.payment_reminder_template import REMINDER_KINDS

    return frozenset(REMINDER_KINDS)


# Hier stond `_is_uuid()`, een vormtoets die een UUID leesbaar zou houden. Verwijderd
# 2026-08-04 (ronde 5): geen enkele `readable` in `PAYLOAD_POLICY` gebruikte hem, terwijl drie
# docstrings UUID wel als leesbare vorm adverteerden. Dat gat is de verkeerde kant op gevaarlijk:
# wie het verschil ziet, concludeert uit de documentatie dat UUID's leesbaar HOREN te zijn en zet
# hem aan -- en dan is een `task_id` een leesbare, stabiele correlatiesleutel in een onuitwisbaar
# log, zonder dat een test die beslissing afdwingt. Terugzetten mag, maar dan met een expliciete
# regel in `PAYLOAD_POLICY` en een test die vastlegt WAAROM die koppeling nodig is.


class ToolPolicy(NamedTuple):
    """Wat er van de payload van een tool leesbaar mag worden vastgelegd.

    Twee verschillende vragen, dus twee velden.

    `params` -- de sleutelNAMEN die de tool zelf declareert (accepteert of expliciet weigert).
    Alleen deze namen mogen verbatim in een log staan. Ook een sleutel is modeloutput, en een
    vormpatroon liet `Jan_Jansen_salaris_82000` ongehinderd door: dat ziet er nu eenmaal uit als
    een parameternaam. Een vorm kan niet antwoorden WIE de sleutel schreef; deze lijst wel. Een
    naam die er niet in staat wordt zelf een pseudonym, stabiel per tenant, zodat "hoeveel
    argumenten waren er en welke komen terug" traceerbaar blijft (AI Act art. 12(2)).

    `readable` -- de deelverzameling waarvan ook de WAARDE leesbaar mag blijven, met de eis
    waaraan die waarde moet voldoen. Al het overige wordt een digest.
    """

    params: frozenset[str]
    readable: dict[str, Shape]


#: Per tool: het vocabulaire en de leesbare waarden. Een tool die hier niet in staat krijgt een
#: LEGE policy -- dan worden zowel sleutelnamen als waarden gedigest. De default is
#: pseudonimiseren, niet doorlaten.
#:
#: `role` heeft geen leesbare waarde: een rolnaam en een persoonsnaam zijn qua vorm niet te
#: onderscheiden ("Finance Analyst" en "Jan Jansen" passen op hetzelfde patroon). De
#: traceerbaarheid blijft: dezelfde rol geeft dezelfde digest.
#:
#: `tests/architecture/test_tool_payloads_are_pseudonymised.py::
#: test_every_executable_tool_has_a_reviewed_allowlist` eist dat elke uitvoerbare tool hier een
#: expliciete regel heeft, zodat een nieuwe tool een beoordeling vraagt in plaats van stil te
#: degraderen.
PAYLOAD_POLICY: dict[str, ToolPolicy] = {
    # ALS-piloot. Gelezen: `role` (hr_registry.py:162), `limit` (:223), `offset` (:224).
    # Expliciet geweigerd maar wel deel van het vocabulaire: `_UNSUPPORTED_FILTERS` (:72-81).
    # Grenzen: MAX_LIMIT=1000 / MAX_OFFSET=100_000 (:63-64).
    "query_hr_database": ToolPolicy(
        params=frozenset({"role", "limit", "offset", "department", "employee_id"}),
        readable={"limit": _bounded_int(1_000), "offset": _bounded_int(100_000)},
    ),
    # Zelfde vocabulaire als `query_hr_database`: dezelfde module leest de payload, dezelfde
    # weigeringen (`_UNSUPPORTED_FILTERS`) gelden, dezelfde grenzen. Een eigen regel en geen
    # verwijzing, want een gedeelde regel zou bij een wijziging aan de ene tool stil de andere
    # meenemen.
    "analyze_skill_gap": ToolPolicy(
        params=frozenset({"role", "limit", "offset", "department", "employee_id"}),
        readable={"limit": _bounded_int(1_000), "offset": _bounded_int(100_000)},
    ),
    # De eerste SCHRIJFtool van de HR-registry (2026-09-21). Gelezen in
    # `hr_registry.py::_schedule_training`: `user_email`, `training_name`, `status`.
    #
    # `user_email` is NIET leesbaar en dat is hier de kern van de zaak: het is het enige veld in
    # deze hele tabel dat per definitie een persoon aanwijst. Een digest houdt de traceerbaarheid
    # (dezelfde medewerker geeft dezelfde digest binnen dezelfde tenant) zonder het adres in een
    # onuitwisbaar log te zetten. `upsert_employee_trainings` laat het adres om dezelfde reden uit
    # zijn foutmeldingen, en de tool geeft het niet terug in zijn antwoord -- drie lagen die
    # elkaar NIET vervangen: deze regel dekt de PAYLOAD, de andere twee dekken het ANTWOORD.
    #
    # `training_name` evenmin, op dezelfde grond als `role` hierboven: een cursusnaam en een
    # persoonsnaam zijn qua VORM niet te onderscheiden, en dit veld is modeloutput.
    #
    # `status` wel: dat is een opgesomde verzameling met een bron van waarheid, en juist deze
    # waarde maakt het auditspoor bruikbaar -- "er is iets toegewezen" is iets anders dan "er is
    # iets op afgerond gezet".
    "schedule_training": ToolPolicy(
        params=frozenset({"user_email", "training_name", "status"}),
        readable={"status": _one_of(_employee_training_statuses)},
    ),
    # Debiteurentools (dag 2). Gelezen in `receivables_registry.py`: `_LIST_FIELDS` en
    # `_SEND_FIELDS`. Leesbaar alleen wat geen persoon of vrije tekst is: de paginering, de
    # status en de soort brief. Het adres, het onderwerp en de tekst worden een digest -- de
    # volledige brief staat in `hitl_tickets` (voor de goedkeurder) en in `outgoing_messages`
    # (wat er vertrekt), niet in een onuitwisbaar log.
    "list_receivables": ToolPolicy(
        params=frozenset({"status", "limit", "offset"}),
        readable={
            "limit": _bounded_int(200),
            "offset": _bounded_int(100_000),
            "status": _one_of(_receivable_statuses),
        },
    ),
    "send_payment_reminder": ToolPolicy(
        params=frozenset(
            {"receivable_id", "kind", "recipient_name", "recipient_email", "subject", "body"}
        ),
        readable={"kind": _one_of(_reminder_kinds)},
    ),
    # Crediteurentools (crediteuren dag 2). Gelezen in `payables_registry.py`: `_RECORD_FIELDS` en `_PROPOSE_FIELDS`. Niets is
    # leesbaar: een leverancier, een IBAN, een factuurnummer, een bedrag en de zin met het waarom zijn persoons- of bedrijfsgegevens
    # of vrije tekst. Ze worden een digest in het log; de volledige gegevens staan in `hitl_tickets` (voor de goedkeurder) en in
    # `payables` (wat er is vastgelegd), niet in een onuitwisbaar log.
    "record_supplier_invoice": ToolPolicy(params=frozenset({"bestand_id"}), readable={}),
    # Betaalvoorstel (crediteuren dag 3): de regels bevatten leveranciersnamen, gemaskeerde IBAN's en bedragen. Digest in het log; de
    # volledige lijst staat in `hitl_tickets` voor de goedkeurder.
    "propose_payment_run": ToolPolicy(
        params=frozenset(
            {"regels", "totaal_cents", "drempel_cents", "vier_ogen_vereist", "waarom"}
        ),
        readable={},
    ),
    "propose_supplier_invoice": ToolPolicy(
        params=frozenset(
            {
                "bestand_id",
                "supplier_id",
                "supplier_name",
                "iban",
                "bekend_iban",
                "invoice_number",
                "amount_cents",
                "currency",
                "invoice_date",
                "due_date",
                "waarom",
            }
        ),
        readable={},
    ),
    # Business-tools. `create_task`/`update_task` valideren via TaskCreate/TaskUpdate
    # (domains/tasks/schemas.py:15-50); die velden vormen het vocabulaire. `list_tasks` en
    # `delete_task` lezen rechtstreeks uit de payload (business_registry.py:176-179, :206).
    "create_task": ToolPolicy(
        params=frozenset(
            {
                "title",
                "description",
                "status",
                "priority",
                "created_by",
                "assigned_agent_id",
                "payload",
                "parent_task_id",
                "external_ref",
                "due_at",
            }
        ),
        readable={"priority": _one_of(_task_priorities), "status": _one_of(_task_statuses)},
    ),
    # `skip`, NIET `offset` -- business_registry.py:178. De eerste versie van deze tabel had
    # `offset`, dus de echte parameter werd gedigest en een niet-bestaande bleef leesbaar. Een
    # aanname in plaats van een meting, in precies de tabel die dat moet voorkomen.
    "list_tasks": ToolPolicy(
        params=frozenset({"status", "assigned_agent_id", "skip", "limit"}),
        readable={
            "skip": _bounded_int(100_000),
            "limit": _bounded_int(1_000),
            "status": _one_of(_task_statuses),
        },
    ),
    "update_task": ToolPolicy(
        params=frozenset(
            {
                "task_id",
                "title",
                "description",
                "status",
                "priority",
                "assigned_agent_id",
                "payload",
                "result",
                "parent_task_id",
                "external_ref",
                "due_at",
                # HIGH-risk tool: business_registry.py:228 popt dit als controleveld.
                "_hitl_ticket_ref",
            }
        ),
        readable={
            "priority": _one_of(_task_priorities),
            "status": _one_of(_task_statuses),
        },
    ),
    "delete_task": ToolPolicy(
        params=frozenset({"task_id", "_hitl_ticket_ref"}), readable={}
    ),
    # Lokale tools. Gelezen: local_registry.py:104 (path), :126 (command), :168-170
    # (to/subject/body), :230 (prompt). `model` stond eerder in deze tabel en wordt door
    # `local__llm_generate` niet gelezen -- een fantoomnaam.
    #
    # Lege `readable` en niet weggelaten: dat maakt zichtbaar dat het een beoordeling is.
    # `send_email` draagt een adres en een berichttekst, `llm_generate` een prompt. Daar hoort
    # niets van in het klare in een permanente opslag.
    #
    # `local__run_shell` stond hier tot 2026-08-11 en is verwijderd samen met de tool zelf
    # (ADR-036 OP-126): een prefix-controle plus `create_subprocess_shell` maakte elke
    # commando-allowlist waardeloos.
    "local__send_email": ToolPolicy(frozenset({"to", "subject", "body"}), {}),
    "local__llm_generate": ToolPolicy(frozenset({"prompt"}), {}),
    "local__read_file": ToolPolicy(frozenset({"path"}), {}),
    # Test-tools. `test__echo` echoot de HELE payload en leest geen enkele benoemde sleutel
    # (test_tools.py:16), dus zijn vocabulaire is leeg -- `message` stond hier eerder en was een
    # fantoom. `test__fail` leest `message` (:23), `test__slow` leest `delay_seconds` (:29) --
    # dat laatste stond hier als `seconds`, dezelfde klasse fout als `offset`/`skip`.
    "test__echo": ToolPolicy(frozenset(), {}),
    "test__fail": ToolPolicy(frozenset({"message"}), {}),
    "test__slow": ToolPolicy(
        frozenset({"delay_seconds"}), {"delay_seconds": _bounded_int(3_600)}
    ),
}

_EMPTY_POLICY = ToolPolicy(frozenset(), {})

_cached_key: bytes | None = None
_key_lock = threading.Lock()


def _configured_key() -> str | None:
    """De geconfigureerde sleutel, of None. Apart zodat een test hem kan vervangen."""
    return os.environ.get(KEY_ENV_VAR) or None


#: De ENIGE omgevingen waar een ontbrekende sleutel mag worden opgevangen met een ephemere.
#: Een allowlist en geen blocklist: `is_production()` matcht alleen "production", terwijl de
#: vloot ook `staging`, `blue` en `green` gebruikt -- en blue/green is een PRODUCTIETECHNIEK.
#: Met een blocklist vielen die stil open op een per-proces sleutel, en dan geeft dezelfde
#: waarde per worker een andere digest; precies de koppelbaarheid waarop het
#: art.-12(2)-argument rust valt dan weg zonder dat iemand het merkt.
EPHEMERAL_KEY_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test", "local"})

#: Onder deze lengte weigeren: met bekende klaartekst-paren (opsombare velden als `status` of
#: `None`) is een korte passphrase offline te kraken tegen een hash per gok.
MIN_KEY_LENGTH = 32

#: Minimaal aantal VERSCHILLENDE tekens. Bewust laag, en dat getal is gemeten en niet gekozen.
#:
#: Over 200.000 uitkomsten per generator: `token_urlsafe(32)` zakt niet onder 22 verschillende
#: tekens, maar `token_hex(16)` zakt tot 8 -- zijn alfabet heeft immers maar 16 symbolen. Een
#: drempel boven de 8 weigert dus een sleutel met 128 bits entropie en laat productie niet meer
#: opstarten. Daarom ligt de drempel op 8 en doet `_repeats_a_block()` het echte werk: met
#: alleen dit getal is `"abcdefgh" * 6` (ook 8 verschillende tekens) niet van een geldige
#: hex-sleutel te onderscheiden.
MIN_DISTINCT_CHARACTERS = 8

#: scrypt-parameters. `n=2**14` met `r=8`, `p=1` kost 128 * n * r * p = 16 MB. Bewust NIET
#: `2**15`: dat is 32 MB en tikt daarmee tegen de standaard `maxmem` van OpenSSL aan, waardoor
#: de afleiding faalt met een obscure OpenSSL-fout in plaats van te werken.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DERIVED_KEY_BYTES = 32


def _repeats_a_block(value: str) -> int | None:
    """De lengte van het herhaalde blokje, of None.

    Ook AFGEKAPTE herhalingen. De klassieke truc `value in (value + value)[1:-1]` ziet alleen
    EXACTE herhalingen en laat `("SanskritiSetu" * 4)[:45]` ongehinderd door -- gemeten tijdens
    het bouwen van deze check, en juist dat is wat een mens typt.
    """
    length = len(value)
    for period in range(1, length // 2 + 1):
        if value == (value[:period] * (length // period + 1))[:length]:
            return period
    return None


def key_strength_problem(configured: str) -> str | None:
    """None als de sleutel bruikbaar is, anders de reden in een leesbare zin.

    **Deze functie bestaat zodat de runtime en de boot-check niet uiteen kunnen lopen.**
    `pseudonymisation_key()` gooit ermee, `config/config_validator.py` meldt ermee. Stond de eis
    maar op een van de twee plekken, dan haalt een zwakke sleutel de boot-check en weigert de
    runtime hem daarna -- een geslaagde deploy waarna ELKE tool-aanroep faalt. Dat is precies de
    stille storing die de boot-check moest voorkomen, en de reden dat de lengte-eis daar al staat.

    **Wat dit NIET is: een raadbaarheids-orakel.** `sanskritisetu-staging-key-2026-08` heeft 16
    verschillende tekens en is geen herhaling, dus hij komt hier door -- terwijl hij te raden is.
    Een dictionary- of patrooncheck zou dat moeten vangen en is bewust buiten scope: brittle, en
    de echte verdediging is dat de sleutel met `secrets.token_urlsafe(32)` wordt gegenereerd (zo
    staat het in de deploy-instructie en in `docs/BACKLOG.md` DEPLOY-001).

    **Wat deze functie WEL vangt, precies drie klassen** (Gate 2 ronde 6, F2 -- de eerdere
    formulering "de MECHANISCH zwakke sleutel" beloofde meer dan hij levert):
      1. te kort (`< MIN_KEY_LENGTH`);
      2. te arm alfabet (`< MIN_DISTINCT_CHARACTERS` verschillende tekens);
      3. periodieke herhaling van een blok, ook afgekapt.
    Daarbuiten komt mechanisch zwak materiaal er wel door. Gemeten: `"CHANGEME" + "!" * 30`
    (38 tekens, 8 verschillende) en `"a" * 32 + "bcdefgh"` (39 tekens, 8 verschillende) worden
    BEIDE geaccepteerd -- ze halen de lengte, halen precies de alfabet-eis, en zijn geen zuivere
    blokherhaling. Een verscherping op "meest frequente teken > helft van de string" zou die twee
    vangen (79 procent en 82 procent), maar vraagt eerst een valse-positieven-meting over de vier
    generatoren; niet ongemeten toevoegen.

    **Waarom de drempel op 8 staat en niet op een redelijk lijkende 10.** Exact uitgerekend (niet
    gesampled) met inclusie-exclusie over het aantal strings van lengte n over een alfabet van 16
    dat hoogstens k verschillende tekens gebruikt, voor de zwakste legitieme generator
    `token_hex(16)` (32 hex-tekens):
      - hoogstens  7 verschillend: 3,55e-08 -- 1 op 28.202.626
      - hoogstens  8 verschillend: 2,71e-06 -- 1 op 369.522
      - hoogstens 10 verschillend: 1,72e-03 -- **1 op 581**
    Met drempel 10 zou productie dus ongeveer een keer per 581 sleutelrotaties niet meer opstarten
    op een volkomen geldige sleutel. 8 ligt aan de goede kant van die klif, en dat is de eigenlijke
    onderbouwing. Een eis die een echte sleutel afwijst is erger dan geen eis.

    De committe test (`tests/unit/tool_broker/test_pseudonymisation_key_strength.py`) toetst dit
    op 300 sleutels per generator over de VIER generatoren in `KEY_GENERATORS`
    (`token_urlsafe` 24/32, `token_hex` 16/32) -- nul afwijzingen, tegen runtime EN boot-check.
    """
    if len(configured) < MIN_KEY_LENGTH:
        return (
            f"is korter dan {MIN_KEY_LENGTH} tekens. Met bekende klaartekst-paren is zo'n waarde "
            "offline te kraken."
        )

    distinct = len(set(configured))
    if distinct < MIN_DISTINCT_CHARACTERS:
        return (
            f"heeft maar {distinct} verschillende tekens (minimaal {MIN_DISTINCT_CHARACTERS}). "
            "Lengte alleen is geen sterkte: een lange, arme sleutel is even goedkoop te raden "
            "als een korte."
        )

    period = _repeats_a_block(configured)
    if period is not None:
        return (
            f"is een herhaling van hetzelfde blokje van {period} tekens. De effectieve sterkte is "
            f"die van {period} tekens, niet die van {len(configured)}."
        )

    return None


def _environment() -> str:
    """De EXPLICIET gezette omgeving, genormaliseerd. Leeg als niemand hem heeft gezet.

    Bewust `os.environ` en niet `get_settings().environment`: die laatste heeft de default
    "development", en dat is een van de omgevingen die een ephemere sleutel mag gebruiken. Een
    proces waar `ENVIRONMENT` simpelweg vergeten is, zou daarmee stil in de ontwikkelmodus
    vallen -- en dan geeft dezelfde waarde per worker en na elke recycle (ADR-011) een andere
    digest. Precies de koppelbaarheid waarop het art.-12(2)-argument rust, weg zonder dat iemand
    het merkt. Een ontbrekende omgeving is dus geen ontwikkelomgeving.
    """
    return str(os.environ.get("ENVIRONMENT") or "").strip().lower()


def _allows_ephemeral_key() -> bool:
    """Mag een ontbrekende sleutel hier met een ephemere worden opgevangen?"""
    return _environment() in EPHEMERAL_KEY_ENVIRONMENTS


#: Omgevingsvariabele die het vastleggen van de ECHTE payload aanzet, voor het debuggen van een
#: agent die zich vreemd gedraagt. Standaard uit.
#:
#: Overgenomen van de OpenTelemetry GenAI-conventie, waar het vastleggen van prompt- en
#: tool-inhoud standaard uit staat en expliciet aangezet moet worden
#: (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`). Gehardend op twee punten die OTel niet
#: specificeert: hij wordt alleen gehonoreerd in omgevingen zonder echte persoonsgegevens, en
#: elke zo vastgelegde regel zegt zelf dat hij onbewerkt is.
CAPTURE_ENV_VAR = "TOOL_PAYLOAD_CAPTURE_CONTENT"

#: De ENIGE waarden die de opt-in aanzetten. Een allowlist en geen `bool(os.environ.get(...))`:
#: die laatste maakt van de string "false" een `True`, en dan staat het aan terwijl de
#: configuratie zegt dat het uit is.
_CAPTURE_TRUE_TOKENS: frozenset[str] = frozenset({"1", "true", "yes", "on"})

#: De omgevingen waar de opt-in wordt gehonoreerd. Bewust DEZELFDE verzameling als voor de
#: ephemere sleutel, want het is dezelfde vraag: kan hier een echt persoonsgegeven langskomen?
#: Wie de inhoud wil vastleggen in een omgeving MET echte gegevens moet deze verzameling
#: wijzigen -- zichtbaar in de diff, onder een architectuurtest, en met een DPIA-onderbouwing.
#: Dat is de juiste drempel; een omgevingsvariabele die iemand in een paniekmoment omzet is het
#: niet.
CONTENT_CAPTURE_ENVIRONMENTS: frozenset[str] = EPHEMERAL_KEY_ENVIRONMENTS

#: Sleutel waaronder een onbewerkt vastgelegde regel dat van zichzelf zegt. Alleen aanwezig in
#: die modus: de afwezigheid betekent gepseudonimiseerd, en dat is buiten
#: `CONTENT_CAPTURE_ENVIRONMENTS` de enige mogelijke modus. Een model kan de marker niet
#: vervalsen -- in de standaardmodus hoort `_redaction` bij geen enkel tool-vocabulaire, dus de
#: sleutelnaam wordt zelf een pseudonym; en in de opt-in-modus zet de broker hem als LAATSTE en
#: overschrijft daarmee wat er ook stond.
REDACTION_MODE_KEY = "_redaction"
VERBATIM_MODE = "verbatim"

_capture_warned = False


def _content_capture_enabled() -> bool:
    """Mag de ECHTE payload worden vastgelegd? Een beslispunt, zodat er een plek is om te auditen.

    Vier keer nee voordat het ja wordt: de variabele moet gezet zijn, met een expliciet token uit
    de allowlist, in een omgeving die het toestaat -- en staat hij aan waar dat niet mag, dan
    wordt hij GENEGEERD met een foutmelding. Uit en luid, niet uit en stil.
    """
    global _capture_warned

    raw = os.environ.get(CAPTURE_ENV_VAR)
    if raw is None or raw.strip().lower() not in _CAPTURE_TRUE_TOKENS:
        return False

    environment = _environment()
    if environment not in CONTENT_CAPTURE_ENVIRONMENTS:
        logger.error(
            "%s staat aan in omgeving '%s' en wordt GENEGEERD. Onbewerkte tool-payloads worden "
            "daar niet vastgelegd; die omgeving kan echte persoonsgegevens bevatten. Toegestaan "
            "in: %s.",
            CAPTURE_ENV_VAR,
            environment or "<niet gezet>",
            sorted(CONTENT_CAPTURE_ENVIRONMENTS),
        )
        return False

    if not _capture_warned:
        # Een keer per proces en niet per aanroep: bij BE-AGT-044 is een per-aanroep-waarschuwing
        # teruggedraaid omdat het detectiesignaal in ruis verdronk.
        logger.warning(
            "%s staat aan in omgeving '%s': tool-payloads worden ONBEWERKT vastgelegd, met "
            "%s='%s' in elke regel. Alleen bedoeld voor debuggen met testdata.",
            CAPTURE_ENV_VAR,
            environment,
            REDACTION_MODE_KEY,
            VERBATIM_MODE,
        )
        _capture_warned = True

    return True


def reset_capture_warning() -> None:
    """Vergeet dat er al gewaarschuwd is. Alleen bedoeld voor tests."""
    global _capture_warned
    _capture_warned = False


def reset_key_cache() -> None:
    """Vergeet de gecachte sleutel. Alleen bedoeld voor tests."""
    global _cached_key
    with _key_lock:
        _cached_key = None


def pseudonymisation_key() -> bytes:
    """De HMAC-sleutel.

    Buiten `EPHEMERAL_KEY_ENVIRONMENTS` is `KEY_ENV_VAR` verplicht: ontbreekt hij, dan volgt een
    `RuntimeError`. Bewust geen terugval op een naakte hash en niet op `SECRET_KEY`; beide zijn
    voor lage-entropie-waarden terug te rekenen en geven dus schijnbescherming.

    Daarbinnen een per-proces willekeurige sleutel. Digests zijn dan niet vergelijkbaar tussen
    processen -- voor ontwikkeling geen bezwaar en veiliger dan een bekende constante.

    Onder een lock: zonder dat kunnen twee threads elk hun eigen sleutel toewijzen, en dan
    geldt "dezelfde waarde geeft dezelfde digest" niet meer -- precies de eigenschap waarop het
    art.-12(2)-argument rust.
    """
    global _cached_key

    with _key_lock:
        if _cached_key is not None:
            return _cached_key

        configured = _configured_key()
        if configured:
            problem = key_strength_problem(configured)
            if problem is not None:
                raise RuntimeError(
                    f"{KEY_ENV_VAR} {problem} Genereer hem met `secrets.token_urlsafe(32)`."
                )
            # scrypt en niet een enkele SHA-256-ronde: die kost een aanvaller met een
            # woordenlijst niets, en er ZIJN bekende klaartekst-paren -- opsombare velden als
            # `status` staan leesbaar in hetzelfde log als de digests.
            #
            # VASTE salt, en dat is geen omissie. Een willekeurige salt maakt de afleiding
            # per proces anders, en dan geeft dezelfde waarde een andere digest na elke
            # worker-recycle (ADR-011). Dat sloopt stil de koppelbaarheid waarop het
            # art.-12(2)-argument rust -- dezelfde reden waarom een ontbrekende sleutel buiten
            # development hard faalt in plaats van een ephemere te verzinnen. De salt hoeft
            # hier geen geheim te zijn: hij scheidt domeinen, de sleutel doet het geheime werk.
            _cached_key = hashlib.scrypt(
                configured.encode("utf-8"),
                salt=_HMAC_DOMAIN,
                n=_SCRYPT_N,
                r=_SCRYPT_R,
                p=_SCRYPT_P,
                dklen=_DERIVED_KEY_BYTES,
            )
            return _cached_key

        if not _allows_ephemeral_key():
            raise RuntimeError(
                f"{KEY_ENV_VAR} is niet gezet en omgeving '{_environment()}' staat geen "
                "ephemere sleutel toe. Zonder eigen sleutel kan een tool-payload niet "
                "gepseudonimiseerd worden, en een naakte hash of SECRET_KEY is geen "
                "alternatief: beide zijn voor lage-entropie-waarden terug te rekenen."
            )

        logger.warning(
            "%s is niet gezet; buiten productie wordt een per-proces sleutel gebruikt.",
            KEY_ENV_VAR,
        )
        _cached_key = secrets.token_bytes(32)
        return _cached_key


def _tenant_scope(tenant_id: int) -> bytes:
    """De tenant-domeinscheiding, met validatie.

    Fail-closed en geen terugval op een gedeelde constante: dezelfde persoon zou dan in twee
    tenants dezelfde digest krijgen en over die grens correleerbaar zijn. Een per-proces
    willekeurige terugval is evenmin een optie -- dat sloopt stil de koppelbaarheid waarop het
    art.-12(2)-argument rust, exact de reden waarom de SLEUTEL buiten development ook hard
    faalt.
    """
    if isinstance(tenant_id, bool) or not isinstance(tenant_id, int):
        raise ValueError(
            f"tenant_id moet een int zijn voor de pseudonimiseringsscope, niet "
            f"{type(tenant_id).__name__}. De scope mag nooit uit de payload komen: die is "
            "modeloutput."
        )
    if tenant_id <= 0:
        raise ValueError(
            f"tenant_id {tenant_id} is geen geldige tenant voor de pseudonimiseringsscope."
        )
    return str(tenant_id).encode("utf-8")


def _digest(value: object, tenant_scope: bytes) -> dict[str, str]:
    """Keyed, tenant-gescheiden digest van een payload-waarde."""
    try:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        # Geen `default=str`: dat levert voor een niet-serialiseerbaar object een repr met
        # geheugenadres op, dus per run een andere digest voor dezelfde logische waarde. Een
        # vaste marker houdt de digest reproduceerbaar, wat het hele punt is.
        canonical = f"<unserialisable:{type(value).__name__}>"

    mac = hmac.new(
        pseudonymisation_key(),
        _HMAC_DOMAIN + b":" + tenant_scope + b":" + canonical.encode("utf-8"),
        hashlib.sha256,
    )
    return {"hmac": mac.hexdigest()}


def _digest_key(key: str, tenant_scope: bytes) -> str:
    """Pseudonym voor een sleutelNAAM die niet op een parameternaam lijkt.

    Eigen domeinscheiding (`:key:`), zodat een sleutelpseudonym nooit gelijk kan zijn aan een
    waardedigest. Dezelfde naam geeft binnen een tenant dezelfde uitkomst, dus de VORM van de
    aanroep blijft traceerbaar -- hoeveel argumenten er waren en welke terugkeren -- zonder de
    naam zelf vast te leggen.
    """
    mac = hmac.new(
        pseudonymisation_key(),
        _HMAC_DOMAIN + b":key:" + tenant_scope + b":" + key.encode("utf-8"),
        hashlib.sha256,
    )
    return f"<k:{mac.hexdigest()[:16]}>"


#: De sleutels die `ToolBrokerService.execute_tool` zelf uit de EXECUTIECONTEXT in de payload
#: schrijft, voordat de HITL-poort draait (ADR-036 OP-75).
#:
#: Deze horen NIET in `approval_binding`. Bij goedkeuren bestaan ze nog niet -- `create_hitl_request`
#: bouwt de payload uit `action_params` plus servermetadata -- en bij uitvoeren wel. Telden ze mee,
#: dan verschilde de binding aan de twee kanten en matchte de UPDATE in `redeem` nul rijen: elke
#: menselijke goedkeuring was stil onverzilverbaar en de actie bleef permanent geblokkeerd.
#:
#: Geen verlies aan strengheid: de tenant zit al in de domeinscheiding van de HMAC EN in de WHERE
#: van `redeem`, en wie het verzoek deed staat in `_requested_by`.
#:
#: `tests/unit/tool_broker/test_hitl_approval_is_bounded.py` leest de injectieplekken in
#: `service.py` met de AST en dwingt af dat deze verzameling daarmee gelijk blijft. Zo is dit
#: wiring en geen naamlijst -- het onderscheid dat OP-65 en ronde 2 van deze sprint al kostte.
BROKER_INJECTED_KEYS = frozenset({"tenant_id", "user_id"})


def approval_binding(tool_name: str, payload: Mapping[str, object], *, tenant_id: int) -> str:
    """Een keyed binding over WELKE tool met WELKE parameters is goedgekeurd (ADR-036 OP-63).

    **Waarom dit bestaat.** De HITL-poort toetste alleen `status == "approved"`. Een goedgekeurde
    ticketverwijzing was daarmee bruikbaar voor elke andere HIGH-risk tool met elke andere
    parameterset -- en `ToolRiskClassifier` zet onbekende tools standaard op HIGH, dus dat gold
    voor alles. Deze waarde legt de goedkeuring vast op precies een handeling.

    **Wat er WEL en NIET in meetelt.** Alleen de parameters die het MODEL schreef. Eruit gaan de
    servermetadata met een `_`-prefix (`_decision_id`, `_requested_at`, ...) en de sleutels die de
    broker zelf uit de executiecontext injecteert (`BROKER_INJECTED_KEYS`). Die laatste bestaan bij
    goedkeuren nog niet en bij uitvoeren wel; meetellen maakte elke goedkeuring onverzilverbaar
    (ADR-036 OP-75).

    **Waarom alleen sleutels zonder underscore-prefix.** De payload van een ticket bevat naast de
    tool-parameters ook boekhouding die de server erbij zet (`_decision_id`, `_requested_at`, ...)
    en die bij uitvoering niet opnieuw wordt aangeboden. Zou die meetellen, dan kan een legitieme
    goedkeuring nooit worden verzilverd. De parameters zelf hebben geen underscore-prefix; dat is
    de conventie die `business_registry` en `redact_for_publication` beide al hanteren.

    **Waarom een eigen domeinscheiding.** `:binding:` zorgt dat deze waarde nooit gelijk kan zijn
    aan een waardedigest (`_digest`) of een sleutelpseudonym (`_digest_key`). Hetzelfde principe
    als daar, en om dezelfde reden: twee betekenissen mogen niet op dezelfde bytes uitkomen.

    Faalt hard zonder sleutel, net als de rest van deze module. Een binding die stil terugvalt op
    een constante zou elke goedkeuring weer universeel maken -- precies het defect dat dit dicht.
    """
    parameters = {
        k: v
        for k, v in payload.items()
        if not k.startswith("_") and k not in BROKER_INJECTED_KEYS
    }
    try:
        canonical = json.dumps(
            {"tool": tool_name, "params": parameters}, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        # HARDE FOUT, geen terugval (ADR-036 OP-96). De eerste versie viel terug op een vorm
        # ZONDER parameters. Gemeten gevolg: twee volstrekt verschillende aanroepen kwamen dan op
        # dezelfde binding uit -- een botsing-met-opzet in een veiligheidsprimitief.
        #
        # De rechtvaardiging in het oude commentaar ("anders verzilvert een legitieme goedkeuring
        # nooit") beschrijft precies de situatie waarin WEIGEREN het juiste antwoord is: een
        # parameter die niet te serialiseren is, is ook niet vast te leggen als wat er is
        # goedgekeurd. Fail-closed is hier goedkoop -- de goedkeurkant komt altijd uit JSONB en is
        # dus altijd serialiseerbaar.
        raise ValueError(
            f"Kan de goedkeuringsbinding voor {tool_name!r} niet berekenen: een parameter is niet "
            f"serialiseerbaar ({type(exc).__name__}). Een goedkeuring die niet vast te leggen is, "
            "hoort niet verzilverbaar te zijn."
        ) from exc

    mac = hmac.new(
        pseudonymisation_key(),
        _HMAC_DOMAIN + b":binding:" + _tenant_scope(tenant_id) + b":" + canonical.encode("utf-8"),
        hashlib.sha256,
    )
    return mac.hexdigest()


def value_digest(value: str, *, tenant_id: int) -> str:
    """Een keyed, tenant-gescheiden digest van EEN losse waarde (ADR-036 OP-78).

    `redact_for_publication` werkt op een payload en pseudonimiseert ook de SLEUTELS; voor een
    onbekende tool levert dat een lege policy op en verdwijnt de waarde uit het resultaat. Voor een
    enkele waarde is dit het juiste primitief.

    Eigen domeinscheiding (`:value:`), zodat deze uitkomst nooit gelijk kan zijn aan een
    waardedigest uit een payload, aan een sleutelpseudonym of aan een goedkeuringsbinding. Dezelfde
    regel als bij `_digest_key` en `approval_binding`, en om dezelfde reden: twee betekenissen mogen
    niet op dezelfde bytes uitkomen.
    """
    mac = hmac.new(
        pseudonymisation_key(),
        _HMAC_DOMAIN + b":value:" + _tenant_scope(tenant_id) + b":" + value.encode("utf-8"),
        hashlib.sha256,
    )
    return mac.hexdigest()


def digest_result(value: object, *, tenant_id: int) -> dict[str, str] | None:
    """Een keyed, tenant-gescheiden digest van een tool-RESULTAAT (ADR-036 OP-29).

    `redact_for_publication` werkt op de INVOER: een dict met bekende parameternamen per tool,
    waarvoor een allowlist zinvol is. Een resultaat heeft die vorm niet -- bij `local__read_file`
    is het bestandsinhoud, bij `local__llm_generate` modeltekst, en beide zijn evengoed
    modeloutput als de invoer zelf. `value_digest` verwacht een `str`; een resultaat is vaak een
    dict of `None`. Dit primitief hergebruikt dezelfde keyed-HMAC-machinerie (`_digest`) maar
    accepteert elk JSON-serialiseerbaar object en geeft `None` terug voor `None`, zodat een
    afwezig resultaat afwezig blijft in plaats van een digest van "null" te worden.

    Zelfde primitief voor `result`, `tool_output` en `error_detail`/`error`: alle vier zijn
    ongefilterde modeloutput die naar dezelfde bewarende sinks gaat (`_publish_tool_event`,
    `log_execution`, `tool_execution_history`). Zie
    `tests/architecture/test_tool_results_are_registered_as_open.py` voor de volledige lijst.
    """
    if value is None:
        return None
    return _digest(value, _tenant_scope(tenant_id))


def safe_digest_result(value: object, *, tenant_id: int) -> dict[str, str] | None:
    """`digest_result`, maar redactie zelf falen mag de foutafhandeling niet omverwerpen.

    Bedoeld voor gebruik binnen een `except`-tak (of een `finally`-blok). `redact_for_publication`
    op de PAYLOAD faalt AL, hard en met opzet, zodra `pseudonymisation_key()` ontbreekt -- geen
    tool draait zonder sleutel. Die `RuntimeError` komt in dezelfde except-tak terecht die het
    RESULTAAT/de foutmelding probeert te redigeren. Riep die tak `digest_result` rechtstreeks aan,
    dan faalde de sleutel-opvraging daar OPNIEUW, en die TWEEDE `RuntimeError` verving de eerste --
    in een `except`-tak wordt de aanroeper dan de verkeerde exception-klasse gewaar (gemeten:
    `test_pseudonymisation_leaks.py::TestAMissingKeyAbortsTheExecution` kreeg een rauwe
    `RuntimeError` uit deze module in plaats van de bedoelde `ToolExecutionException`), en in een
    `finally`-blok VERVANGT een nieuwe exception zelfs een al onderweg zijnde HTTPException.
    Terugvallen op `None` is hier veilig: dat publiceert minder, nooit de rauwe waarde.
    """
    try:
        return digest_result(value, tenant_id=tenant_id)
    except (RuntimeError, ValueError) as exc:
        # Alleen de twee gedocumenteerde, verwachte oorzaken: pseudonymisation_key() (geen
        # sleutel, RuntimeError) en _tenant_scope() (ongeldige tenant_id, ValueError). Een
        # bredere except zou een ONVERWACHTE bug in _digest() zelf ook stilzwijgend inslikken
        # als "sleutel ontbreekt" -- precies het soort gemaskeerde fout dat dit project's eigen
        # regel ("elke fout is een regressie") wil voorkomen.
        logger.error("OP-29: kon resultaat niet redigeren voor publicatie: %s", exc)
        return None


def safe_value_digest(value: str | None, *, tenant_id: int) -> str | None:
    """`value_digest`, met dezelfde val als `safe_digest_result` hierboven."""
    if not value:
        return None
    try:
        return value_digest(value, tenant_id=tenant_id)
    except (RuntimeError, ValueError) as exc:
        logger.error("OP-29: kon foutmelding niet redigeren voor publicatie: %s", exc)
        return None


def policy_for(tool_name: str) -> ToolPolicy:
    """Het vocabulaire en de leesbare waarden van deze tool.

    Een onbekende tool krijgt een LEGE policy: zowel sleutelnamen als waarden worden dan
    gedigest. Dat is de veilige default en niet een omissie.
    """
    return PAYLOAD_POLICY.get(tool_name, _EMPTY_POLICY)


def redact_for_publication(
    tool_name: str,
    payload: Mapping[str, Any],  # TODO(TYPE): replace Any with concrete type
    *,
    tenant_id: int,
    broker_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Payload zoals hij in een bewarende sink mag staan.

    Drie beslissingen, in deze volgorde:

    1. **Zette de aanroeper deze sleutel zelf uit de executiecontext?** (`broker_keys`) Dan is
       het geen modeloutput en blijft alles zoals het is.
    2. **Lijkt de sleutelNAAM op een parameternaam?** Zo niet, dan is de naam zelf modeloutput
       en wordt hij een pseudonym. Zonder deze stap kon de payload de persoonsgegevens in de
       SLEUTEL zetten, met `None` als waarde -- en dan zag de vastgelegde regel er volledig
       schoon uit.
    3. **Mag de WAARDE onder deze sleutel leesbaar blijven, en heeft hij de juiste vorm?** Een
       beoordeelde sleutelnaam zegt niets over wat er in staat: de naam is beoordeeld, de waarde
       is modeloutput, en deze functie loopt voordat de tool zijn parameters valideert. Leesbaar
       blijft alleen wat lid is van een OPSOMMING (`_one_of`, uit de declaratie) of binnen een
       grens valt die de tool zelf accepteert (`_bounded_int`); vrije tekst en geneste structuren
       worden een digest. Let op het verschil: `_one_of` is een echte opsomming, `_bounded_int` is
       een BEREIK en dus nog een vormtoets -- zie ADR-036 OP-34 voor de bits die dat kost.

    Sleutelnamen die de stap-2-toets halen blijven zichtbaar: zonder de namen is niet vast te
    stellen welke vorm de aanroep had, en dat is wat AI Act art. 12(2) toetsbaar wil houden.

    Args:
        tool_name: bepaalt welke waarden leesbaar mogen blijven.
        payload: de te publiceren payload. Wordt NIET gemuteerd.
        tenant_id: de tenant uit de EXECUTIECONTEXT. Verplicht, en nooit uit `payload`.
        broker_keys: sleutels die de aanroeper zelf uit de context injecteerde.

    Raises:
        ValueError: als `tenant_id` geen geldige tenant is.
        RuntimeError: als er geen pseudonimiseringssleutel beschikbaar is.
    """
    if _content_capture_enabled():
        return _verbatim(payload)

    policy = policy_for(tool_name)
    tenant_scope = _tenant_scope(tenant_id)
    published: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    for key, value in payload.items():
        if key in broker_keys:
            published[key] = value
            continue

        if not isinstance(key, str) or key not in policy.params:
            # De sleutel hoort niet bij het vocabulaire van deze tool, dus hij is door het
            # model verzonnen en kan alles bevatten. Naam EN waarde digesten -- en `None`
            # hier NIET doorlaten: juist een lege waarde onder een sprekende sleutelnaam
            # maakte de vastgelegde regel schoon-lijkend zonder een digest in zicht.
            published[_digest_key(str(key), tenant_scope)] = _digest(value, tenant_scope)
            continue

        shape = policy.readable.get(key)
        if value is None or (shape is not None and shape(value)):
            published[key] = value
        else:
            published[key] = _digest(value, tenant_scope)

    return published


def _verbatim(payload: Mapping[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """De payload onbewerkt, met de modus erin. Alleen bereikbaar via de opt-in."""
    published = dict(payload)
    # ALS LAATSTE, zodat een door het model geschreven `_redaction` wordt overschreven --
    # hetzelfde "context wint"-patroon dat service.py al voor `tenant_id` gebruikt.
    published[REDACTION_MODE_KEY] = VERBATIM_MODE
    return published
