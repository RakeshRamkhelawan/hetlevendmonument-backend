# Review BE-DB-050 -- `users` miste de constraint waar twee foreign keys op steunen

| | |
|---|---|
| **Feature** | BE-DB-050 |
| **Branch** | `fix/model-drift-constraints` |
| **Commits** | `c016b82c` |
| **Datum** | 2026-08-17 |
| **Eindoordeel** | APPROVED WITH MINOR GAPS -- geen open CRITICAL of HIGH |

---

## 1. Verloop

Deze bevinding is niet uit een review gekomen maar uit het uitputtend onderzoeken van
OP-155, nadat Rakesh vroeg om fase 1 tot en met 3 grondig uit te zoeken. De opdracht was
onderzoek; dit was de enige vondst die zonder ontwerpkeuze meteen kon worden opgelost.

De aanleiding om er uberhaupt naar te kijken was een eerder gemelde drift op
`UserConsent`. Bij het natrekken bleek dat geen los geval maar een patroon van drie -- en
het zwaarste was niet degene die gemeld was.

## 2. Wat er is nagemeten en niet aangenomen

De keten die dit ernstig maakt, is regel voor regel zelf gelezen:

| Wat | Waar | Uitkomst |
|---|---|---|
| de constraint bestaat in de migratie | `20260529b:25` | `op.create_unique_constraint("uq_users_id_tenant", "users", ["id", "tenant_id"])` |
| er hangt een samengestelde FK aan | `20260529b:58-65` | `["user_id", "tenant_id"] -> ["id", "tenant_id"]` op `users` |
| het model heeft hem niet | `rbac_models.py` `__table_args__` | alleen twee `Index`-regels |
| het zusje heeft hem wel | `persona_models.py:40` | `uq_personas_id_tenant` |

Die laatste regel is wat "omissie" van "keuze" onderscheidt. Zonder die vergelijking was
het een vermoeden gebleven.

## 3. Het rode bewijs

De guard was rood op `users` en groen op `personas` -- exact de asymmetrie die de vier
metingen hierboven voorspellen. Dat is een sterker rood bewijs dan een enkele falende
assertie: het toont aan dat de guard onderscheid maakt en niet simpelweg alles afkeurt.

## 4. Waar ik bij deze guard op heb gelet

Vandaag zijn drie guards van mijzelf hol gebleken, alle drie door te grof te koppelen.
Daarom hier expliciet:

- De guard loopt over een BENOEMDE verzameling FK-doelen, geen zoektocht. In vijf seconden
  te controleren.
- Hij vergelijkt de KOLOMMEN, niet de constraintnaam. Een naamswijziging is geen defect;
  een andere kolomverzameling wel.
- Een `Index(..., unique=True)` telt bewust NIET mee. Dat is de tegenrichting die er hier
  toe doet: PostgreSQL accepteert zo'n index wel als FK-doel, maar SQLAlchemy genereert er
  bij `create_all` geen constraint voor. Twee tabellen zitten vandaag in precies die val.

## 5. Wat OPENSTAAT

| Wat | Status |
|---|---|
| `user_consents` -- `uq_user_tenant_consent` | OPEN |
| `contact_opt_outs` -- `uq_contact_opt_outs_tenant_contact_channel` | OPEN; het model documenteert de drift zelf in een comment die nooit is vervangen |
| vier gevallen van vorm-/naamdrift | OPEN, geen gedragsbreuk maar wel luidruchtige `autogenerate` |
| `CheckConstraint`- en `ForeignKey`-drift | NIET onderzocht |

Dat laatste is de meest waarschijnlijke volgende steen: `uq_users_id_tenant` bleek een
FK-doelwit, dus de aanname dat constraints en foreign keys los van elkaar staan gaat hier
niet op.

## 6. Bewijs

```
c016b82c   rode test vooraf: rood op `users`, groen op `personas`
           2275 gerichte tests groen
           volledige suite, pyright 0, mypy 0, ruff schoon, doc-gate 0
```

## 7. Eindoordeel

**APPROVED WITH MINOR GAPS.** Een klein wijzigingsoppervlak (een constraint plus een
import) met een groot effect: de tenant-integriteit die de migratie moest opleveren was in
de hele testomgeving afwezig, en de afwezigheid was per constructie onzichtbaar. De twee
resterende drifts staan geregistreerd en zijn niet stil ingekort.
