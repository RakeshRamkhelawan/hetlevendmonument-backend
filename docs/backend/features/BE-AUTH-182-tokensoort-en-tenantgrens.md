# Backend Feature Specification

## Metadata

- Feature ID: BE-AUTH-182
- Feature naam: Tokensoort stempelen en controleren (OP-182) + tenantgrens bij rolwijzigingen (OP-183)
- Status: Geimplementeerd, Gate 3 groen, poortselectie groen
- Auteur: senior developer (sessie sanskritisetu-org-58)
- Reviewer: Gate 2 -- code-reviewer en quality-reviewer op het PLAN (twee rondes, beide NO-GO, beide verwerkt)
- Datum: 2026-09-12
- Gerelateerde user story / ticket: ADR-036 OP-182, OP-183 (P0-autorisatiecluster, Dag 2)
- Gerelateerde router / module: `src/core/auth/jwt_handler.py`, `src/core/auth/token_kind.py`,
  `src/core/auth/oauth2_service.py`, `src/core/security/security_manager.py`,
  `src/core/services/rbac_service.py`
- Gerelateerde frontend endpoints: geen. GEMETEN: de frontend leest geen type-claim (vier
  parsers, alle zonder verificatie; beide `JWTPayload`-interfaces hebben geen `type`- of
  `token_type`-veld; alle 41 `token_type`-treffers zijn het OAuth2-responseveld).
- Gerelateerde database tabellen: `user_roles`, `roles`, `users` (alleen gelezen; geen migratie)
- Versie: 1.0

---

## Doel en scope

### Doel

Twee gaten in de autorisatie die beide zonder escalatie te misbruiken waren.

**OP-182.** Niets controleerde het SOORT token. Een refresh-token -- levensduur zeven dagen,
en bij uitloggen niet ingetrokken -- was bruikbaar als access-token op elk endpoint. En elk
refresh-token zette de gebruiker in tenant 1, ongeacht bij welke organisatie hij hoorde.

**OP-183.** Rollen toekennen of intrekken kon over de tenantgrens heen: de gebruiker-id kwam
ongevalideerd uit de request body, terwijl de tenant uit de middlewarecontext kwam, en niets
vergeleek die twee.

### In scope

- Het soort token stempelen in de JOSE-header `typ` bij uitgifte, en controleren na een
  geslaagde decode.
- De hardgecodeerde `tenant_id: int = 1` op het refresh-pad.
- De tweede verifier (`security_manager`), die soort-blind was op dezelfde sleutel.
- De tenantvergelijking bij het toekennen en intrekken van rollen, in de service.
- Een architectuurtest die voorkomt dat de stempel een conventie wordt.

### Out of scope

- **Sleutelscheiding per tokensoort.** RFC 8725 par. 3.12 noemt aparte sleutels en aparte
  `aud` als alternatieven. Beide zijn op termijn beter -- bij sleutelscheiding faalt een
  refresh-token op een access-verifier op de HANDTEKENING, in elke bibliotheek, ook in code
  die niemand reviewt. Ze vragen sleutelbeheer en rotatie die dit project niet heeft en
  horen in een eigen ADR. Dit is de voornaamste beperking van deze oplossing en staat ook
  in de registerrij.
- **Token-intrekking op het verzoekpad** (OP-188, Dag 4).
- **`tenant_id` met constraint op `user_roles`** (OP-190): migratie, dus interlock.
- **Frontend-rolvocabulaire** (OP-193, Dag 5).

---

## Build summary

- **Nieuw gebouwd:** `src/core/auth/token_kind.py` (het soort-primitief met de aanvaarde
  headerwaarden op EEN plek); `JWTHandler.create_refresh_token`; `JWTHandler._encode` als
  enige ondertekenplek in die klasse; `RBACService._doelgebruiker_in_tenant`;
  `tests/unit/auth/test_het_tokensoort_wordt_gestempeld_en_gecontroleerd.py` (20 toetsen);
  `tests/unit/rbac/test_de_tenantgrens_in_rolwijzigingen.py` (6 toetsen);
  `tests/architecture/test_jwt_ondertekenen_blijft_bij_de_fabriek.py` (4 toetsen).
- **Gewijzigd:** `create_access_token` stempelt `at+jwt`; `verify_token` kreeg
  `expected_kind` keyword-only met default ACCESS en controleert de header;
  `create_token_pair` gebruikt de refresh-fabriek; `oauth2_service._create_refresh_token`
  verloor zijn tenant-default en gebruikt de refresh-fabriek;
  `oauth2_service.refresh_access_token` verwacht expliciet REFRESH;
  `security_manager.generate_token` stempelt mee en `verify_token` controleert;
  `rbac_service.assign_role` en `revoke_role` vergelijken de tenant.
- **Verwijderd:** de body-claim `token_type` als SCHRIJFgedrag (gemeten: 1 schrijver, 0
  lezers) en de body-claim-controle `type` op het refresh-pad (vervangen door de header).
- **Beinvloede bestaande flows:** inloggen, tokenvernieuwing, en elk verzoek dat door
  `verify_token` gaat (25 aanroepplekken). Zes bestaande toetsen zijn bijgewerkt; drie
  daarvan pinden het defecte gedrag vast (`_create_refresh_token(1)` zonder tenant, en de
  body-claim `type`), twee crashten op een eigen fout van mij (zie hieronder) en een muntte
  zelf een token buiten de fabriek om.

---

## Ontwerpbesluiten, met de reden

1. **De header `typ`, niet een body-claim.** RFC 8725 par. 3.11 beveelt expliciete typering
   aan; RFC 9068 par. 2.1 maakt `at+jwt` dwingend voor access tokens en par. 4 eist dat de
   resource server de waarde controleert en elke andere weigert. De header valt onder de
   handtekening. `refresh+jwt` is een PRIVATE waarde: RFC 9068 zegt niets over refresh
   tokens, en dat staat ook zo in de code.
2. **Beide spellingen aanvaarden.** RFC 9068 par. 4 schrijft letterlijk `at+jwt` OF
   `application/at+jwt` voor. Een strikte vergelijking met alleen de korte vorm zou een
   MOET-aanvaarde waarde weigeren.
3. **Twee fabrieken, geen soort-parameter.** Een parameter met een default is de bypass:
   vergeet een aanroeper hem, dan krijgt een refresh-token de access-stempel. Een tweede
   functienaam kun je niet vergeten. Een toets pint vast dat de fabriek geen soort-parameter
   heeft.
4. **`expected_kind` keyword-only, default ACCESS.** Vergeet een aanroeper op het
   refresh-pad hem, dan wordt een refresh-token daar GEWEIGERD -- luid en in de veilige
   richting. Een toets pint die default vast zodat niemand er later een doorlaat-waarde van
   maakt.
5. **Geen overgangsvenster.** Een ontbrekende `typ` wordt geweigerd. Grond, van de eigenaar:
   er is geen productiedata en er zijn geen klanten, alleen zelf aangemaakte testgebruikers.
   De kosten van de harde knip zijn dus een keer opnieuw inloggen. Een terugval die een
   `typ`-loos token accepteert, laat het gat juist open.
6. **De guard in de SERVICE, niet in de router** (OP-183). ADR-033 wijst een handler die
   zelf query't af, en gemeten lopen alle zeven aanroepers door de service -- inclusief de
   bulk-endpoints. Een routercheck zou een van de drie aanroepers dekken.

---

## Wat NIET is opgelost en bij de sluiting hoort

- **Er is nog EEN sleutel voor twee tokensoorten** (gemeten:
  `jwt_handler.secret_key == security_manager.secret_key`). De bescherming is een CONTROLE
  die een nieuwe verifier kan vergeten, afgedekt door de architectuurtest en niet door de
  wiskunde. Dit is de kern van het Devil's Advocate-argument van de reviewer en het is
  terecht.
- **`user_roles` heeft nog geen `tenant_id` met constraint.** De bescherming van OP-183 is
  een `if` in een servicemethode boven een tabel die cross-tenant rijen fysiek toestaat.
  OP-190, met migratie en interlock.
- **Een tweede, in productie onbereikbaar schrijfpad blijft staan:**
  `user_management/crud_router.py:490-532` zet binnen `TenantFilterBypass` de tenantfilter
  uit, wist alle rollen van een gebruiker en zoekt de rol in de tenant van het DOELWIT.
  Gemeten onbereikbaar via `src.main` (de productieconstructie), maar een geladen wapen.

---

## Verificatie

- **Mutatiebewijs in BEIDE richtingen, vijf onafhankelijke mutaties**, tegen de ECHTE
  fabriek en verifier zonder mocks: soortcontrole verwijderd -> 4 rood; ontbrekende `typ`
  doorgelaten -> 1 rood; refresh-fabriek stempelt ACCESS -> 3 rood; alleen de korte
  spelling aanvaard -> 1 rood; nieuwe ondertekenplek toegevoegd -> de architectuurtest
  rood. Ongemuteerd groen, na herstel opnieuw groen.
- **OP-183 apart mutatiegetest** tegen een echte sqlite-sessie: guard weg -> precies de vier
  weigerende toetsen rood, de twee legitieme blijven groen.
- **Gate 3:** `ruff check src/ tests/` schoon; `run_mypy_audit.py --fail-on-increase` 0
  fouten, geen toename; `pyright` 0 errors, 0 warnings op het gewijzigde oppervlak.
- **Any-ratel** onveranderd op 7111.
- **Register:** OP-183 en OP-182 gesloten met `GEVERIFIEERD=` en `BEWIJS=`; non-ASCII-telling
  van het register onveranderd op 447; de 18 ADR-036-registerguards groen.

---

## Eigen fout tijdens de bouw, genoteerd

De teller per weigergrond stond eerst in `__init__`. Drie bestaande toetsen bouwen een
handler met `JWTHandler.__new__` en slaan `__init__` dus over; die kregen een
`AttributeError` in plaats van een nette weigering. Een guard die crasht op een object dat
zo is gebouwd, is een guard die je niet kunt vertrouwen. Gerepareerd: de teller wordt lui
aangemaakt in de telfunctie zelf.
