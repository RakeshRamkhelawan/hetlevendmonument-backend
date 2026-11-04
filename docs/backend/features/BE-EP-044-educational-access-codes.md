# Backend Feature Specification

## Metadata

| Veld | Waarde |
|------|--------|
| Feature ID | BE-EP-044 |
| Naam | Foundation Educational Access Code Generator & Management Endpoints |
| Status | Completed |
| Auteur | AI-agent (senior architect-rol) |
| Reviewer | Red Team / Shadow CEO |
| Datum | 2026-09-12 |
| User story / ticket | ADR-029 P2-EDU: Echte Educatieve Toegangscode Generatie & Docentenportaal Koppeling |
| Router / module | `src/core/api/v1/foundation/edu.py`, `src/core/api/v1/foundation/schemas.py` |
| Frontend / Consumer endpoints | `POST /{tenantSlug}/foundation/edu/codes`, `GET /{tenantSlug}/foundation/edu/codes`, `DELETE /{tenantSlug}/foundation/edu/codes/{id}` |
| Database tabellen | `educational_access`, `study_collections`, `tenants` |
| Versie | 1.0.0 |

---

## Doel en scope

### Doel

Docenten en onderwijsinstellingen in staat stellen om cryptografisch veilige, 8-karakter toegangscodes te genereren voor schoolklassen en studiegroepen. Deze codes geven leerlingen tijdelijke toegang tot erfgoedcollecties en lesmodules via de educatieve portal zonder dat leerlingen persoonlijke accounts of wachtwoorden hoeven aan te maken (AVG-compliant voor minderjarigen).

### In scope

1. **Code Generatie (`generate_edu_code`)**:
   - `SAFE_EDU_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"` (32 karakters: verwijdert visueel ambigue tekens zoals 0, O, 1, I, L).
   - Generatie via `secrets.choice` voor cryptografische entropie (32^8 = 1.099.511.627.776 mogelijke combinaties).
   - Exact 8 hoofdletters conform `EduSessionRequest` schema-invariante regex `^[A-Za-z0-9]{8}$`.

2. **Endpoints (`src/core/api/v1/foundation/edu.py`)**:
   - `POST /{tenantSlug}/foundation/edu/codes`:
     - Accepteert `CreateEduCodeRequest(class_name, teacher_email, valid_hours, max_students, notes)`.
     - Berekent `expires_at` met `to_utc()`.
     - Slaat gehashte code op (`hash_edu_code(code)`) in `EducationalAccess.code_hash`.
     - Creëert gekoppelde `StudyCollection(name=class_name, tenant_id=tenant.id, educational_access_id=access.id)`.
     - Retourneert status 201 en eenmalig de onversleutelde code via `EduCodeCreateResponse`.
   - `GET /{tenantSlug}/foundation/edu/codes`:
     - Haalt alle actieve of historische toegangscodes op voor de tenant.
     - Lekt noch de ruwe code noch de hash (veilig model `EduCodeItem`).
   - `DELETE /{tenantSlug}/foundation/edu/codes/{id}`:
     - Markeert code als ingetrokken (`is_active = False`).
     - Retourneert status 204 No Content.

3. **Veiligheid & Scheiding**:
   - Geen persoonsgegevens van leerlingen opgeslagen; enkel het docenten e-mailadres voor notificaties.
   - SHA-256 hashopslag in de database.
   - Tenant-isolatie strikt gewaarborgd (`tenant_id == tenant.id`).

---

## Trainingssamenvatting

- **Component**: Foundation Educational Access Code Generator (`BE-EP-044`)
- **Doel**: Veilige klas-gebaseerde toegang tot erfgoedlesmateriaal zonder leerlingregistratie.
- **Architectuurregel**: Codes zijn exact 8 karakters, cryptografisch gegenereerd, enkel gehasht opgeslagen in PostgreSQL.
- **Geverifieerd met**: `tests/unit/test_foundation_edu_codes.py` (10 tests PASS), `portal/src/__tests__/TeacherPortalCodes.test.tsx` (4 tests PASS).
- **Actor**: Docent / Onderwijzer
  - **Flow**: Docent vult klasnaam en geldigheidsduur in op het docentenportaal -> Frontend roept `POST /{tenantSlug}/foundation/edu/codes` aan -> Backend genereert cryptografische 8-teken code, hasht deze met SHA-256 en slaat StudyCollection op -> Docent ontvangt eenmalig de deelbare toegangscode voor de klas.
