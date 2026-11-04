# Feature-spec: BE-EP-056 Verhaal insturen met foto of geluid (ADR-029)

**ID:** `BE-EP-056`
**Onderwerp:** Aanmelden via de inloglink, bestanden kiezen vanaf het eigen apparaat, plek op de kaart, locatiegegevens uit foto's
**Aanmaakdatum:** 2026-11-03
**Status:** Gebouwd met unit-, mutatie- en componenttests; uitrol na akkoord en een test op een telefoon
**Sprint / Context:** Demo subsidiegever november 2026; ADR-029 eis 4 ("lage drempel voor uploaders, magic-link")

---

## 1. Doel & Context

Tot 2026-11-03 kon een verteller op *Deel je verhaal* geen foto of geluid van het eigen apparaat
kiezen, alleen een link plakken. De plek moest als breedte- en lengtegraad worden ingetypt. Het
e-mailveld "voor statusupdates" werd nergens opgeslagen. De upload-API (BE-EP-036) bestond wel, maar
vraagt een ingelogde eigenaar, en een nieuwe verteller kon geen account krijgen: de inloglink werkte
alleen voor bestaande gebruikers.

Deze feature maakt het insturen bruikbaar voor gewone vertellers:

1. *Deel je verhaal* begint met het e-mailadres. De verteller krijgt een inloglink; een onbekend adres
   krijgt daarbij een bezoekersaccount. Na de klik komt de verteller terug op het formulier.
2. Een knop *Foto, geluid of document kiezen* en een knop *Foto maken* (camera op de telefoon).
3. Een kaartje waarop de verteller de plek aanwijst. Coordinaten verdwijnen uit beeld.
4. Foto's, video's en opnames worden opgeslagen zonder locatie en andere persoonlijke metadata.
   Spraakopnames (.m4a) zijn toegestaan.
5. Accounts waarvan de inloglink nooit is gebruikt, worden na 7 dagen opgeruimd.

## 2. Beveiliging en privacy

- **Account aanmaken** (`POST /{tenantSlug}/foundation/auth/magic-link` met `aanmelden: true`):
  - alleen voor een ONBEKEND adres; een bestaand account houdt zijn rol;
  - altijd met de laagste rol `visitor`, `is_verified=false`, in de tenant van de aanvraag;
  - alleen voor een adres dat op een e-mailadres lijkt;
  - hCaptcha en de bestaande rate limits (5 per IP per minuut, 3 per adres per uur) gelden;
  - het antwoord is altijd hetzelfde, zodat niet te zien is of een adres al bestond;
  - pas na het gebruiken van de link is het account geverifieerd (`is_verified`, `email_verified`);
  - e-mailadressen worden in kleine letters vergeleken en opgeslagen; een gelijktijdige tweede
    aanvraag voor hetzelfde adres valt terug op het account dat er dan al is (savepoint).
- **Metadata uit foto's** (`foundation_storage.verwijder_metadata`, aangeroepen in het upload-endpoint
  voordat er iets wordt opgeslagen): JPEG, PNG en WebP worden opnieuw opgeslagen zonder EXIF en
  tekstblokken; de stand (EXIF Orientation) wordt eerst in de pixels verwerkt; het kleurprofiel blijft.
  Afbeeldingen boven 50 miljoen pixels of die niet te lezen zijn, worden geweigerd (400).
- **Metadata uit MP4** (video en .m4a): de blokken `udta` en `meta` in `moov` en `trak` (locatie,
  titel, toestel, maker; een iPhone-opname krijgt standaard de straatnaam als titel) krijgen het
  type `free` en worden met nullen gevuld. Elk blok houdt zijn lengte, dus de verwijzingen naar
  beeld en geluid blijven kloppen en de bytes van beeld en geluid veranderen niet. Een MP4 met een
  ongeldige blokindeling wordt geweigerd (400). GIF, MP3, WAV, OGG, WebM en PDF komen ongewijzigd door.
- **Ongebruikte accounts** (`foundation_accounts.verwijder_ongebruikte_accounts`, in de nachtelijke
  job `levendmonument-opschonen`): alleen rol `visitor`, niet geverifieerd, nooit ingelogd, ouder
  dan 7 dagen, en nergens naar verwezen (verhaal, klas, archiefexport, docentaanvraag; die
  verwijzingen staan op `ON DELETE SET NULL`). Inloglinks verdwijnen mee (`CASCADE`).
- **Terug na inloggen**: het portaal bewaart het pad (`hlm_na_inloggen`) en accepteert alleen paden
  binnen de eigen site (geen `//`, geen schema, geen backslash).

## 3. Onderdelen

| Onderdeel | Bestand |
|---|---|
| Aanmelden via inloglink | `src/core/api/v1/foundation/auth.py` (`request_magic_link`, `verify_magic_link`), `schemas.py` (`MagicLinkRequest.aanmelden`) |
| Metadata uit foto's, video's en opnames; m4a | `src/core/services/foundation_storage.py` (`verwijder_metadata`, `_wis_mp4_metadata`, `ALLOWED_MIME_TYPES`), `src/core/api/v1/foundation/upload.py` |
| Ongebruikte accounts | `src/core/services/foundation_accounts.py`, aangeroepen in `foundation_leerlingantwoorden._main` (nachtelijke job; draait op het `lm-api`-image) |
| Formulier | `portal/src/pages/SubmitStory.tsx`, `portal/src/components/BestandKiezer.tsx`, `portal/src/components/PlekKiezer.tsx` |
| Terug na inloggen | `portal/src/naInloggen.ts`, `portal/src/pages/Login.tsx` (verteller gaat standaard naar Mijn Inzendingen) |
| API-client | `portal/src/api/client.ts` (`requestMagicLink(..., { aanmelden })`) |

Pillow (al aanwezig via fpdf2, `requirements-prod.lock`) doet het beeldwerk; er is geen nieuwe
afhankelijkheid.

## 4. Tests

| Test | Bewaakt |
|---|---|
| `tests/unit/api/v1/foundation/test_aanmelden_via_inloglink.py` | regels uit par. 2 voor het aanmaken van een account (6 tests, 12 gevallen) |
| `tests/unit/test_be_ep_056_foto_zonder_locatie.py` | GPS en tekst weg uit JPEG/PNG/WebP, stand blijft goed; locatie en titel weg uit MP4 en .m4a met gelijke indeling, ook bij 64-bits blokken; andere typen ongewijzigd; weigeren van kapotte en te grote bestanden; m4a toegestaan; het endpoint slaat de opgeschoonde bytes op |
| `tests/unit/test_be_ep_056_accounts_opschonen.py` | de opruimregels uit par. 2 (rol, nooit gebruikt, 7 dagen, geen verwijzingen, gecorreleerde subquery, tenant) en dat de nachtelijke job ze aanroept |
| `portal/src/__tests__/VerhaalInsturen.test.tsx` | stap 1 met aanmelden, upload na het opslaan van het verhaal, opnieuw proberen, terug naar stap 1 bij verlopen inlog, bestandscontrole, geen open redirect, axe |

**Mutatiebewijs** (2026-11-03): elke regel is weggehaald en de bijbehorende test werd rood:
rol `visitor` vervangen door `curator`; bestaand account overschrijven; geen e-mailcontrole;
`aanmelden` negeren; niet verifieren na de link; endpoint slaat het origineel op; stand niet
verwerken; geen pixelgrens; m4a niet toegestaan; metadata niet weghalen. 10 van 10 rood.
Tweede ronde (MP4 en accounts): niet in `trak` kijken; alleen hernoemen zonder wissen; MP4 niet
opschonen; rol, verificatie, termijn, verhalen of docentaanvraag niet controleren; job roept het
opruimen niet aan. 9 van 9 rood.

## 5. Bekende beperkingen

- QuickTime-video's (.mov) en XMP-blokken (`uuid`): opgelost in BE-EP-057.
- Een verhaal heeft een bestand: opgelost in BE-EP-057 (tot 10 bestanden).
- HEIC-foto's van een computer worden in het portaal geweigerd met uitleg; een iPhone zet ze bij het
  kiezen zelf om naar JPEG.
- Het aanmaken van content zonder inloggen blijft in de API mogelijk (andere clients); het portaal
  gebruikt die route niet meer voor vertellers.
