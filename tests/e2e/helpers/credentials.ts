/**
 * De enige bron van e2e-inloggegevens voor de suite onder tests/e2e.
 *
 * Volgorde: E2E_ADMIN_* (expliciet voor de testronde), dan DEFAULT_ADMIN_* (dezelfde variabelen
 * waarmee src/core/database/seed.py de beheerder aanmaakt), dan de waarde van de dev-seed. Die
 * laatste is geen productiegeheim: het is het wachtwoord van de lokale ontwikkel- en testdatabase
 * (zie ook frontend/tests/e2e/global-setup.ts en tests/integration/conftest.py).
 *
 * Gemeten 2026-10-05 (nazorgtoets scenario 5): helpers/auth.ts gebruikte `Admin@123` en de
 * HITL-spec `test@example.com`; geen van beide kon inloggen op de draaiende stack.
 */

export interface UserCredentials {
  email: string;
  password: string;
}

const DEV_SEED_ADMIN: UserCredentials = {
  email: 'admin@sanskritisetu.org',
  password: 'AdminPass123!',
};

export const E2E_ADMIN: UserCredentials = {
  email: process.env.E2E_ADMIN_EMAIL || process.env.DEFAULT_ADMIN_EMAIL || DEV_SEED_ADMIN.email,
  password: process.env.E2E_ADMIN_PASSWORD || process.env.DEFAULT_ADMIN_PASSWORD || DEV_SEED_ADMIN.password,
};

/**
 * Een gewone gebruiker ZONDER beheerdersrol (rol `user`), om rolgrenzen mee te testen:
 * `/audit-logs` en `/api/v1/system/*` weigeren hem (403). Wordt aangemaakt door
 * `python scripts/seed_tweede_gebruiker.py` (lokaal; weigert in production en staging), met
 * dezelfde dev-standaard. Geen productiegeheim: het wachtwoord van de lokale ontwikkeldatabase.
 */
const DEV_SEED_MEDEWERKER: UserCredentials = {
  email: 'medewerker@sanskritisetu.org',
  password: 'MedewerkerPass123!',
};

export const E2E_MEDEWERKER: UserCredentials = {
  email: process.env.E2E_MEDEWERKER_EMAIL || DEV_SEED_MEDEWERKER.email,
  password: process.env.E2E_MEDEWERKER_PASSWORD || DEV_SEED_MEDEWERKER.password,
};

/**
 * Een gebruiker met alleen de rol `goedkeurder` (`receivables:approve`), voor tests die een
 * HITL-ticket goedkeuren of afwijzen. Goedkeuren is sinds 2026-10-09 een procesbevoegdheid
 * (ADR-039): de beheerder heeft dat recht NIET meer vanzelf. Aanmaken met
 * `python scripts/seed_tweede_gebruiker.py --rol goedkeurder` (lokaal; weigert in production en
 * staging); het wachtwoord is dat van `E2E_MEDEWERKER_PASSWORD` met dezelfde dev-standaard.
 */
export const E2E_GOEDKEURDER: UserCredentials = {
  email: process.env.E2E_GOEDKEURDER_EMAIL || 'goedkeurder@sanskritisetu.org',
  password: process.env.E2E_MEDEWERKER_PASSWORD || DEV_SEED_MEDEWERKER.password,
};
