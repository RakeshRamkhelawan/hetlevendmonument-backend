"""De sleutel van een klant verlaat de keten nooit via een logregel.

**Waarom dit de derde bewaker is die het oorspronkelijke vijf-fasenplan eiste, en de enige die
nog ontbrak.** Twee ervan staan er al: geen leveranciersadres in de generieke provider
(`test_de_generieke_provider_kent_geen_leverancier.py`) en een meetinstrument dat een
namaakmodel niet als succes telt (`acceptance_thread.py`). De derde stond er niet, terwijl het
pad sinds BE-LLM-004 langer is geworden: de sleutel van een klant wordt ontsleuteld in de
servicelaag, reist als `ProviderRij.api_key` naar de LLM-laag, en komt daar in een
`Authorization`-kop terecht.

Er is al dekking op twee losse plekken -- de `repr` van `ProviderRij` en de melding bij een
onleesbare rij -- maar geen enkele controle over de MODULES heen. Een nieuwe logregel met
`rij.api_key` erin zou dus nergens rood maken, en een sleutel in een logbestand is niet terug
te nemen: logs worden doorgestuurd, bewaard en gelezen door mensen die nooit toegang tot die
sleutel hadden.

**Hoe dit toetst.** Structureel, niet op tekst: elke aanroep `logger.<niveau>(...)` in de
genoemde modules wordt bekeken, en geen enkel argument mag de sleutel dragen -- niet als
`rij.api_key`, niet als losse naam `api_key` of `sleutel`. Een verboden woord in een comment of
docstring maakt deze bewaker dus niet rood, en een echte lek-regel wel.

**Mutatiebewijs (2026-09-23), beide richtingen:**

- in `tenant_llm_provider_service.keten()` het argument `rij.naam` van de overslaan-melding
  vervangen door `rij.api_key`: ROOD.
- in `service.for_tenant` `rij.api_key` als extra argument aan de INFO-regel hangen: ROOD.
- de bestaande regels met `rij.naam`, de host en het label laten staan: GROEN -- die horen er
  te zijn, want zonder spoor van WELK eindpunt er is gebruikt is er geen verwerkingsregister
  (AVG art. 30, AI Act art. 12).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De modules waar een ontsleutelde klantsleutel doorheen komt. Expliciet genoemd, zodat het
#: mutatiebewijs een regel per element kan hebben en een nieuwe module een bewuste toevoeging is.
MODULES_MET_DE_SLEUTEL = (
    "src/core/services/tenant_llm_provider_service.py",
    "src/core/services/llm/service.py",
    "src/core/services/llm/providers/openai_compatible.py",
    # Toegevoegd 2026-09-24 (BE-LLM-005, door BEIDE Gate 2-reviewers aangewezen). Deze module
    # houdt providerobjecten vast waarvan `config.api_key` de ontsleutelde klantsleutel is, en
    # logt op vier plekken. Zolang hij niet in deze lijst stond, was precies de vorm waarvoor
    # `DRAGERS` bestaat -- `logger.debug("%s", schakel.provider.config)` -- hier groen gebleven.
    "src/core/services/llm/providers/failover.py",
)

#: Namen die de sleutel zelf dragen. `api_key_encrypted` staat er NIET bij: die is versleuteld
#: en zegt niets zonder de hoofdsleutel, en hem loggen is onhandig maar geen lek.
#:
SLEUTELNAMEN = {"api_key", "sleutel"}

#: Objecten die het geheim BEVATTEN en het bij het afdrukken meenemen.
#:
#: Toegevoegd 2026-09-23 (Gate 2). Beide reviewers wezen erop dat deze bewaker blind was voor de
#: vorm waarin de sleutel vandaag leeft: `logger.debug("%s", self.config)` drukt een hele
#: `LLMConfig` af, en die draagt `api_key`. De bewaker keek alleen naar de NAAM van het veld en
#: zag dus niets -- een controle op een woord in plaats van op wat er gebeurt. (`LLMConfig` heeft
#: sinds diezelfde ronde ook `repr=False` op dat veld; dit is de tweede rem, want een volgende
#: dataclass krijgt die vlag misschien niet.)
DRAGERS = {"config"}


def _logaanroepen(boom: ast.AST) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(boom)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "logger"
    ]


def _gerenderd(argument: ast.expr) -> list[ast.expr]:
    """De uitdrukkingen die daadwerkelijk in de tekst terechtkomen.

    Een f-string is EEN argument maar rendert meerdere uitdrukkingen; zonder deze stap zou een
    `logger.info(f"... {self.config} ...")` als een enkele knoop langskomen en de vorm eronder
    niet te onderscheiden zijn.
    """
    if isinstance(argument, ast.JoinedStr):
        return [deel.value for deel in argument.values if isinstance(deel, ast.FormattedValue)]
    return [argument]


def _draagt_de_sleutel(argument: ast.expr) -> bool:
    """Draagt deze uitdrukking het geheim, rechtstreeks of via een object dat het bevat?

    **Twee vormen, en het onderscheid is met opzet fijn (Gate 2, 2026-09-23).**

    1. De sleutel zelf (`rij.api_key`, `sleutel`): overal in de uitdrukking fout.
    2. Een OBJECT dat de sleutel draagt (`self.config`, een `LLMConfig`): alleen fout als het
       object ZELF wordt afgedrukt. `self.provider.config.model` drukt een modelnaam af en is
       prima -- een bestaande logregel doet dat, en een bewaker die daarop afgaat zou vragen om
       een uitzonderingslijst in plaats van een scherpere toets.

    Daarom wordt voor vorm 2 alleen de BUITENSTE knoop bekeken: `X.config` is een drager,
    `X.config.model` niet.
    """
    for uitdrukking in _gerenderd(argument):
        for n in ast.walk(uitdrukking):
            if isinstance(n, ast.Attribute) and n.attr in SLEUTELNAMEN:
                return True
            if isinstance(n, ast.Name) and n.id in SLEUTELNAMEN:
                return True
        if isinstance(uitdrukking, ast.Attribute) and uitdrukking.attr in DRAGERS:
            return True
        if isinstance(uitdrukking, ast.Name) and uitdrukking.id in DRAGERS:
            return True
    return False


def test_geen_enkele_logregel_draagt_de_klantsleutel() -> None:
    overtredingen: list[str] = []
    gezien = 0

    for pad in MODULES_MET_DE_SLEUTEL:
        bestand = REPO_ROOT / pad
        assert bestand.exists(), (
            f"{pad} bestaat niet meer. Is de module hernoemd, werk dan MODULES_MET_DE_SLEUTEL "
            "bij -- een bewaker die naar een verdwenen bestand kijkt, bewaakt niets."
        )
        boom = ast.parse(bestand.read_text(encoding="utf-8"))
        for aanroep in _logaanroepen(boom):
            gezien += 1
            for argument in list(aanroep.args) + [kw.value for kw in aanroep.keywords]:
                if _draagt_de_sleutel(argument):
                    overtredingen.append(f"{pad}:{aanroep.lineno}")

    assert gezien, (
        "er is geen enkele logaanroep gevonden in de genoemde modules -- dan meet deze bewaker "
        "niets meer en klopt de lijst of de vorm van de aanroep niet"
    )
    assert not overtredingen, (
        "een logregel draagt de ontsleutelde klantsleutel: "
        + ", ".join(overtredingen)
        + ". Een sleutel in een logbestand is niet terug te nemen."
    )
