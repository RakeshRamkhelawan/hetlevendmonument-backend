STATUS: APPROVED
# Backend Feature Review -- BE-CRD-001

## Metadata

- Feature ID: BE-CRD-001
- Feature naam: Crediteuren dag 1: leveranciers en inkoopfacturen vastleggen
- Review datum: 2026-10-24
- Reviewers: security-reviewer en code-reviewer (subagents), een ronde Gate 2 op de commits a443bd70 en ee4218cf; zelfreview op de verwerking
- Spec locatie: `docs/backend/features/BE-CRD-001-crediteuren-dag1-inkoopfacturen-vastleggen.md`

---

## Eindoordeel

**APPROVED** na verwerking. Beide reviewers gaven CHANGES_REQUESTED; elke bevinding is door de bouwer zelf nagemeten voordat iets is aangenomen (de reviewers hadden niets kunnen draaien en redeneerden). Alle HIGH en MEDIUM zijn gerepareerd met een rode test eerst, behalve wat hieronder als dag 3 en 4 is vastgelegd. Een tweede ronde is niet gevraagd; het maximum is twee.

## Bevindingen en afhandeling

| ID | Ernst | Bevinding | Gemeten door de bouwer | Afhandeling |
|---|---|---|---|---|
| S-1 | HIGH | `*:read` gaf elke medewerker met de rol `user` de IBAN's en alle inkoopfacturen: `payables` stond niet in `EXPLICIT_RESOURCES` | ja: een eigen test met een rol met alleen `*:read` kreeg 200 | `EXPLICIT_RESOURCES = {hr, payables}` (ook `rechten.ts`); 5 tests rood, nu groen; mutatie G1 rood |
| C-H1 | HIGH | een falende auditregel gaf een 500 na een geslaagde commit (`best_effort` rolt terug, het object verloopt) | ja: vier tests rood met `MissingGreenlet` | het antwoord wordt voor de auditregel opgebouwd; mutatie A1 rood. Hetzelfde patroon staat in `receivables/router.py` (gemeld, niet aangeraakt) |
| S-2 / C-M2 | MEDIUM | uniciteit op de exacte tekst: "Acme BV" en "acme bv", "INK-1" en "ink-1 " | ja: 9 tests rood | unieke indexen op `lower(...)`, strip in schema en repository; mutaties P12 (gelijkwaardig: de index vangt het) en G5 rood |
| S-3 | MEDIUM | `_EEN_REGEL` liet U+2028, U+0085, bidi-omkering en nulbreed door | ja: 6 van 10 tekens kwamen erdoor | patroon met `\p{Cc}\p{Cf}\p{Zl}\p{Zp}`; mutatie A3 rood |
| S-4 / C-L2 | MEDIUM | `set_status` leest zonder rijslot: twee gelijktijdige wijzigingen | alleen de SQL: de test eist `FOR UPDATE` in de query | `with_for_update(of=Payable)`; mutatie P13 rood. Echte gelijktijdigheid is niet gemeten |
| C-M1 | MEDIUM | het scherm vroeg de standaard 50: de 51e leverancier ontbrak in de keuzelijst | ja: de client riep zonder limiet aan | maximum van de API (1000) en een waarschuwing bij 1000 |
| C-F1 | MEDIUM | geen slot tegen dubbelklik op geld | de uitgeschakelde knop vangt een tweede klik; het slot beschermt het formulier zelf | slot (ref) plus uitgeschakelde knoppen; mutatie F4 rood met een test op het formulier |
| C-M3 / S-7 | LOW | elke `IntegrityError` heette "al vastgelegd" | ja: rode test met een sleutelfout | alleen een botsing op DE unieke index; de rest wordt gelogd en doorgegeven |
| C-L1 | LOW | "ontvangen" gaf "hoort bij een latere stap" | ja | gewone tekst "kan niet van ... naar ..." |
| S-12 | LOW | IBAN zonder landlengte | ja: een NL-IBAN van 17 tekens met kloppende som kwam erdoor | lengte per SEPA-land (36 landen); onbekende landen houden de controlesom; mutaties P8 en P9 rood |
| C-F2 / F3 / F4 | LOW | niet herladen na een mislukte controle; geen "opnieuw proberen" bij mislukt laden; tabel zonder naam en `scope` | F2 en F4 gemeten | F2 en F4 opgelost (mutatie F5 rood); F3 bewust niet, zie FE-PGS-037 |
| S-5, S-9, S-12 (valuta) | MEDIUM tot LOW | goedkeurder en invoerder na AVG-wissing; IBAN-wijziging zonder spoor; auditregel buiten de transactie; valuta en SEPA | n.v.t. | ontwerpinput voor dag 3 en 4, vastgelegd in de spec onder "Bewust laten liggen" |
| S-6, S-10, S-11, S-13, S-8 | LOW | RLS beschermt nog niets (OP-151); `TESTING` in productie; downgrade met gegevens; 409-tekst met een zwarte lijst; statusfilter 409 | n.v.t. | niet nieuw of bewust; genoteerd. De downgrade laat tabellen met gegevens vallen: voor uitvoer op een omgeving met echte facturen eerst aankondigen (interlock 1) |

Wat de reviewers positief vonden en de bouwer bevestigde: elke repositorymethode filtert op `tenant_id` en heeft een isolatietest; de samengestelde sleutel; `payables:approve` bestaat niet en `approve` zit in `EXPLICIT_ACTIONS`; geen IBAN of bedrag in de auditregels; de routers blijven onder de grenzen van ADR-033.

## Mutatiebewijs (wegwerp-worktree, kopie als terugweg)

28 mutaties; 24 rood, 1 aangepast en dan rood (F4: er kwam een test op het formulier bij), 3 gelijkwaardig (een tweede laag vangt het).

- **Repository en tenant:** P1 tot P5 (geen tenantfilter op get en lijst van beide repositories, geen leverancierstoets): rood.
- **Statusverloop en invoer:** P6 (later stap al toegestaan), P7 (bedrag nul), P8 en P9 (IBAN-controle en -lengte), P10 en P11 (wie vastlegde en controleerde), P13 (rijslot): rood.
- **API en rechten:** A1 (antwoord na de audit), A2 (schrijven vraagt alleen lezen), A3 (Unicode-tekens), G1 (jokerrecht): rood.
- **Migratie onder de applicatierol:** G2 (geen RLS), G3 (policy `USING true`), G4 (geen samengestelde sleutel), G5 (factuursleutel zonder `lower`), G6 (geen bedrag-CHECK): rood.
- **Scherm:** F1 (bedrag als komma-getal), F2 (Engelse terugvaltekst), F3 (schrijfknoppen voor iedereen), F4 (geen slot), F5 (niet herladen), F6 (menu volgt een ander recht), F8 (jokerrecht in het scherm): rood.
- **Gelijkwaardig:** P12 (de hoofdletterongevoelige controle in de repository: de unieke index vangt de dubbele), A4 (spaties niet strippen in het schema: de repository strip ook), F7 (`padEnd` in `euroNaarCenten`: `parseBedrag` vult al aan). Twee lagen houden elkaar in evenwicht; elke laag heeft een eigen test op het gedrag.

## Niet gemeten

De volledige tests/architecture-ronde en de volledige vitest-ronde (zie de eindmelding); echte gelijktijdigheid; de acceptatie met beeld; staging en productie.
