# Feature-spec: BE-EP-052 Foundation Media Streaming & Secure User-Delegation Read-SAS API

**ID:** `BE-EP-052`  
**Onderwerp:** Veilige Media Streaming, HTTP 206 Partial Content Range Requests en User-Delegation Read-SAS  
**Aanmaakdatum:** 2026-09-15  
**Status:** Geimplementeerd & Geverifieerd  
**Sprint / Context:** ADR-029 P1-4 Veilige Media Aflevering & Toegankelijkheid  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

In Het Levend Monument erfgoedplatform (ADR-029) worden diverse typen multimedia beheerd (audio-interviews, videobeelden, historische documenten en foto's). Voorheen bood het upload-endpoint enkel directe URL's of permanente links zonder adequate autorisatiecontroles of ondersteuning voor efficiënt media streamen.

Om te voldoen aan **ADR-029 P1-4**, **WCAG 2.1 AA (Tijdgebonden media)** en cloud native security best-practices:
1. **Azure User-Delegation Read-SAS (Entra ID):** Kortstondige (15-30 minuten), cryptografisch ondertekende SAS-tokens via Entra ID OAuth (`DefaultAzureCredential` met `get_user_delegation_key`) of fallback naar Account SAS (`account_key`). De opslagsleutels worden nooit blootgesteld aan de client en de database bewaart uitsluitend de canonieke blob URI.
2. **RFC 9110 HTTP Range Requests (Status 206 Partial Content):** Directe ondersteuning voor audio/video scrubbing (zoeken en vooruitspoelen in opnames) voor lokale storage en doorverwijzing naar Azure Blob Storage voor cloud caching.
3. **Strikte Autorisatie & Privacy Matrix:**
   - `APPROVED + PUBLIC`: Publiek toegankelijk.
   - `APPROVED + COMMUNITY`: Uitsluitend toegankelijk voor ingelogde bezoekers van de betreffende tenant (of beheerder/curator).
   - `APPROVED + EDU`: Uitsluitend toegankelijk met een actieve `edu_session` cookie (gevalideerd in Redis en Postgres) of door curatoren/beheerders.
   - `PENDING` / `REJECTED`: Uitsluitend toegankelijk voor de originele uploader of curator/admin; voor alle andere verzoekers retourneert het endpoint 404 (anti-enumeratie).
   - `REMOVED`: Uitsluitend toegankelijk voor curator/admin; voor uploader en publiek 404.
4. **Polyglot Security Hardening:**
   - `X-Content-Type-Options: nosniff` ter voorkoming van MIME-sniffing exploits.
   - `Content-Disposition: inline` voor streaming en `attachment; filename="sanitized"` voor beveiligde downloads.
   - `secure_filename` en strikte path-traversal preventie (`is_relative_to(local_upload_dir)`).

---

## 2. API Contract

### A. Media Metadata / Read URL: `GET /{tenantSlug}/foundation/content/{content_id}/media`
- **Query parameters:**
  - `redirect: bool = False`: Indien `true`, retourneert een HTTP 307 Temporary Redirect direct naar de beveiligde stream/SAS URL.
  - `download: bool = False`: Indien `true`, wordt `Content-Disposition: attachment` afgedwongen met gesaniteerde bestandsnaam.
  - `stream: bool = False`: Indien `true`, wordt lokale media direct gestreamd via chunked streaming i.p.v. metadata JSON.
- **Respons (200 OK bij `redirect=false` en `stream=false`):**
```json
{
  "url": "https://mystorage.blob.core.windows.net/foundation-content/2026/09/oral_history.mp3?skoid=...&sig=...",
  "mime_type": "audio/mpeg",
  "file_size_bytes": 10485760,
  "expires_in_seconds": 1800
}
```

### B. Directe Streaming Endpoint: `GET /{tenantSlug}/foundation/content/{content_id}/media/stream`
- **Headers:** `Range: bytes=start-end`, `bytes=start-`, of `bytes=-suffix`.
- **Query parameters:** `download: bool = False`.
- **Respons:**
  - Zonder Range: **200 OK** met headers `Accept-Ranges: bytes`, `Content-Length`, `Content-Type`, `X-Content-Type-Options: nosniff`.
  - Met geldige Range: **206 Partial Content** met header `Content-Range: bytes start-end/total_size`, `Content-Length: chunk_len`.
  - Met ongeldige Range: **416 Range Not Satisfiable** met header `Content-Range: bytes */total_size`.

---

## 3. Beveiliging, Compliance & Kwaliteit

- **Geen URL Lekken:** Privé en educatieve media kunnen niet via statische publieke webpaden worden uitgelezen.
- **Tijdelijke Geldigheid:** Read-SAS tokens verlopen automatisch na 30 minuten (instelbaar tot 15 minuten).
- **Anti-Enumeratie:** Niet-goedgekeurde items of verwijderde items retourneren `404 Not Found` in plaats van `403 Forbidden` om content-probing door kwaadwillenden te verhinderen.
- **WCAG 2.1 AA:** Scrubbing en partial content garanderen soepel afspelen in HTML5 `<audio>` en `<video>` elementen, ondersteund door schriftelijke transcripties.

---

## 4. Trainingssamenvatting

- **Actor**: Bezoeker / Leerling / Onderzoeker
  - **Flow**: De gebruiker opent een erfgoedverhaal op de detailpagina (`/verhaal/:id`). De frontend vraagt de mediabron aan via `/media/stream` of met een kortstondige Read-SAS URL. De gebruiker kan audio/video direct afspelen en door de opname navigeren (scrubbing) waarbij de browser HTTP 206 Range requests uitvoert. Via de download-knop kan het originele bronbestand veilig worden opgeslagen met een geschoonde bestandsnaam.
- **Actor**: Erfgoedbeheerder / Curator
  - **Flow**: De curator inspecteert ingezonden items in de curatiequeue of beoordeelt gemelde items. De curator heeft altijd toegang tot de bijbehorende media, zelfs wanneer de status `PENDING`, `REJECTED` of `REMOVED` is.
