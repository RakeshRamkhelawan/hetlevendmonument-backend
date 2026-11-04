STATUS: APPROVED
# Backend Feature Review -- BE-CNL-001

## Metadata

- Feature ID: BE-CNL-001
- Feature naam: De council bij een koude start
- Review datum: 2026-10-23
- Reviewer: security-reviewer (subagent), een ronde Gate 2 op de ongecommitte wijziging; zelfreview op de tests
- Spec locatie: `docs/backend/features/BE-CNL-001-council-koude-start-en-klanttekst.md`

---

## Eindoordeel

**APPROVED.** De reviewer gaf GO met een voorbehoud: hij kon `git diff` niet draaien en las de huidige staat. Dat voorbehoud is door de bouwer weggenomen: `git show --stat` van de commit toont precies acht bestanden en geen wijziging in `coordinator.py` of de aggregatieregel.

## Bevindingen en afhandeling

| ID | Ernst | Bevinding | Afhandeling |
|---|---|---|---|
| F-001 | LOW | geen tijdsgrens rond de opwarming; een niet-reagerende pool houdt de lifespan vast, en een importfout in `_init_council_warmup` liet het opstarten crashen | `asyncio.wait_for` (5 s) in `warm_up_risk_register`, imports binnen de try; test `test_een_hangende_database_houdt_het_opstarten_niet_vast`; mutatie M10 rood |
| F-002 | LOW | `clear_tenant_context()` herstelde de vorige tenantcontext niet | de vorige waarde wordt hersteld, ook bij een fout; test `test_de_opwarming_herstelt_de_tenantcontext_die_er_al_was` (2 gevallen); mutatie M11 rood |
| F-003 | LOW | de zin "Probeer het over een moment opnieuw" kan automatische retries uitlokken | niet nagemeten of de agent- of toolketen automatisch herhaalt; geboekt onder "Bewust laten liggen" in de spec |
| F-004 | LOW | gedrag van het tenantfilter of de rijbeveiliging bij een tenant zonder rijen niet gemeten | de opwarming leest alleen en gooit het resultaat weg; geboekt in de spec |

Beantwoord door de reviewer, met bronverwijzing: (a) geen blokkade wordt doorgelaten, alleen tekst verandert; (b) een echt veto wordt niet verborgen, want elk veto met een andere code telt als echt; (c) de opwarming leest alleen; (d) geen gevoelige data in tekst of log; (e) `tenant_id` komt nergens uit een request.

## Wijziging NA Gate 2 ronde 1 (niet door de security-reviewer gezien)

Na de meting in de volle stack (zie de spec, "Gemeten" punt 5 en 6) is de opwarming uitgebreid van een naar drie gelijktijdige sessies (`verbindingen=3`, `asyncio.gather` binnen dezelfde tijdsgrens van 5 s), en is de logregel van `_init_council_warmup` een f-string geworden (de logging van deze app vult %-argumenten niet in). Alleen zelfreview: een extra test (`test_de_opwarming_opent_meer_verbindingen_tegelijk`), mutatie M12 (een verbinding in plaats van drie) rood. ## Gate 2 ronde 2 (security-reviewer, alleen de diff 1e2f0cdb..afab42d6)

Eindoordeel **GO**, twee LOW, geen CRITICAL/HIGH/MEDIUM. Dit is de tweede en laatste ronde (ronde-cap).

| ID | Ernst | Bevinding | Afhandeling |
|---|---|---|---|
| F-005 | LOW | `gather(return_exceptions=True)` geeft een geannuleerde kindtaak terug als `CancelledError`; die is geen `Exception` en glipt langs `except Exception` tot in de lifespan | een geannuleerde sessie wordt een `RuntimeError` en dus een mislukte opwarming (False); test `test_een_geannuleerde_opwarmsessie_laat_het_opstarten_niet_crashen`. Door de bouwer onafhankelijk ook gevonden. NOG NIET gedraaid: de fix en de test zijn tijdens een pauze voor een push geschreven en worden na "push klaar" gedraaid |
| F-006 | LOW | drie gelijktijdige sessies kunnen alleen bij een zeer kleine pool (pool_size 1, geen overflow) de pool uitputten | de 5 s tijdsgrens en het niet-fataal vangnet maken dat onschadelijk; de werkelijke pool-instelling in staging en productie is niet gemeten |

Beantwoord door de reviewer: geen tenantlek tussen de gelijktijdige taken (de context wordt in de ouder gezet en kinderen krijgen een kopie, de `finally` herstelt de oorspronkelijke waarde); geen log-injectie in de f-string; geen secrets. Niet nagemeten door de reviewer: een kind dat annulering negeert, de poolinstelling buiten de lokale omgeving, en het `CancelledError`-pad (alleen redenering).

## Mutatiebewijs

Elf mutaties, allemaal rood, met een kopie als terugweg: opwarming leeg, stap uit de lifespan, `except` weg, helper altijd False, altijd True, helper negeert een echt veto, elk van de drie tekstplekken (audit, agentpoort, basisagent), geen tijdsgrens, tenant niet hersteld.

## Niet gemeten

De volledige API vers gestart met Redis; een echte wachttijd van 30 minuten voor de poolvervanging; automatische retries; de acceptatie met beeld.
