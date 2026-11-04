# Review BE-DATA-001 — Agentic-domain tenant_id NOT NULL + RLS + live Alembic-keten

## A. Eindoordeel

APPROVED WITH MINOR GAPS

## B. Samenvatting

De specificatie beschrijft een substantiele hardening van 9 agentic-domain tabellen: `tenant_id NOT NULL`, RLS-policies en een nieuwe live migratie. De broncode in `src/domains/agentic/models.py` toont inderdaad `nullable=False` op de betrokken modellen. De spec is ongewoon gedetailleerd over testbewijs, revisiegeschiedenis en pre-existing bevindingen (gebroken historische Alembic-keten, seed-scripts die breken).

## C. Bevindingen per categorie

### 1. Coverage gaps

- De spec noemt migratie `884d744f6aa9` maar geeft geen bestandspad. TODO: migratiepad toevoegen zodat reviewers het kunnen verifiëren zonder te zoeken.
- De spec noemt 8 tabellen met RLS en `tenant_id NOT NULL`, maar `prompt_experiment_variants` heeft geen eigen `tenant_id`. Dit is correct toegelicht via de FK-relatie, maar een expliciete lijst van welke 8 tabellen RLS hebben ontbreekt.

### 2. Functionele onduidelijkheden

- Duidelijk: doel is tenant-isolatie op DB-niveau.
- De "pre-existing" bevinding over de gebroken Alembic-keten (`audit_logs` nooit aangemaakt) staat expliciet als niet-vandaag-opgelost. Dat is correct gescheiden van de scope.

### 3. Technische onduidelijkheden

- De fix van `sa.inspect(op.get_bind())` naar raw SQL `CREATE TABLE IF NOT EXISTS` is gedetailleerd beschreven, inclusief reproduceerbare crash (`alembic upgrade head --sql`).
- De nieuwe architecture-test `test_no_sa_inspect_in_migrations.py` is benoemd.

### 4. Ontbrekende foutstatussen en edge cases

- De Trainingssamenvatting noemt `IntegrityError` bij ontbrekende `tenant_id`. Dat is correct.
- Een edge case ontbreekt: wat gebeurt er bij een downgrade van de migratie als er al productiedata in de 9 tabellen staat? De spec zegt "pre-launch, geen productiedata", maar `DROP TABLE IF EXISTS` verwijdert wel data. Dat is acceptabel gegeven de context, maar verdient een waarschuwing.

### 5. Acceptatiecriteria problemen

- De criteria zitten verschanst in testbewijs-blokken. Een expliciete checklist ontbreekt, maar de testnamen dekken het wel.

### 6. Integratorhandleiding / API-uitleg problemen

- Niet van toepassing op DB-migratie. De Trainingssamenvatting geeft voldoende context.

### 7. Trainingsdata problemen

- De Trainingssamenvatting is in bullet-vorm i.p.v. tabel, maar bevat alle verplichte velden. Geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- De spec is een compact feature-note. Dat past bij een audit-fix, maar is inconsistent met het volledige backend template.
- De sectie "Reviewers" vermeld een "Final Approver" die oorspronkelijk NO-GO gaf en daarna GO. Dat is waardevolle context, maar hoort formeel onder een afzonderlijke review-brief of in de spec-status.

### 9. Risico's voor implementatie, security of QA

- De gebroken historische Alembic-keten is een pre-existing risico dat niet in deze scope wordt opgelost. Correct gemarkeerd als prioritair actiepunt voor Rakesh.
- De seed-scripts die breken (backlog SP-DATA-ARCH-1) zijn expliciet vastgelegd.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | Backend inventory / migratie | Migratiebestandspad ontbreekt | Reviewers kunnen de migratie niet direct vinden | Voeg toe: `src/alembic/versions/884d744f6aa9_*.py` |
| Low | Trainingssamenvatting / edge case | Gedrag bij downgrade met data niet benoemd | `DROP TABLE IF EXISTS` is destructief | Noteer expliciet dat deze migratie niet bedoeld is voor productiedata en dat een downgrade data wist |

## E. Ontbrekende items

- Geen functioneel ontbrekende items binnen scope.

## F. Verbeterde tekstvoorstellen

- "Nieuwe live migratie `884d744f6aa9`" -> "Nieuwe live migratie `src/alembic/versions/884d744f6aa9_add_agentic_domain_tables.py`".

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja, met de kanttekening dat de historische Alembic-keten nog steeds niet vanaf nul bootstraapt.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja, met bovenstaande minor gaps.
- Geschikt voor integratorhandleiding / API-documentatie: beperkt; dit is een intern DB-hardening item.
