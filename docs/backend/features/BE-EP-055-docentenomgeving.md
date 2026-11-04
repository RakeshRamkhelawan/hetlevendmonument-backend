# Feature-spec: BE-EP-055 Docentenomgeving (ADR-029)

**ID:** `BE-EP-055`
**Onderwerp:** Docentaccounts met goedkeuring, klassen met klascodes, lessen per klas, leerlingantwoorden met feedback, printbare PDF's
**Aanmaakdatum:** 2026-11-03
**Status:** Gebouwd met unit- en componenttests; end-to-end getest op productie na uitrol (zie par. 9)
**Sprint / Context:** Demo subsidiegever november 2026; volgt op het lesmateriaal "Vijf verhalen over vrijheid" (commit 2f51acd06)

---

## 1. Doel & Context

Tot 2026-11-03 kon alleen een curator of beheerder klascodes maken (BE-EP-044, BE-SEC-057) en zag
elke klas al het lesmateriaal. Leerlingen konden niets terugsturen. Deze feature geeft scholen een
eigen omgeving:

- een docent vraagt een account aan; de stichting keurt goed of af;
- een docent maakt klassen, elk met een eigen klascode, en kiest per klas welke werkbladen open staan;
- leerlingen vullen antwoorden in bij een werkblad; de docent leest ze en geeft feedback;
- de docent downloadt handleidingen en werkbladen als PDF.

## 2. Privacy (minderjarigen)

- Een leerling geeft alleen een voornaam of bijnaam op (max. 40 tekens, geen `@`). Geen e-mail,
  geen account.
- De browser bewaart een willekeurig token (`localStorage`, `hlm_leerling_token`); de database
  alleen de SHA-256 ervan. Daarmee ziet de leerling de eigen antwoorden terug.
- Antwoorden worden 8 weken na het eerste opslaan verwijderd: de API ruimt bij elk lezen en schrijven
  de verlopen rijen van de eigen tenant op, en de dagelijkse job `levendmonument-opschonen`
  (`python3 -m src.core.services.foundation_leerlingantwoorden`, eigenaar-verbinding) verwijdert ze
  voor alle tenants.
- Alleen een code met de rol leerling kan antwoorden opslaan.
- Een docent ziet alleen antwoorden uit EIGEN klassen.

## 3. Onderdelen

| Onderdeel | Bestand |
|---|---|
| Modellen | `src/core/models/foundation_content.py`: `FoundationTeacherApplication`, `FoundationClassLesson`, `FoundationStudentAnswer`; `StudyCollection.owner_portal_user_id` en `target_age_group` |
| Migratie | `src/alembic/versions/20261103_adr029_docentenomgeving.py` (puur toevoegend, RLS op de drie nieuwe tabellen) |
| API | `src/core/api/v1/foundation/docent.py` |
| Lessen per klas | `src/core/services/foundation_klas.py`, gebruikt door `edu.py` (`/edu/content` en `/edu/content/{id}`) |
| Antwoorden + bewaartermijn | `src/core/services/foundation_leerlingantwoorden.py` |
| PDF | `src/core/services/foundation_lespdf.py` (fpdf2, Helvetica) |
| Vragen per werkblad | `scripts/seed/bouw_lesmateriaal.py` zet `metadata.vragen` (`sleutel`, `sectie`, `tekst`) |
| Portaal | `TeacherPortal.tsx`, `AntwoordFormulier.tsx`, `DocentenBeheerPanel.tsx` (tab "Docenten"), `ContentDetail.tsx` |
| Infra | job `levendmonument-opschonen` in `infra/main-levendmonument-prod.bicep` |

## 4. API-contract (prefix `/api/v1/{tenantSlug}/foundation`)

Openbaar: `POST /docent/aanvraag` (hCaptcha, `portal_public_write_limit`). Altijd 202 met dezelfde
tekst; een tweede open aanvraag met hetzelfde adres wordt niet bewaard. Mail naar de aanvrager en
naar het contactadres van het portaal.

Ingelogd: `GET /docent/ik` (rol + status van de laatste aanvraag).

Docent (`require_docent`: teacher, curator of admin; tenant-match 403):

- `GET /docent/lesmateriaal`, `GET /docent/lesmateriaal/{id}`, `GET /docent/lesmateriaal/{id}/pdf`
- `GET|POST /docent/klassen`; de POST geeft de klascode EENMALIG terug. Zonder `les_ids` staan alle
  werkbladen van het niveau open.
- `POST /docent/klassen/{id}/nieuwe-code`, `POST /docent/klassen/{id}/intrekken`
- `PUT /docent/klassen/{id}/lessen` (alleen goedgekeurde EDU-werkbladen van de tenant, anders 422)
- `GET /docent/klassen/{id}/antwoorden`, `PUT /docent/antwoorden/{id}/feedback`

Een klas of antwoord van een andere docent geeft 404.

Leerling (`require_edu_session`): `GET|PUT /edu/antwoorden/{content_id}` met header
`X-Leerling-Token`. Alleen vragen uit `metadata.vragen`, max. 2000 tekens per antwoord, max. 200
inzendingen per klas per werkblad.

Beheerder (`require_admin`): `GET /admin/docenten/aanvragen`, `POST .../{id}/goedkeuren`,
`POST .../{id}/afwijzen`, `GET /admin/docenten`, `POST /admin/docenten/{id}/intrekken`.
Goedkeuren verlaagt nooit een curator- of beheerdersrol en stuurt een eenmalige inloglink (48 uur).
Intrekken zet de rol terug naar bezoeker en zet alle klascodes van die docent uit.

## 5. Lessen per klas

Een klas MET eigenaar (docent) ziet alleen de opengezette lessen, ook als dat er nul zijn. Een
klascode ZONDER eigenaar (oude vorm, BE-EP-044) ziet al het lesmateriaal, zoals voorheen.

## 6. Tests

- `tests/unit/test_foundation_docent.py`: rollen, tenant-match, eigenaarsfilter, lessen per klas
  (oude code ziet alles, lege selectie ziet niets), leerlingrol, naam- en antwoordcontrole, token
  als hash, bewaartermijn van 8 weken, goedkeuren verlaagt geen hogere rol.
- Portaal: `TeacherPortal.test.tsx`, `AntwoordFormulier.test.tsx`, `DocentenBeheerPanel.test.tsx`,
  `ContentDetailEdu.test.tsx`.

## 7. Niet in scope

Zelf registreren zonder goedkeuring, koppeling met een schoolsysteem (SSO, Entree), cijfers geven,
meerdere docenten per klas.

## 8. Open aannames

- Het contactadres van het portaal (`FoundationPortalSettings.contact_email`) ontvangt de meldingen
  van nieuwe aanvragen.
- Een docent die ook curator of beheerder is, houdt die hogere rol.

## 9. Gemeten

Zie de overdracht van 2026-11-03 (`docs/infra/OVERDRACHT-2026-11-02.md`, aanvulling) voor de
end-to-end test op productie.
