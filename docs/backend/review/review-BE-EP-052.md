# Code Review: BE-EP-052 Foundation Media Streaming & Secure User-Delegation Read-SAS API

**Feature ID:** `BE-EP-052`  
**Onderwerp:** Veilige Media Streaming, HTTP 206 Partial Content Range Requests en User-Delegation Read-SAS  
**Reviewer:** Red Team / Shadow CEO  
**Datum:** 2026-09-15  
**STATUS: APPROVED**  

---

## 1. Doel & Beoordeling

Het doel van `BE-EP-052` is het leveren van een veilige, performante en robuuste media streaming- en download-infrastructuur conform ADR-029 P1-4, RFC 9110 (HTTP Range Requests voor audio/video scrubbing) en de strikte privacy- en zichtbaarheidsmatrix van Het Levend Monument erfgoedplatform.

### Pluspunten
- **RFC 9110 Range Header Volledigheid:** Ondersteunt gesloten bereiken (`bytes=0-499`), open bereiken (`bytes=500-`), suffix bereiken (`bytes=-500`) en retourneert status 206 Partial Content met `Content-Range` en `Accept-Ranges: bytes`.
- **Foutafhandeling (Status 416):** Onbevredigbare bereiken (`start >= size`, `start > end`, lege bestanden) retourneren keurig status 416 Range Not Satisfiable met header `Content-Range: bytes */size`.
- **Dual-strategy Azure SAS:** Maakt gebruik van Azure Entra ID OAuth (`DefaultAzureCredential`) voor kortstondige User-Delegation SAS-tokens, met naadloze terugval naar Account SAS (`account_key`) indien connection strings geconfigureerd zijn in dev/on-prem omgevingen.
- **Autorisatie & Anti-Enumeratie:** Privé-, educatieve-, pending-, rejected- en removed-content is hermetisch afgeschermd volgens de matrix. Niet-toegankelijke items retourneren `404 Not Found` in plaats van 403 om doelgerichte content-probing en enumeratie door aanvallers te voorkomen.
- **Polyglot & Traversal Hardening:** `X-Content-Type-Options: nosniff`, `Content-Disposition: inline|attachment`, `secure_filename` en `is_relative_to(local_upload_dir)` sluiten path traversal en MIME-type sniffing aanvallen structureel uit.
- **Frontend & WCAG 2.1:** Detailpagina (`ContentDetail.tsx`) gebruikt de beveiligde stream URL voor `<audio>` en `<video>` tags en biedt een directe, veilige downloadlink.

---

## 2. Devil's Advocate (Red Team Mandaat)

### Risico's & Beheersing
1. **Bandbreedte Uitputting / DDoS via Range Loops:** Kwaadwillenden zouden massaal kleine ranges kunnen opvragen om I/O-uitputting te veroorzaken.  
   *Beheersing:* Endpoint is beschermd door de `portal_media_read_limit` Redis token-bucket rate limiter. Bovendien worden chunks asynchroon via `aiofiles` en `StreamingResponse` gestreamd zonder het bestand volledig in het geheugen te laden.
2. **Path Traversal via Gemanipuleerde file_url:** Een opgeslagen URL zoals `../../etc/passwd` zou theorethisch willekeurige systeembestanden kunnen streamen.  
   *Beheersing:* `FoundationStorageService.get_local_file_path` controleert via `Path.resolve().is_relative_to(root)` of het bestand zich binnen de geautoriseerde upload-map bevindt; zo niet, retourneert de functie `None` en resulteert dit in een veilige 404.
3. **Sessiekaping bij Educatieve Content:** Delen van de `edu_session` cookie tussen browsers.  
   *Beheersing:* Sessies hebben een strikte TTL in Redis en worden bij ieder verzoek getoetst aan de geldigheid van de activatiecode in de PostgreSQL database.

**Oordeel:** GO (STATUS: APPROVED).
