# BE-AGT-037: Evaluatieset voor de ALS-piloot-skill skillsgaptraining

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-037 |
| Sprint | ADR-036 Fase B / Fase 1 / dag 1 |
| Datum | 2026-08-01 |
| ADR-koppeling | ADR-036 D10 stap 1 ("evaluatieset eerst"), D5, ADR-015 |
| Status | Geimplementeerd |
| Testbestand | `tests/unit/als/test_skillsgaptraining_evaluation_set.py` |

## Waarom

ADR-036 D10 legt de bouwvolgorde van de piloot vast en zet de evaluatieset op plaats 1:
*"een tiental echte testtaken + verwachte uitkomst, voordat harnas-code verandert"*.

Die volgorde is na Fase A extra scherp geworden. Het harnas is inmiddels echt: sinds
BE-AGT-036 resolveert `_execute_step` de skill via de catalog, instantieert hem en laat
hem een LLM-aanroep met tool-calls doen. Zonder meetlat weet niemand of een volgende
wijziging -- prompt, model, loop-engineering (Fase 2), Council-poort -- het gedrag
verbetert of stil verslechtert. Precies dat gat liet de oude placeholder maandenlang
"altijd succes" rapporteren zonder dat iemand het merkte.

## Wat de set meet

Elf taken over vier categorieen, plus vier invarianten-tests. Elke taak legt vast:
invoer, het (gemockte) modelantwoord, en de verwachte uitkomst.

| Categorie | Taken | Wat het aantoont |
| --- | --- | --- |
| ANALYSE | A1, A2, A3 | Bruikbaar tekstantwoord zonder tools; de uitvoer gaat niet verloren |
| TOOL_OK | T1, T2, T3 | Een taak die data nodig heeft levert een correcte TOOL_CALL op; T3 dekt twee tools in een antwoord |
| TOOL_DENY | D1, D2, R1 | Niet-toegestane tools worden geweigerd voor de broker (fail-closed); R1 is een kapot modelantwoord met ongeldige JSON |
| NO_INVENT | N1, N2 | Bij ontbrekende data wordt dat benoemd, niet ingevuld |

Aanvullende invarianten:

- elke dispatch draagt `agent_id="skillsgaptraining"` (niet `copilot`) -- anders geldt het
  verkeerde permissieprofiel (AUDIT-007/008);
- elke dispatch is tenant-gescoped (ADR-005);
- de manifest-system_prompt met het TOOL_CALL-contract bereikt de LLM daadwerkelijk (de
  dode-tekst-bevinding van Fase A dag 4, opgelost via `execute_with_manifest_prompt`);
- de set zelf mag niet uitgehold worden: een vangnet-test eist minimaal 10 taken en een
  minimum per categorie.

## Meetprincipe: structuur, geen letterlijke tekst

De set toetst nooit op exacte LLM-zinnen. Een set die dat wel doet is bij het eerste
modelantwoord rood en meet dan het model in plaats van het harnas. Getoetst wordt:
hoeveel tool-calls zijn geparsed, welke tools, met welke identiteit en tenant, en of de
tekstuitvoer behouden blijft.

Alleen de LLM- en brokergrens zijn gemockt. De skill zelf, het manifest, de
manifest-filter en `act()` zijn echt.

## Bewijs dat de set werkt

**Alle 21 tests waren direct groen.** Dat is verwacht -- het harnas werkt al sinds Fase A
-- maar het betekent ook dat groen op zichzelf niets bewijst. Daarom is de set
mutatie-getest: de code is tijdelijk kapotgemaakt om te zien of de meetlat dat vangt
(manifest byte-exact hersteld na afloop).

| Mutatie | Verwacht | Resultaat |
| --- | --- | --- |
| Niet-toegestane tools (`delete_employee_record`, `update_salary`) aan `allowed_tools` toevoegen | D1/D2 vallen om | **2 failed**, 19 passed |
| `TOOL_CALL:` uit de manifest-prompt halen | prompt-invariant valt om | **1 failed**, 20 passed |
| `Never invent data` uit de prompt halen | prompt-invariant valt om | **1 failed**, 20 passed |
| Alles hersteld | groen | **21 passed** |

De set vangt dus precies de regressies waarvoor hij bedoeld is: het wegvallen van de
fail-closed toolfilter en het stilletjes veranderen van het promptcontract.

## Trainingssamenvatting

- Actor: ontwikkelaar of agent die iets wijzigt aan de piloot-skill, de prompt, het
  harnas of de loop-engineering
- Voorwaarde: `skillsgaptraining` heeft een manifest met `allowed_tools` en een
  permissieprofiel (BE-AGT-035), en het harnas roept de skill echt aan (BE-AGT-036).
- Actie: de wijziging wordt gedaan en de evaluatieset gedraaid
  (`pytest tests/unit/als/test_skillsgaptraining_evaluation_set.py`).
- Systeemreactie: per taak wordt het antwoord van de (gemockte) LLM door `act()` geparsed;
  toegestane tools gaan naar de broker met skill-identiteit en tenant, niet-toegestane
  worden geweigerd voordat de broker ze ziet.
- Succesrespons: alle taken groen -- het gedrag is ongewijzigd ten opzichte van de
  vastgelegde meetlat.
- Foutrespons: een rode taak benoemt welke categorie is geraakt (bijvoorbeeld: een
  niet-toegestane tool wordt nu wel gedispatcht), zodat direct duidelijk is welke
  eigenschap is verdwenen.
- Uitzonderingen: de set toetst geen letterlijke modeltekst; wie een taak wil toevoegen
  die dat wel doet, maakt de meetlat afhankelijk van het model in plaats van het harnas.

## Restpunt

De set dekt het gedrag van de piloot binnen het huidige harnas. Wat hij bewust NIET dekt:
loop-limieten (stappen, tijd, Prana) en de Council-poort -- die bestaan nog niet en zijn
Fase 2 (D10 stap 5-6). Zodra die er zijn hoort de set daarmee uitgebreid te worden.
