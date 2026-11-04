# Backend Feature Specification

## Metadata

- **Feature ID:** BE-HR-AIV-001
- **Feature naam:** AI-verordening voor de pilot -- uitleg bij elk opleidingsvoorstel, ook voor de medewerker zelf
- **Status:** In uitvoering (code en tests geschreven; Gate 2 loopt; acceptatie met beeld nog te doen)
- **Auteur:** bouwer aipilot (sessie sanskritisetu-org-bd)
- **Reviewer:** code-reviewer + quality-reviewer (subagents, Gate 2)
- **Datum:** 2026-10-14
- **Gerelateerde user story / ticket:** brief `docs/agent-briefs/generated/2026-10-12-sprint-dag-ai-verordening-voor-de-pilot.md`; onderzoek `docs/onderzoek-ai-verordening-hr-pakket-hoog-risico.md` (art. 13, art. 26, art. 86)
- **Gerelateerde router / module:** `src/core/api/v1/hr/training_proposals_router.py`, `src/core/api/v1/hr/my_training_proposals_router.py`, `src/core/repositories/hr_training_proposals_repository.py`
- **Gerelateerde frontend endpoints:** `frontend/src/pages/PersoneelPage.tsx` (uitleg per voorstel, links naar de teksten)
- **Gerelateerde database tabellen:** `training_proposals`, `skills`, `role_required_skills`, `employee_skills`, `user_roles` (alleen lezen; GEEN migratie)
- **Versie:** 1.0

## Doel en scope

### Doel

Bij elk opleidingsvoorstel hoort een uitleg in gewone taal: welke vaardigheid, welk niveau gevraagd en
gemeten, uit welke beoordeling (datum), dat het voorstel met vaste regels is gemaakt en dat een mens
besluit. HR ziet die uitleg bij elk voorstel; de medewerker kan de uitleg van ZIJN eigen voorstellen
opvragen. Daarnaast liggen de vier standaardteksten voor de klant in `docs/klant/hr-pakket/`.

### In scope

- `GET /api/v1/hr/training-proposals`: elk voorstel krijgt een veld `explanation`.
- `GET /api/v1/hr/training-proposals/{id}/explanation` (`hr:read`).
- `GET /api/v1/hr/my-training-proposals` en `.../{id}/explanation`: alleen de voorstellen van de aanroeper.
- De verouderde docstring in `src/core/models/hr_skills_models.py` bijgewerkt naar de gemeten stand.
- Vier teksten voor de klant, de pagina Personeel linkt ernaar.

### Buiten scope

- Conformiteitsdossier, CE-markering, EU-registratie (voor 2 december 2027, eigen brief).
- Een scherm voor de medewerker zelf (alleen de route bestaat; er is nog geen medewerkersscherm).
- Een bias- of nauwkeurigheidsmeting van de voorstellen.

## Stap 0 -- wat is gemeten (2026-10-14, commit 994beb91)

1. **Zit er een taalmodel in het maken van een voorstel?** Nee. Rijen in `training_proposals` ontstaan
   uitsluitend via `POST /training-proposals` -> `HRTrainingProposalsRepository.create_from_gap`, een
   SQL-vergelijking van `EmployeeSkill.level < RoleRequiredSkill.required_level`. De `reason` is een
   f-string. Meting: `git grep create_from_gap -- src` geeft alleen de router en de repository.
2. **Wat doet de agent `skillsgaptraining` wel?** Zijn manifest zegt `technology: llm`. Zijn skillmodule
   (`skills/skillsgaptraining.py`) roept een taalmodel aan voor een vrije-tekstadvies en mag via de
   broker de tools `query_hr_database`, `analyze_skill_gap` en `schedule_training` aanroepen. Hij maakt
   geen `training_proposals`-rijen. Het pilotpakket `hr.reskilling_engine` bevat alleen deze agent
   (`config/domain_packs.yaml`); interne mobiliteit en tevredenheidsmeting zijn uitgesteld.
3. **Wat doet `annex_iii_classification: annex_iii` nu al?** Alle vier de HR-skills staan erop. In de
   code gebruikt alleen `BaseSpecialistAgent._floor_applies_to` (specialist_base.py) het: bij
   `human_in_the_loop: hitl` gaat dan ELKE actie, ook lezen, langs een mens. De docstring in
   `hr_skills_models.py` zei dat `skillsgaptraining` nog op `none` stond; dat was verouderd en is
   bijgewerkt.
4. **Niet gemeten:** de nauwkeurigheid van de voorstellen, vooringenomenheid, en of het taalmodel in de
   agent in de pilot daadwerkelijk wordt aangeroepen met persoonsgegevens (de tool `analyze_skill_gap`
   levert aftellingen per rol en vaardigheid).

## Gedrag

### De uitleg (`build_explanation`)

Velden: `proposal_id`, `skill`, `training`, `required_level`, `measured_level`, `assessed_at`,
`reassessed_since_proposal`, `reason_at_proposal`, `rule_based` (altijd waar), `human_decides` (altijd
waar), `status`, `created_at`, `decided_at`, `text` (gewone taal) en, alleen voor HR, `decided_by_email`.

- `required_level`: het hoogste niveau dat een van de functies van de medewerker voor de vaardigheid
  eist (`MAX` over `role_required_skills` van zijn functies).
- `measured_level` en `assessed_at`: de HUIDIGE beoordeling uit `employee_skills`. Is die beoordeeld na
  het maken van het voorstel (`assessed_at > created_at`), dan staat `reassessed_since_proposal` aan en
  zegt de tekst dat; `reason_at_proposal` blijft de bevroren tekst van toen.
- Haalt het huidige niveau de eis nu wel (`measured_level >= required_level`), dan zegt de tekst dat
  eerlijk ("haalt de eis nu; het voorstel is gemaakt toen het niveau lager was") en NIET "onder de
  eis" (Gate 2, 2026-10-14).
- `required_level` is het HOOGSTE niveau over alle functies van de medewerker die die vaardigheid
  eisen; `reason_at_proposal` noemt de ene functie waarvoor het voorstel is gemaakt. Heeft iemand twee
  functies met een eis voor dezelfde vaardigheid, dan kan het getoonde vereiste niveau hoger zijn dan
  de eis van die ene functie. Bekende beperking, niet opgelost.
- Voor de medewerker ontbreekt `decided_by_email`: hij ziet WAT er besloten is, niet welke collega.

### Autorisatie en tenant

- HR-route: `hr:read`. Eigen route: ingelogd; de medewerker is `current_user.id` uit de JWT.
- `tenant_id` komt uit de JWT-context, nooit uit het verzoek (een `tenant_id` in de query wordt genegeerd).
- Een voorstel van een collega of van een andere tenant is via de eigen route "niet gevonden" (404, geen
  403): een 403 zou verklappen dat het voorstel bestaat.
- Elke query filtert expliciet op `tenant_id` (`_rijen_query`).

### Foutcodes

| Situatie | Code |
|---|---|
| Voorstel bestaat niet, is van een collega of van een andere tenant | 404 |
| Niet ingelogd | 401 |
| HR-route zonder `hr:read` | 403 |

## Afhankelijkheden

- Geen migratie, geen nieuwe tabel, geen nieuwe dependency.
- `build_explanation` is een zuivere functie; ze staat in de repository-module en wordt via
  `src/core/api/v1/hr/dependencies.py` aan de routers gegeven (ADR-033).

## Trainingssamenvatting

### Uitleg bij een voorstel bekijken (HR)

- Actor: medewerker van personeelszaken met leesrechten
- Voorwaarde: er bestaat een opleidingsvoorstel in de eigen organisatie
- Actie: opent de pagina Personeel
- Systeemreactie: onder elk voorstel staat een uitleg met vaardigheid, niveaus, beoordelingsdatum en de zin dat een mens besluit
- Succes: de uitleg is leesbaar zonder iets te openen
- Fout: zonder leesrechten ziet de gebruiker geen voorstellen en geen uitleg
- Uitzonderingen: is de vaardigheid opnieuw beoordeeld na het voorstel, dan zegt de uitleg dat

### Eigen voorstel en uitleg opvragen (medewerker)

- Actor: medewerker met een opleidingsvoorstel
- Voorwaarde: ingelogd in de eigen organisatie
- Actie: vraagt zijn eigen voorstellen of de uitleg van een eigen voorstel op
- Systeemreactie: alleen eigen voorstellen met uitleg, zonder naam of e-mailadres van de besluitnemer
- Succes: de medewerker leest waarom de opleiding is voorgesteld
- Fout: het voorstel van een collega of van een andere organisatie geeft "niet gevonden" (404)
- Uitzonderingen: een `tenant_id` in het verzoek wordt genegeerd

### Standaardteksten voor de klant lezen

- Actor: medewerker van personeelszaken met leesrechten
- Voorwaarde: pagina Personeel is geopend
- Actie: klikt een link onder "Teksten voor uw organisatie"
- Systeemreactie: de tekst opent in een nieuw tabblad, met de kop "Concept -- laat uw jurist dit toetsen"
- Succes: de vier teksten zijn bereikbaar
- Fout: zonder leesrechten zijn de links niet zichtbaar (de bestanden zelf zijn statisch en met de URL zonder inloggen op te halen; er staat niets gevoeligs in)
- Uitzonderingen: de teksten beloven geen juridische zekerheid en noemen wat niet is gemeten

## Regressierisico's

- De uitleg gebruikt het HUIDIGE niveau; wie de beoordeling wijzigt, wijzigt de uitleg van een open
  voorstel. Dat staat in de tekst (`reassessed_since_proposal`).
- De kopieen van de teksten in `frontend/public/klant/hr-pakket/` moeten gelijk blijven aan de bron;
  bewaakt door `tests/architecture/test_klantteksten_hr_pakket.py`.
