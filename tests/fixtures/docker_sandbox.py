"""Fixture: geen ECHTE Docker-daemonverbinding uit een unittest (ADR-036 OP-214).

**Bijgewerkt 2026-09-10 (ADR-036 OP-216, Route A).** Route 1 hieronder is INMIDDELS GEFIXED:
`LocalToolRegistry.__init__` bouwt geen `ProductionSandboxManager` meer en raakt de
Docker-daemon niet langer (`src/core/tool_broker/local_registry.py`). De zes testbestanden die
deze fixture UITSLUITEND voor route 1 importeerden, zijn bijgewerkt om hem niet meer te
importeren: `tests/architecture/test_tool_policy_matches_the_tools.py`,
`tests/unit/events/test_tool_event_publishing.py`, `tests/unit/test_test_tools.py`,
`tests/unit/tool_broker/test_op29_result_error_redaction.py`,
`tests/unit/tool_broker/test_op35_blocked_attempts_are_audited.py`,
`tests/unit/tool_broker/test_pseudonymisation_leaks.py` (per bestand geverifieerd: geen van de
zes raakt route 2/3/4). Deze fixture blijft bestaan en autouse voor de bestanden die routes
2-4 raken (o.a. `test_tenant_sandbox_orchestrator.py`, `test_main_api_critical_coverage.py`,
`test_base_agent_toolbroker.py`, `test_hitl_wiring_consistency.py`, `test_sprint9_dag1_fixes.py`)
-- die zijn NIET aangeraakt, want ze verbinden nog steeds echt.

**De oorspronkelijke bevinding, gemeten 2026-09-09 uit CI-run 34290014186.** Vier verschillende
constructies in dit project openden in hun CONSTRUCTOR een echte verbinding naar de
Docker-daemon, alle vier via dezelfde functie, `docker.from_env()`:

  1. ~~`LocalToolRegistry.__init__` -> `get_production_sandbox_manager()` ->
     `ProductionSandboxManager._init_docker_client`~~ -- GEFIXED, zie hierboven (OP-216);
  2. `TenantSandboxOrchestrator.initialize()` (`tenant_sandbox_orchestrator.py:204`);
  3. `DockerSandboxManager()` (`sandbox_manager.py:268`);
  4. `SandboxManagerFactory.create_manager()` vanuit de FastAPI-lifespan
     (`src/core/api/main.py`), die op 3 uitkomt.

In CI weigert de OP-18-netwerkblokkade dat terecht -- `/var/run/docker.sock` is een echte
uitgaande verbinding uit een unittest. Omdat `EchteVerbindingInUnitTest` met opzet van
`BaseException` erft (ontwerpkeuze 3 in `tests/fixtures/netwerkblokkade.py`) glipt hij door
de brede `except Exception` in `_init_docker_client()` EN die in
`LocalToolRegistry.__init__`, en valt de test hard om in plaats van stil terug.

**Waarom dit lokaal onzichtbaar was.** Op Windows gebruikt docker-py een named pipe in plaats
van een unix-socket, dus daar raakt dit codepad de socketlaag niet en vuurt de blokkade nooit.
Nagemeten met een stand-in die dezelfde exceptieklasse gooit op dezelfde plek (`docker.from_env`
laten falen; de klasse wordt geimporteerd uit `netwerkblokkade`, het is dus letterlijk dezelfde
`BaseException`-subklasse en niet een nabootsing): 51 rode regels, 48 unieke node-ids. Een
controlerun ZONDER de stand-in gaf er 4, allemaal al bestaande Windows-lokale problemen, en die
4 komen ook in de stand-in-run terug. Netto dus 44 node-ids in 9 bestanden, plus de 2 bestanden
die uit het CI-log zelf kwamen: 11 bestanden. De aftrekking is op NAAM gedaan en niet op aantal.

In CI zag je er TWEE, omdat de blokkerende poort met `-x` en `-n 2` draait en dus per worker
stopt na het eerste falen. Die onderrapportage -- 2 gemeld tegen 44 werkelijk, een factor 22 --
is een zelfstandige bevinding over de poort en staat als OP-217 open.

**Waarom EEN naad en niet vier.** `docker.from_env` is de enige plek waar de verbinding wordt
gelegd; alle vier de routes komen daar langs. Een fixture per aanroeper zou vier keer hetzelfde
zeggen en bij een vijfde aanroeper stil tekortschieten. Even belangrijk is wat deze keuze NIET
doet: hij vervangt geen fabrieksfunctie en geen managerklasse, dus de echte objecten worden nog
steeds gebouwd. Dat is bewust. Een eerdere versie patchte
`local_registry.get_production_sandbox_manager`, en in `test_tool_policy_matches_the_tools.py`
-- een architectuurtest -- zou die de ECHTE manager door een dubbel hebben vervangen; een
architectuurtest die tegen het attribuutoppervlak van een `MagicMock` asserteert, meet niets.
Met deze naad wordt de manager gewoon geconstrueerd en blijft alleen de socket dicht.

**Waarom niet in een conftest.** Een repo-brede autouse-fixture die uitzet wat een andere test
meet is in dit project al eens 1538 tests lang onopgemerkt gebleven. Daarom is dit, net als
`tests/fixtures/tool_execution_tenant.py`, een fixture die je PER BESTAND importeert: hij werkt
alleen in bestanden die er expliciet om vragen. Een test die de sandboxlaag ZELF als onderwerp
heeft, hoort in een bestand dat deze fixture niet importeert.

Die keuze laat een gat: het volgende testbestand dat een sandbox construeert, verbindt weer
echt. Een guard die per testmodule toetst "raakt hij een sandboxconstructie, dan moet hij deze
fixture importeren" is overwogen en NIET gebouwd, om een gemeten reden. Een tekstscan op de vier
constructienamen vindt 13 testbestanden, en mist er 2 van de 11 die de daemon werkelijk raken:
`test_base_agent_toolbroker.py` en `test_hitl_wiring_consistency.py` komen binnen via
`EnhancedBaseAgent.tool_broker`, dus zonder een van die namen in hun tekst. Tegelijk noemt de
scan 4 bestanden die de daemon NIET raken. Zo'n guard zou dus in beide richtingen ongelijk aan
de werkelijkheid zijn -- precies de holle vorm uit de rookmeldersaudit -- en de gedateerde
uitzonderingslijst die dat moet opvangen, is dan het enige wat hem groen houdt.

Wat het gat WEL dicht is er al: de OP-18-netwerkblokkade zelf. Die heeft dit geval betrapt, en
betrapt het volgende geval net zo goed. Het echte probleem is niet dat niets het merkt maar dat
de poort met `-x` en `-n 2` maar TWEE van de 44 falen laat zien; dat is OP-217. Conform
stopregel 3 (besluit Rakesh 2026-09-07) hier dus een registerrij en geen tweede guard.

**Wat deze fixture NIET repareert.** De oorzaak. Dat `LocalToolRegistry` een draaiende
Docker-daemon eist om gebouwd te kunnen worden -- terwijl `sandbox_manager` nergens in `src/`,
`tests/` of `scripts/` gelezen wordt, er in dat bestand geen subprocess-pad bestaat, en de
klassedocstring toch `executes within the sandbox` belooft -- staat als OP-216 OPEN. De druk om
dat op te lossen verdween met deze fixture, en dat is met een strict-xfail-guard vervangen:
`tests/architecture/test_op216_de_registry_isoleert_niet.py` legt de huidige onware belofte
vast en wordt ROOD op het moment dat OP-216 wordt gerepareerd, zodat de registerrij dan niet
kan blijven staan.

Gebruik:

    from tests.fixtures.docker_sandbox import geen_echte_docker_daemon  # noqa: F401
"""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

#: De ENE functie die de verbinding legt. `patch.object` met `create=False` (de standaard) is
#: hier het vangnet: verdwijnt of verplaatst deze naam, dan faalt de fixture luid met een
#: `AttributeError` in plaats van stil niets te patchen.
#:
#: Wat hij NIET dekt, expliciet zodat een lezer het niet hoeft te raden: een aanroeper die
#: `docker.DockerClient(...)` of `docker.APIClient(...)` rechtstreeks bouwt, of die
#: `from docker import from_env` doet en dus zijn eigen binding heeft. Gemeten 2026-09-09: geen
#: van die drie vormen bestaat vandaag in `src/`. Komt er ooit een bij, dan dekt deze fixture
#: hem NIET en presenteert dat zich in CI als een nieuw OP-18-falen -- niet als een stil gat.
DOEL = "from_env"


@pytest.fixture(autouse=True)
def geen_echte_docker_daemon() -> Iterator[MagicMock]:
    """Laat de daemonverbinding een dubbel zijn; de rest van de constructie blijft echt."""
    import docker

    with patch.object(docker, DOEL) as van_omgeving:
        yield van_omgeving
