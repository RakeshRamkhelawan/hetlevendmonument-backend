# Review: BE-SEC-051 -- Autorisatiecluster (ADR-036 OP-254/255/256/257/258, OP-189, OP-199)

**STATUS: APPROVED WITH MINOR GAPS**
**Datum:** 2026-09-18
**Branch:** `iter/op154-inlogpad`
**Reviewers:** code-reviewer en security-reviewer (Gate 2), plus nameting door de auteur

---

## Ronde 1 -- beide reviewers: CHANGES_REQUESTED op het oorspronkelijke ontwerp

Het eerste ontwerp voor OP-254 was: cache-invalidatie bijbouwen op alle zes de plekken die
rechten wijzigen. Beide reviewers wezen dat onafhankelijk af met hetzelfde argument: meet
eerst of de cache zijn prijs waard is, want een invalidatieplicht op zes plekken is precies
de vorm die het probleem heeft veroorzaakt.

**Verwerkt.** De meting (mediaan 2,18 ms, p95 2,85 ms, een of twee controles per verzoek,
nul aanroepers in een lus) leidde tot het kleinere en veiligere besluit: de cache is
verwijderd. Dat is het belangrijkste inhoudelijke resultaat van deze reeks, en het kwam van
de review en niet van de auteur.

De security-reviewer bracht in dezelfde ronde twee bevindingen in die als OP-256 en OP-257
zijn geregistreerd en in deze reeks gesloten.

---

## Nameting door de auteur (niet door de reviewers)

1. **Een claim van de auteur was onjuist en is gecorrigeerd.** Ik meldde dat ook de
   revoke-richting cache-blijvend was. Bij hermeten via de echte servicemethodes bleek dat
   fout: ik had de rol met rauwe SQL verwijderd en daarmee de invalidatie in `revoke_role`
   omzeild. Expliciet gecorrigeerd richting Rakesh.
2. **Een reviewer overdreef licht.** De claim "de gewone negatieve uitkomst wordt niet
   gecachet" is nagelopen en onjuist: de `if not permissions:`-tak WERD gecachet; alleen het
   conditions-false-pad niet. Niet op gezag aangenomen.
3. **De eerste versie van de OP-258-guard was blind.** Uitzonderingslijst op bestandsniveau;
   alle drie de voorwaartse mutaties bleven groen. Betrapt door het eigen mutatiebewijs,
   herschreven naar `bestand::functie`, opnieuw gemuteerd, nu rood waar het rood hoort.
4. **De eerste versie van een retentiebewaker was hol** (eerdere rij in dezelfde sessie,
   zelfde patroon): hij toetste alleen de nieuwe helper, niet het gedrag.

---

## Gates

| Gate | Uitkomst |
| --- | --- |
| Gate 1 -- plan | Sprintbrief `docs/agent-briefs/generated/2026-09-18-sprint-dag-autorisatiecluster-op254-op189-op199.md`, snippets gestempeld op commit `043a54ea` |
| Gate 2 -- review | CHANGES_REQUESTED in ronde 1, verwerkt; daarna GO |
| Gate 3 -- meting | pyright 0 errors, ruff schoon, mypy-baseline ongewijzigd |
| Testpoort | 16657 passed, 170 skipped, 20 xfailed, 0 failed |
| Register | `list_adr036_open_items.py --diff-against`: -4 en -2, netto 84 -> 77, nieuw open geen |

---

## Bevindingen die BLIJVEN openstaan

| ID | Ernst | Bevinding |
| --- | --- | --- |
| FA-051-1 | MINOR | Geen guard op het SCHRIJFpad van `is_superuser`. Gemeten dat geen request-schema het veld kent, maar niets dwingt dat af. Wie het aan een update-schema toevoegt, maakt van een bootstrapvlag een escalatiepad zonder dat een test rood wordt. |
| FA-051-2 | MINOR | "Gedrag identiek" bij OP-258 is gelezen, niet bewezen: er is geen vergelijkingstest tussen het oude en het nieuwe rol-toewijspad, want het oude bestaat niet meer. |
| FA-051-3 | MINOR | Twee plekken schrijven bewust nog rauw op `user_roles` (transactioneel), met gedateerde uitzondering en staleness-test. |
| FA-051-4 | MINOR | De prestatiemeting achter het verwijderen van de cache is gedaan op een testdatabase met weinig rijen. Bij een klant met duizenden permissierijen is het niet dezelfde query. |

Geen BLOCKERS.

---

## Devil's Advocate -- waarom dit alsnog faalt

**1. De cache is weg, en dat wordt een prestatieklacht op de dag dat er verkeer is.** De
juiste reactie is dan meten en indexeren; de verleidelijke reactie is de cache terugzetten,
en wie dat doet krijgt OP-254 gratis mee. De vier metingen staan daarom in de docstring van
`RBACService` en niet alleen in dit document.

**2. De guards bewaken de VORM, niet de werking.** Beide nieuwe architecture-tests toetsen
dat een aanroep door de juiste functie gaat, niet dat die functie het goede antwoord geeft.
Dat is bewust -- daar zijn de gedragstests voor -- maar een volgende sessie die "de guard is
groen" leest, kan denken dat het gedrag bewaakt is.

**3. OP-189 is gesloten op een meting die morgen kan verlopen.** Zie FA-051-1. Dit is de
zwakste plek van de hele reeks en hij is met opzet als eerste in de "niet gedaan"-lijst
gezet.

**4. Vier tests zijn verwijderd in plaats van gerepareerd.** Elk met een geschreven reden op
de plek waar de test stond. Verwijderen is de goedkoopste manier om een suite groen te
krijgen; dit is het punt waarop een volgende reviewer het scherpst moet kijken.

---

## Openstaand voor Rakesh

Niets blokkerends. De vier MINOR-bevindingen zijn geregistreerd in dit document en in
sectie K van de spec; geen ervan blokkeert aantoonbaar iets vandaag, en geen ervan krijgt
daarom een eigen guard (conform de uitzondering op de NOOIT-lijst voor bevindingen waarvan
GEMETEN is dat ze vandaag niets blokkeren).
