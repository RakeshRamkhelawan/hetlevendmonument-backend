"""De noodstop op de modeldeur: bij een stilgezette klant gaan er GEEN klantgegevens naar een taalmodel.

**Het principe (ronde 3, besluit van de gebruiker).** Besluit A van ronde 2 sloot de chat. Dit sluit
elk ander pad: een agent, een achtergrondtaak, een dienst. Waar een taalmodel wordt aangeroepen staat
de controle OP DAT PUNT, niet in de aanroeper. Dan dekt een controle alle paden, ook een pad dat er
morgen bij komt, en hoeft niemand eraan te denken.

**Poort en adapter.** Dit is de poort: alleen standaardbibliotheek, zodat elke modelstack
(`core/llm`, `services/llm`, `als`, `learning`, `workflow`, `strategy`) hem kan gebruiken zonder
een extra koppeling naar de noodstop-infrastructuur. De adapter
(`src/core/noodstop/model_deur.py`) meldt zich bij het laden aan met de echte controle (de
guard) en de tenantcontext. **De poort laadt niets zelf** (ronde 4, optie A): elk procesopstartpunt
(de app, elke dramatiq-worker, de scheduler) schrijft bovenaan het bestand
`from src.core.noodstop import model_deur  # noqa: F401`. Alleen die vorm: de DSM-meter
(`scripts/dsm_full_analysis.py`) telt `from ... import` (`ast.ImportFrom`) en telt `import x`
(`ast.Import`) NIET, dus alleen de from-vorm maakt de rand zichtbaar. Dat de meter `import x` niet
telt is een eigen gebrek met een eigen opdracht (`2026-10-22-sprint-dag-dsm-meter-telt-ook-import-x`),
niet in deze tak opgelost. De poort met een tekenreeks-import (`importlib`) maakte de rand ook
onzichtbaar, en de rand is echt. De architectuurtest
`test_modeldeur_adapter_wordt_bij_het_opstarten_geladen.py` dwingt beide af. Is er geen adapter
aangemeld, dan weigert de aanroep (`ModelDeurNietBeschikbaar`, fail-closed): een deur zonder
controle gaat niet open.

**Twee manieren om de klant te kennen.**

1. *Expliciet*: een object dat zijn klant kent (`TenantTaalmodel`, een `LLMService.for_tenant`) draagt
   `noodstop_tenant_id`. Dat is de precieze weg en werkt ook zonder tenantcontext.
2. *Uit de context*: een client of provider kent zijn klant niet; de verzoekcontext (JWT, middleware)
   of de actor (`set_tenant_id`) wel. Staat er een tenant in de context, dan geldt die.

Geen van beide (geen klant bekend): een systeemtaak zonder klantgegevens (gezondheidscontrole,
platformstandaard). Die loopt door. Dat is de ENIGE doorgang en de reden staat in de architectuurtest
(`test_elk_modelpad_controleert_de_noodstop.py`). Is er wel een klant maar kan de stand niet worden
gelezen, dan weigert de aanroep (fail-closed, zoals elke deur).

**Eenmaal per aanroep.** Een aanroep die zelf een andere bewaakte aanroep doet (een client die
`chat_completion` aanroept vanuit `generate_response`) leest de stand een keer: de buitenste
aanroep onthoudt voor welke klant hij al controleerde.

**Waar de controle staat.** In een basisklasse die `bewaak_modelmethoden` aanroept vanuit
`__init_subclass__` (elke subklasse is dan bewaakt, ook een nieuwe), of met `@bewaakt_model_aanroep`
op een losse methode. De architectuurtest leest de broncode en faalt voor een modelpad zonder een van
beide.

**Kosten.** Een leesactie van een paar tientallen milliseconden per modelaanroep (gemeten, zie het
rapport van ronde 3), op een aanroep die zelf seconden duurt. Er is geen cache: een stop geldt direct.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextvars import ContextVar
from typing import ParamSpec, TypeVar, cast

P = ParamSpec("P")
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Awaitable[object]])

#: Het kenmerk waarmee een object zijn klant meegeeft (zie punt 1 in de moduledocstring).
TENANT_KENMERK = "noodstop_tenant_id"

#: De klant voor wie de lopende aanroep de stand al gelezen heeft (zie "Eenmaal per aanroep").
_gecontroleerd: ContextVar[int | None] = ContextVar("noodstop_model_gecontroleerd", default=None)

_controleur: Callable[[object], Awaitable[None]] | None = None
_klantlezer: Callable[[], int | None] | None = None


class ModelDeurNietBeschikbaar(RuntimeError):
    """Er is geen noodstopcontrole aangemeld: de modeldeur blijft dicht (fail-closed)."""


def registreer(
    controleur: Callable[[object], Awaitable[None]],
    klantlezer: Callable[[], int | None],
) -> None:
    """Door de adapter aangeroepen: de echte controle en de tenantcontext."""
    global _controleur, _klantlezer
    _controleur = controleur
    _klantlezer = klantlezer


def _adapter() -> tuple[Callable[[object], Awaitable[None]], Callable[[], int | None]]:
    if _controleur is None or _klantlezer is None:
        raise ModelDeurNietBeschikbaar(
            "de noodstopcontrole voor modelaanroepen is niet aangemeld: het procesopstartpunt "
            "moet `src.core.noodstop.model_deur` importeren"
        )
    return _controleur, _klantlezer


def _klant_van(argumenten: tuple[object, ...]) -> int | None:
    """De klant van de aanroep: die van het object zelf, anders die van de context, anders geen."""
    if argumenten:
        eigen = getattr(argumenten[0], TENANT_KENMERK, None)
        if eigen is not None:
            return int(eigen) if isinstance(eigen, int) and not isinstance(eigen, bool) else -1
    return _adapter()[1]()


async def _eis(klant: int) -> None:
    await _adapter()[0](klant)


def bewaakt_model_aanroep(functie: F) -> F:
    """Maakt van een async modelaanroep een bewaakte: eerst de stand, dan pas het model.

    Typering (gemeten 2026-10-24, mypy 2.3.0): `Callable[P, Awaitable[R]]` als resultaat verbreedt het
    returntype van elke bewaakte methode en breekt protocollen elders (`ILLMProvider.generate`);
    `Callable[P, CoroutineType[...]]` klopt niet met wat `functools.wraps` teruggeeft (97 fouten). Een
    gebonden TypeVar met `cast` laat de handtekening van de bewaakte functie PRECIES zoals ze was.
    """

    @functools.wraps(functie)
    async def bewaakt(*args: object, **kwargs: object) -> object:
        klant = _klant_van(args)
        if klant is None or _gecontroleerd.get() == klant:
            return await functie(*args, **kwargs)
        await _eis(klant)
        token = _gecontroleerd.set(klant)
        try:
            return await functie(*args, **kwargs)
        finally:
            _gecontroleerd.reset(token)

    return cast(F, bewaakt)


def bewaakt_model_stroom(
    functie: Callable[P, AsyncIterator[T]],
) -> Callable[P, AsyncIterator[T]]:
    """Zoals `bewaakt_model_aanroep`, voor een async generator (een stroom van brokken)."""

    @functools.wraps(functie)
    def bewaakt(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[T]:
        async def stroom() -> AsyncIterator[T]:
            klant = _klant_van(args)
            if klant is not None and _gecontroleerd.get() != klant:
                await _eis(klant)
            async for brok in functie(*args, **kwargs):
                yield brok

        return stroom()

    return bewaakt


def bewaak_modelmethoden(klasse: type, namen: Iterable[str]) -> None:
    """Bewaakt de genoemde methoden die `klasse` ZELF definieert. Voor `__init_subclass__`."""
    for naam in namen:
        functie = klasse.__dict__.get(naam)
        if inspect.isasyncgenfunction(functie):
            setattr(klasse, naam, bewaakt_model_stroom(functie))
        elif inspect.iscoroutinefunction(functie):
            setattr(klasse, naam, bewaakt_model_aanroep(functie))
