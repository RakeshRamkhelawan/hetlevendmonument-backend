"""Een manifestwijziging moet gefaseerd kunnen uitrollen (ADR-036 OP-02).

Bevinding OP-02: een wijziging in het manifest of de instructietekst van de HR-pilootagent
gaat in EEN keer naar alle tenants. Er is geen versieveld op het manifest en geen enkele
manier om een nieuwe prompt eerst aan een kleine groep te geven. Een fout raakt iedereen
tegelijk, en terugdraaien kan alleen met een nieuwe deploy.

Het bestaande blue-green-raamwerk (`deployment/blue_green/deploy.py`) lost dit NIET op: dat
schakelt hele containeromgevingen om via nginx (0 procent -> 100 procent) en kent geen
tenants. Gemeten: geen enkele import ervan in `src/`.

Deze tests leggen de drie eigenschappen vast die OP-02 vraagt:

  1. het manifest draagt een VERSIENUMMER, en dat nummer komt in de agentconfiguratie;
  2. een manifest met een `canary`-blok levert voor de ENE tenant de oude en voor de ANDERE
     de nieuwe tekst -- de percentage-uitrol;
  3. de toewijzing is STABIEL (dezelfde tenant krijgt bij herhaling hetzelfde) en er is een
     AUTOMATISCHE TERUGVAL naar de stabiele versie.

De tests lopen over de ECHTE weg: een echt manifestbestand, `SkillManifest.load()`, en
`BaseSpecialistAgent`, dat de tenant kent. Er wordt nergens een verwachte uitkomst
nagerekend met een tweede kopie van dezelfde formule -- de vraag is steeds alleen OF de
splitsing bestaat en of hij stabiel is.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.als.agents.skill_manifest import SkillManifest
from src.core.als.agents.specialist_base import BaseSpecialistAgent

PILOT_MANIFEST = (
    Path(__file__).parents[3]
    / "src"
    / "core"
    / "als"
    / "agents"
    / "skills"
    / "manifests"
    / "skillsgaptraining.yml"
)

STABIELE_PROMPT = "Je bent de stabiele versie. Antwoord kort."
CANARY_PROMPT = "Je bent de NIEUWE versie. Antwoord kort en noem je versie."

# Ruim genoeg om bij 5 procent zowel binnen- als buitenvallers te bevatten. Geen
# willekeurige tenants: een aaneengesloten reeks, zodat de test niet kan slagen door een
# gelukkige greep.
TENANT_BEREIK = range(1, 201)

# Voor de stabiliteitscontrole is een steekproef genoeg: die eigenschap is per tenant, niet
# over de verdeling. Elke agentconstructie kost ~30 ms, dus de hele reeks tweemaal bouwen
# zou deze ene test 12 s laten duren.
STABILITEIT_STEEKPROEF = list(range(1, 21))


def _schrijf_manifest(doelmap: Path, *, canary: dict[str, object] | None) -> Path:
    """Schrijf een echt manifestbestand, gebaseerd op dat van de piloot.

    Bewust een KOPIE van het productiemanifest en geen zelfgebouwde dict: zo loopt de test
    door dezelfde verplichte velden en dezelfde parser als productie, en breekt hij als het
    manifestformaat verandert.
    """
    data = yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8"))
    data["system_prompt"] = STABIELE_PROMPT
    data["manifest_version"] = 1
    if canary is not None:
        data["canary"] = canary

    pad = doelmap / "skillsgaptraining.yml"
    pad.write_text(yaml.safe_dump(data, allow_unicode=False), encoding="utf-8")
    return pad


def _prompt_voor_tenant(manifest_pad: Path, tenant_id: int) -> str:
    """De systeemprompt zoals de agent hem voor DEZE tenant werkelijk krijgt.

    Loopt via `BaseSpecialistAgent`, want dat is het punt waar de tenant bekend is. Een test
    die alleen `SkillManifest` zou aanroepen, zou de uitrol nooit kunnen zien.
    """
    manifest = SkillManifest.load(manifest_pad)
    agent = BaseSpecialistAgent(config=manifest.to_config(), tenant_id=tenant_id)
    return str(agent.config["system_prompt"])


def test_het_manifest_draagt_een_versienummer(tmp_path: Path) -> None:
    """Zonder versieveld is er niets om een uitrol aan op te hangen (OP-02)."""
    pad = _schrijf_manifest(tmp_path, canary=None)
    config = SkillManifest.load(pad).to_config()

    assert "manifest_version" in config, (
        "Het manifest levert geen `manifest_version` in de agentconfiguratie. Zonder "
        "versienummer is niet vast te stellen WELKE promptversie een tenant draait, en kan "
        "een uitrol niet gefaseerd of teruggedraaid worden (ADR-036 OP-02)."
    )
    assert config["manifest_version"] == 1


def test_een_canary_geeft_niet_alle_tenants_dezelfde_prompt(tmp_path: Path) -> None:
    """De kern van OP-02: 5 procent krijgt de nieuwe tekst, de rest de oude.

    Deze test rekent de bucketformule NIET na. Hij stelt alleen vast dat er over een echt
    tenantbereik een SPLITSING bestaat: minstens een tenant met de nieuwe tekst en minstens
    een met de oude. Dat is precies de eigenschap die vandaag ontbreekt -- vandaag krijgt
    iedereen dezelfde tekst.
    """
    pad = _schrijf_manifest(
        tmp_path,
        canary={
            "manifest_version": 2,
            "percentage": 5,
            "system_prompt": CANARY_PROMPT,
        },
    )

    prompts = {tenant_id: _prompt_voor_tenant(pad, tenant_id) for tenant_id in TENANT_BEREIK}
    binnen = [t for t, p in prompts.items() if p == CANARY_PROMPT]
    buiten = [t for t, p in prompts.items() if p == STABIELE_PROMPT]

    assert binnen, (
        "GEEN ENKELE tenant kreeg de canary-prompt over "
        f"{len(TENANT_BEREIK)} tenants bij 5 procent. De nieuwe manifestversie bereikt dus "
        "niemand; er is geen uitrolmechanisme (ADR-036 OP-02)."
    )
    assert buiten, (
        "ALLE tenants kregen de canary-prompt. Dan is het geen gefaseerde uitrol maar precies "
        "de big-bang die OP-02 beschrijft: een fout raakt iedereen meteen."
    )
    assert len(binnen) + len(buiten) == len(TENANT_BEREIK), (
        "Sommige tenants kregen een derde, onbekende prompt. De resolver hoort uitsluitend de "
        "stabiele of de canary-tekst op te leveren."
    )


def test_de_toewijzing_is_stabiel_voor_dezelfde_tenant(tmp_path: Path) -> None:
    """Een tenant mag niet per aanroep wisselen tussen oud en nieuw.

    Zonder deze eigenschap krijgt dezelfde gebruiker binnen een gesprek twee verschillende
    persona's, en is een waargenomen fout niet te herleiden tot een versie.
    """
    pad = _schrijf_manifest(
        tmp_path,
        canary={
            "manifest_version": 2,
            "percentage": 5,
            "system_prompt": CANARY_PROMPT,
        },
    )

    for tenant_id in STABILITEIT_STEEKPROEF:
        eerste = _prompt_voor_tenant(pad, tenant_id)
        tweede = _prompt_voor_tenant(pad, tenant_id)
        assert eerste == tweede, (
            f"Tenant {tenant_id} kreeg bij twee opeenvolgende aanroepen een ANDERE prompt. "
            "De toewijzing is niet stabiel; dat maakt een canary onbruikbaar."
        )


def test_percentage_nul_laat_iedereen_op_de_stabiele_versie(tmp_path: Path) -> None:
    """De automatische terugval: percentage op 0 zetten haalt de canary bij iedereen weg.

    Dit is de terugvalknop uit OP-02. Hij moet werken zonder nieuwe deploy en zonder dat er
    ook maar een tenant achterblijft op de nieuwe versie.
    """
    pad = _schrijf_manifest(
        tmp_path,
        canary={
            "manifest_version": 2,
            "percentage": 0,
            "system_prompt": CANARY_PROMPT,
        },
    )

    achterblijvers = [
        tenant_id
        for tenant_id in TENANT_BEREIK
        if _prompt_voor_tenant(pad, tenant_id) != STABIELE_PROMPT
    ]
    assert not achterblijvers, (
        f"Na terugval naar 0 procent draaien deze tenants nog de canary: {achterblijvers}. "
        "Een terugval die niet iedereen bereikt, is geen terugval."
    )


def test_een_kapot_canary_blok_valt_terug_op_de_stabiele_versie(tmp_path: Path) -> None:
    """Fail-safe: een onleesbaar canary-blok mag de skill niet omverhalen.

    Een tikfout in het uitrolblok mag nooit tot gevolg hebben dat een tenant helemaal geen
    prompt of een halve prompt krijgt. De veilige uitkomst is de stabiele versie.
    """
    pad = _schrijf_manifest(tmp_path, canary={"percentage": "vijf procent"})

    for tenant_id in (1, 2, 3, 42, 199):
        assert _prompt_voor_tenant(pad, tenant_id) == STABIELE_PROMPT, (
            f"Tenant {tenant_id} kreeg geen stabiele prompt terwijl het canary-blok "
            "onleesbaar is. Een kapotte uitrolconfiguratie hoort genegeerd te worden, niet "
            "de skill te breken."
        )


def test_de_versie_reist_mee_met_de_tekst(tmp_path: Path) -> None:
    """Wie de nieuwe tekst krijgt, rapporteert ook het nieuwe versienummer.

    Dit is wat het versieveld bruikbaar maakt: bij een klacht over een antwoord is uit de
    agentconfiguratie af te lezen WELKE tekst hem voortbracht. Een versienummer dat niet
    meebeweegt met de uitrol is een decoratie.
    """
    pad = _schrijf_manifest(
        tmp_path,
        canary={
            "manifest_version": 2,
            "percentage": 5,
            "system_prompt": CANARY_PROMPT,
        },
    )

    for tenant_id in TENANT_BEREIK:
        manifest = SkillManifest.load(pad)
        agent = BaseSpecialistAgent(config=manifest.to_config(), tenant_id=tenant_id)
        prompt = str(agent.config["system_prompt"])
        versie = agent.config["manifest_version"]
        verwacht = 2 if prompt == CANARY_PROMPT else 1
        assert versie == verwacht, (
            f"Tenant {tenant_id} draait de "
            f"{'canary' if prompt == CANARY_PROMPT else 'stabiele'}-tekst maar rapporteert "
            f"manifest_version={versie}. Versie en tekst horen bij elkaar."
        )


def test_de_noodrem_zet_alle_canary_s_uit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SKILL_CANARY_KILL_SWITCH=true haalt iedereen terug naar de stabiele versie.

    De platformbrede terugval uit OP-02: hij werkt zonder een manifest aan te raken en
    zonder nieuwe deploy, en hij moet ALLE tenants bereiken -- ook die in
    `enabled_tenant_ids`, want anders is de noodrem geen noodrem.
    """
    pad = _schrijf_manifest(
        tmp_path,
        canary={
            "manifest_version": 2,
            "percentage": 100,
            "enabled_tenant_ids": [1, 2, 3],
            "system_prompt": CANARY_PROMPT,
        },
    )

    monkeypatch.setenv("SKILL_CANARY_KILL_SWITCH", "true")
    achterblijvers = [
        tenant_id
        for tenant_id in STABILITEIT_STEEKPROEF
        if _prompt_voor_tenant(pad, tenant_id) != STABIELE_PROMPT
    ]
    assert not achterblijvers, (
        f"Met de noodrem aan draaien deze tenants nog de canary: {achterblijvers}. "
        "Een noodrem die tenants op de nieuwe versie laat staan, lost een incident niet op."
    )
