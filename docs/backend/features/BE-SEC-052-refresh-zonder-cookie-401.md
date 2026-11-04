# BE-SEC-052: refresh zonder refresh-token geeft 401 in plaats van 422

**Status:** APPROVED
**Datum:** 2026-10-05
**Tak:** `fix/auth-race-e2e` (basis `5ea09d34`)

## Probleem (gemeten)

`curl -X POST http://localhost:8110/api/v1/auth/refresh -d '{"grant_type":"refresh_token"}'`
gaf `422 {"loc":["body","refresh_token"],"msg":"Field required"}`. De browser stuurt het
refresh-token als httpOnly-cookie en laat het body-veld weg. `RefreshTokenRequest.refresh_token`
was verplicht, dus FastAPI weigerde voordat de cookie-terugval in `router_token.refresh_token`
kon draaien.

## Oplossing

`src/core/api/auth/schemas.py`: `refresh_token: str | None = None`. De route doet al
`data.refresh_token or request.cookies.get("refresh_token")` en geeft 401 "Refresh token required"
als beide ontbreken. Rate limit (`10/minute`) en de controle op het tokensoort blijven ongewijzigd.

## Endpoint

- `POST /api/v1/auth/refresh` -- 200 met nieuw token; 401 zonder of met ongeldig refresh-token.

## Tests

- `tests/unit/api/auth/test_refresh_without_cookie_is_401.py` -- rood op `5ea09d34` (422 Field
  required), groen na de wijziging.

## Trainingssamenvatting

- Actor: Browser van een ingelogde of uitgelogde gebruiker
- Voorwaarde: de app vraagt een nieuwe sessie aan zonder refresh-token in de body.
- Actie: `POST /api/v1/auth/refresh` met alleen `grant_type`.
- Systeemreactie: de backend leest het refresh-cookie.
- Succesrespons: 200 met nieuw access-token als het cookie geldig is.
- Foutrespons: 401 "Refresh token required" als er geen cookie is.
- Uitzonderingen: geen.
