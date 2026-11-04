"""De terugval op de generieke agent kent TWEE gevallen en die moeten verschillend klinken.

Achtergrond (BE-AGT-068, 2026-09-25). ``get_agent_instance`` ving ``ImportError`` en
``AttributeError`` samen af en meldde beide met ``logger.debug``. Gevolg: een configuratie
met een verkeerde ``class_name`` liet een volledig werkende skill nooit laden, en het enige
spoor stond op een niveau dat in productie niet wordt gelogd.

De twee gevallen:

* de skillmodule BESTAAT NIET -- vandaag de normale stand voor 151 catalogusvermeldingen
  zonder implementatie. Luid melden zou honderden regels per cataloguslading geven;
* de module bestaat WEL maar levert de klasse niet op, of is zelf kapot. Dat is altijd een
  defect en hoort als waarschuwing naar buiten, met de module- EN de klassenaam erin,
  zodat je niet hoeft te raden welke van de twee namen fout is.
"""

from __future__ import annotations

import logging

import pytest

from src.core.als.agents.loader import AgentConfig, EnterpriseCatalogLoader


def _loader_met(config: AgentConfig) -> EnterpriseCatalogLoader:
    """Een loader zonder __init__, zodat er niets van schijf wordt gelezen."""
    loader = EnterpriseCatalogLoader.__new__(EnterpriseCatalogLoader)
    loader.agents = {config.agent_id: config}
    loader.packs = {}
    return loader


def _config(agent_id: str, class_name: str) -> AgentConfig:
    return AgentConfig(
        agent_id=agent_id,
        name=class_name,
        department="mutatietest",
        technology="LLM",
        class_name=class_name,
    )


def test_een_ontbrekende_skillmodule_waarschuwt_NIET(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """151 catalogusvermeldingen zonder implementatie mogen geen waarschuwingsregen geven."""
    loader = _loader_met(_config("bestaatechtniet", "BestaatEchtNietAgent"))

    with caplog.at_level(logging.DEBUG, logger="src.core.als.agents.loader"):
        agent = loader.get_agent_instance("bestaatechtniet", tenant_id=1)

    assert agent is not None, "de terugval op de generieke agent moet blijven werken"
    waarschuwingen = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not waarschuwingen, (
        "Een ontbrekende skillmodule is de bekende stand, geen defect. Gemelde "
        f"waarschuwingen: {[r.getMessage() for r in waarschuwingen]}"
    )


def test_een_bestaande_module_zonder_de_klasse_WAARSCHUWT(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Dit is de vorm die DunningAgentAgent onzichtbaar hield."""
    # 'dunning' bestaat als module; de klasse die hierbij hoort ('DunningKaduukSkill')
    # niet. Exact de vorm van de bevinding, met een naam die nergens anders bestaat.
    loader = _loader_met(_config("dunning", "DunningKaduukAgent"))

    with caplog.at_level(logging.DEBUG, logger="src.core.als.agents.loader"):
        agent = loader.get_agent_instance("dunning", tenant_id=1)

    assert agent is not None, "de terugval moet blijven werken, ook bij een defect"
    waarschuwingen = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert waarschuwingen, (
        "Een module die bestaat maar zijn klasse niet oplevert is een defect en moet "
        "als waarschuwing naar buiten komen."
    )
    # Toets de ARGUMENTEN van de logregel, niet de uitgeschreven tekst. De tekst van de
    # AttributeError bevat de module- en klassenaam namelijk zelf ("module '...' has no
    # attribute '...'"), dus een assertie op de string is groen ook als de logregel die
    # namen helemaal niet meegeeft. Een mutatie die de %s voor de modulenaam wegnam bleef
    # daardoor onbetrapt -- gemeten 2026-09-25.
    record = next(r for r in caplog.records if r.levelno >= logging.WARNING)
    argumenten = [str(a) for a in (record.args or ())]
    assert "src.core.als.agents.skills.dunning" in argumenten, (
        f"de logregel moet de MODULENAAM als eigen argument meegeven: {argumenten}"
    )
    assert "DunningKaduukSkill" in argumenten, (
        f"de logregel moet de gezochte KLASSENAAM als eigen argument meegeven: {argumenten}"
    )


def test_een_skill_met_een_KAPOTTE_eigen_import_waarschuwt_ook(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Een module die bestaat maar zelf een import mist, is een defect -- geen lege plek.

    Zonder de naamstoets in de loader (`e.name == module_name`) valt dit geval samen met
    "module bestaat niet" en verdwijnt het in debug. Precies die mutatie bleef in ronde 1
    onbetrapt omdat er geen test voor was.
    """
    import importlib

    echte_import = importlib.import_module

    def _kapotte_import(naam: str, *args: object, **kwargs: object) -> object:
        # Alleen DEZE skillmodule struikelt. Een patch op alles sloopt ook de terugval
        # zelf (BaseSpecialistAgent importeert onderweg), en dan meet je je eigen mock.
        if naam == "src.core.als.agents.skills.dunning":
            raise ModuleNotFoundError(
                "No module named 'onvindbaar_pakket'", name="onvindbaar_pakket"
            )
        return echte_import(naam, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib, "import_module", _kapotte_import)
    loader = _loader_met(_config("dunning", "DunningAgent"))

    with caplog.at_level(logging.DEBUG, logger="src.core.als.agents.loader"):
        agent = loader.get_agent_instance("dunning", tenant_id=1)

    assert agent is not None, "de terugval moet blijven werken"
    waarschuwingen = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert waarschuwingen, (
        "Een skillmodule die op zijn EIGEN import stukloopt is een defect en mag niet "
        "wegvallen tussen de 151 vermeldingen zonder implementatie."
    )


def test_implemented_agent_keys_telt_een_vermelding_ZONDER_module_NIET_mee() -> None:
    """Anders is de methode een dure manier om len(self.agents) te schrijven.

    De G1-drempel (`tests/unit/test_g1_yaml_validation.py`) rust hierop. Die drempel zelf
    kan dit NIET aantonen: 130 wordt gehaald door 135 echte implementaties en net zo goed
    door 289 vermeldingen. Alleen deze test legt het verschil vast.
    """
    loader = _loader_met(_config("bestaatechtniet", "BestaatEchtNietAgent"))

    assert loader.agents, "voorwaarde: er staat wel degelijk een vermelding in de catalogus"
    assert loader.implemented_agent_keys() == set(), (
        "Een vermelding zonder skillmodule mag niet als implementatie tellen; "
        f"gekregen: {loader.implemented_agent_keys()}"
    )


def test_implemented_agent_keys_telt_een_vermelding_MET_module_WEL_mee() -> None:
    """De tegenrichting: 'geef nooit iets terug' is geen geldige oplossing."""
    loader = _loader_met(_config("dunning", "DunningAgent"))

    assert loader.implemented_agent_keys() == {"dunning"}, (
        "Een vermelding met een bestaande skillmodule EN de gezochte klasse moet "
        f"meetellen; gekregen: {loader.implemented_agent_keys()}"
    )


def test_implemented_agent_keys_telt_een_module_ZONDER_de_klasse_NIET_mee() -> None:
    """Het derde geval, en het enige dat de KLASSE-controle bewijst.

    De twee tests hierboven dekken 'module ontbreekt' en 'module plus klasse aanwezig'.
    Geen van beide wordt rood als de klasse-controle helemaal wegvalt: bij een ontbrekende
    module komt de code daar nooit. Gemeten 2026-09-25: die mutatie bleef onbetrapt tot
    deze test bestond.
    """
    # 'dunning' bestaat als module; 'DunningKaduukSkill' bestaat daarin niet.
    loader = _loader_met(_config("dunning", "DunningKaduukAgent"))

    assert loader.implemented_agent_keys() == set(), (
        "Een module die de gezochte klasse niet oplevert is geen implementatie -- de "
        f"loader valt daar terug op BaseSpecialistAgent; gekregen: "
        f"{loader.implemented_agent_keys()}"
    )
