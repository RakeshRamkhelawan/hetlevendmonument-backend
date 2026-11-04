# Doc-gate uitzonderingen

`scripts/validate_feature_docs.py` leest dit bestand. IDs die hieronder staan worden
gerapporteerd als `[PENDING]` en laten de gate niet falen. **Elk ander incompleet ID
faalt wel.** Zonder dit mechanisme stond de gate permanent rood op bekende, geaccepteerde
gevallen -- en een gate die altijd rood staat, leest niemand meer. Dat is precies het
patroon dat OP-11 heeft opgelost bij de unit- en integratiesuite.

## Regels

1. Een ID mag hier alleen staan met een **datum**, een **reden** en een **eigenaar**.
2. Een ID hier laten staan is geen oplossing, maar een expliciet uitstel. De lijst wordt
   bij elke sprint-afsluiting doorgelopen.
3. Wordt een ID hier compleet gedocumenteerd, dan meldt de validator dat als
   `[PENDING-RESOLVED]` met het verzoek de regel te verwijderen. De gate blijft groen --
   documentatie verbeteren mag nooit een merge blokkeren.
4. Nieuwe IDs toevoegen aan deze lijst vereist een expliciet besluit van Rakesh, net als
   bij een `continue-on-error` op een CI-stap (zie `.claude/rules/quality-gates.md`).

## Openstaand

### SP-BE-ADR029 -- IDs vooruit geregistreerd, specs nog niet geschreven

**Toegevoegd:** 2026-07-31 (OP-11) | **Eigenaar:** sprint SP-BE-ADR029

Deze 25 IDs staan sinds 2026-07-27 in `ID-REGISTRY.md` met een spec-pad dat niet bestaat
(bijvoorbeeld `docs/backend/features/BE-EP-029-001-foundation-content-crud.md`). Het gaat
niet om achterstallige documentatie van afgerond werk, maar om **IDs die vooruit zijn
geregistreerd op werk dat nog moet gebeuren** -- zie het bijbehorende plan
`docs/agent-briefs/generated/2026-07-27-adr029-backend-implementatieplan.md`.

Ze zijn hier geplaatst en niet gecorrigeerd omdat ze toebehoren aan een andere,
parallelle sprint-iteratie; het herstructureren van hun registry-regels is aan die
sprint. De nette eindsituatie is dat deze regels uit `ID-REGISTRY.md` verdwijnen zolang de
specs niet bestaan (het register beschrijft opgeleverde features, niet geplande), of dat
de specs worden geschreven. Beslissing ligt bij Rakesh + de eigenaar van die sprint.

```text
BE-EP-023
BE-EP-024
BE-EP-025
BE-EP-026
BE-EP-027
BE-EP-028
BE-EP-029
BE-EP-030
BE-EP-031
BE-EP-032
BE-EP-033
BE-MDL-012
BE-MDL-013
BE-MDL-014
BE-MDL-015
BE-RTR-001
BE-SCH-032
BE-SCH-033
BE-SCH-034
BE-SEC-039
BE-SEC-040
BE-TSK-014
BE-UTL-047
```

### BE-AGT-045 -- review nog niet afgerond (ronde 6 uitstaand)

**Toegevoegd:** 2026-08-14 (ADR-036 OP-124-nazorg) | **Eigenaar:** Rakesh, met de eigenaar van
BE-AGT-045 | **GO:** Rakesh, 2026-08-14

`docs/backend/review/review-BE-AGT-045.md` bevat het woord `APPROVED` niet: de review staat op
"Ronde 1-5 alle CHANGES_REQUESTED, ronde 6 uitstaand". De validator meldt daarom `NOT APPROVED`
en de gate faalde op dit ene ID -- voor het HELE project, dus ook voor werk dat er niets mee te
maken heeft.

Bewust NIET opgelost door de status op `APPROVED` te zetten: dat zou een reviewrecord
falsificeren. De nette eindsituatie is dat ronde 6 van die review wordt afgerond; dan verdwijnt
deze regel hier automatisch met een `[PENDING-RESOLVED]`-melding.

```text
BE-AGT-045
```

## Opgelost (historie)

| Datum | ID | Wat er ontbrak | Hoe gesloten |
| --- | --- | --- | --- |
| 2026-09-08 | BE-SEC-048 | `## Trainingssamenvatting` + APPROVED-reviewbestand | `merge/golf1` gemerged (Cluster G) -- spec-kop eerst gecorrigeerd (zei "geen implementatie" terwijl commit `ded5b236` de implementatie al bevatte), daarna review geschreven |
| 2026-09-08 | BE-AGT-062 | registerregel wijst buiten `docs/backend/features/` | `merge/golf1` gemerged (Cluster G) -- validator kreeg een expliciete `[EXTERN]`-categorie die het genoemde pad wel controleert |
| 2026-07-31 | BE-AGT-035 | Trainingssamenvatting zonder `Actor:`-flow | flow uitgeschreven (Fase A dag 4) |
| 2026-07-31 | BE-FLW-048 | review-bestand ontbrak | pointer-review naar `review-BE-UTL-048.md` |
| 2026-07-31 | BE-FLW-049 | review-bestand ontbrak | pointer-review naar `review-BE-SEC-041.md` |
| 2026-07-31 | BE-FLW-050 | review-bestand ontbrak | pointer-review naar `review-BE-GDPR-003.md` |
| 2026-07-31 | BE-AGT-036 | Trainingssamenvatting zonder `Actor:`-flow | flow uitgeschreven (Fase A dag 5) |

**Terugkerende oorzaak, goed om te weten:** de validator voert de review-check uit op het
**alfabetisch eerste ID per gedeelde spec**. Een flow-ID als `BE-FLW-050` sorteert voor
zijn feature-ID `BE-GDPR-003`, waardoor de flow-ID de review-check krijgt in plaats van de
feature. Bij prefixen als AGT of API valt dat niet op, omdat die wel voor FLW sorteren.
Vandaar de pointer-reviews.
