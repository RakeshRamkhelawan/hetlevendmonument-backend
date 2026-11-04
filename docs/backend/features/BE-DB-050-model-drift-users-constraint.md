# BE-DB-050 -- `users` miste de constraint waar twee foreign keys op steunen

| | |
|---|---|
| **ID** | BE-DB-050 |
| **ADR** | ADR-036 Fase D / OP-160 |
| **Sprint** | SP-RLS-SWITCH-001, fase 2 (fragment) |
| **Branch** | `fix/model-drift-constraints` |
| **Commits** | `c016b82c` |
| **Datum** | 2026-08-17 |

---

## 1. Het probleem in een zin

De migratie maakt een unique constraint waar twee samengestelde foreign keys op steunen;
het ORM-model maakt hem niet, dus op elke route die het schema met
`Base.metadata.create_all` bouwt ontbreekt zowel de constraint als de bescherming die
eraan hangt.

## 2. Wat er precies aan de hand was

`src/alembic/versions/20260529b_harden_user_persona_preferences_tenant_integrity.py`:

| regel | wat |
|---|---|
| 25 | `op.create_unique_constraint("uq_users_id_tenant", "users", ["id", "tenant_id"])` |
| 58-65 | `fk_user_persona_preferences_user_tenant` -> `users(id, tenant_id)` |
| 66-73 | `fk_user_persona_preferences_persona_tenant` -> `personas(id, tenant_id)` |

PostgreSQL staat een samengestelde foreign key alleen toe als er op het DOEL een UNIQUE
constraint over precies die kolommen ligt. De migratie maakt die dan ook, en de hele
migratie bestaat om die tenant-integriteit af te dwingen -- de naam zegt het.

Het model van `users` (`src/core/models/rbac_models.py`) had in `__table_args__` alleen:

```python
Index("idx_user_tenant_email", "tenant_id", "email", unique=True),
Index("idx_user_tenant_active", "tenant_id", "is_active"),
```

Geen `UniqueConstraint`. Het zusje `personas` draagt de zijne wel
(`src/core/models/persona_models.py:40`), dus dit is aantoonbaar een omissie en geen
bewuste keuze.

## 3. Waarom niemand het merkte

Dit is het deel dat het de moeite waard maakt om op te schrijven.

Elke unittest bouwt zijn schema met `Base.metadata.create_all`. Daar ontbrak de constraint,
en dus ook de foreign key die erop steunt. **Geen enkele test kon het betrappen, want in de
testomgeving bestond het ding niet.** De bescherming die de migratie moest opleveren was in
de hele testboom afwezig, en de afwezigheid was onzichtbaar.

## 4. De valkuil die de guard bewaakt

Een `Index(..., unique=True)` lijkt gelijkwaardig en is dat voor PostgreSQL ook -- een
unieke index is een geldig FK-doel. Maar **SQLAlchemy genereert er bij `create_all` geen
constraint voor**, en dan faalt de foreign key alsnog.

Twee tabellen zitten vandaag in precies die val: `user_cognitive_profiles` en
`user_twin_consent` hebben in de migratie een `UniqueConstraint` en in het model een
`Index(..., unique=True)`. Dat is een van de vier gevallen van vorm-/naamdrift die nog
openstaan.

Daarom toetst de guard de KOLOMMEN en niet de naam, en telt een unieke index bewust niet
mee.

## 5. Bewijs

```
rode test vooraf   rood op `users`, groen op `personas` -- exact de asymmetrie
volledige suite    zie de final-approver brief
pyright            0 errors
mypy-audit         0, baseline 0
ruff               All checks passed
```

## 6. Wat NIET is opgelost

Model-drift bleek geen los geval maar een patroon van drie. Twee blijven open:

| Tabel | Constraint in de migratie |
|---|---|
| `user_consents` | `uq_user_tenant_consent (user_id, tenant_id)` |
| `contact_opt_outs` | `uq_contact_opt_outs_tenant_contact_channel (tenant_id, contact, channel)` |

`contact_opt_outs` is bijzonder: het model documenteert de drift zelf in een comment die
nooit door de constraint is vervangen. Voor een AVG-opt-outtabel betekent dat op elke
`create_all`-omgeving meerdere opt-outrijen per persoon per kanaal, wat de "laatste
stand"-logica onbepaald maakt.

Daarnaast vier gevallen van vorm-/naamdrift, en `CheckConstraint`- en `ForeignKey`-drift
zijn NIET onderzocht. Gezien `uq_users_id_tenant` een FK-doelwit blijkt, is dat laatste
waarschijnlijk de volgende steen om om te draaien.

---

## Trainingssamenvatting

**Actor:** geen eindgebruiker -- dit raakt de schemadefinitie.

**Voorwaarde:** een omgeving waarvan het schema met `Base.metadata.create_all` is
opgebouwd in plaats van via de migratieketen.

**Actie:** een rij in `user_persona_preferences` schrijven met een `user_id` en een
`tenant_id` die niet bij elkaar horen.

**Systeemreactie:** de samengestelde foreign key weigert die rij.

**Succes:** een voorkeur kan niet aan een gebruiker uit een andere klantomgeving worden
gekoppeld.

**Fout:** ontbreekt de constraint op `users`, dan kan de foreign key niet bestaan en wordt
zo'n rij gewoon geaccepteerd -- zonder foutmelding.

**Uitzonderingen:** op een omgeving die wel via de migratieketen is opgebouwd, bestond de
bescherming al; deze wijziging brengt model en database met elkaar in overeenstemming.
