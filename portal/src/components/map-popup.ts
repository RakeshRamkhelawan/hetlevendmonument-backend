/**
 * Inhoud van de kaart-popup als DOM-boom in plaats van een HTML-string (FE-SEC-011).
 *
 * Titel en plaatsnaam komen van inzenders; met `setHTML` werd een titel als
 * `<img src=x onerror=...>` uitgevoerd in de browser van iedere bezoeker van de kaart
 * (stored XSS, markt-review 2026-09-24 blokkade 5). Hier gaat alle tekst via `textContent`,
 * en een afbeeldingsadres alleen mee als het met http(s) of een enkel `/` begint.
 */

export interface PopupGegevens {
  id: number | string;
  title: string;
  location_name?: string | null;
  file_url?: string | null;
}

// Een tweede `/` of een `\` na de eerste `/` maakt er voor de browser een adres op een
// ander domein van (`//x` en `/\x`); beide worden geweigerd.
const VEILIG_ADRES = /^(https?:\/\/|\/(?![\/\\]))/i;

export const isVeiligAfbeeldingsadres = (adres: string | null | undefined): adres is string =>
  typeof adres === 'string' && VEILIG_ADRES.test(adres.trim());

export const buildPopupContent = (gegevens: PopupGegevens): HTMLElement => {
  const wrapper = document.createElement('div');
  wrapper.className = 'p-1 max-w-[220px]';

  if (isVeiligAfbeeldingsadres(gegevens.file_url)) {
    const img = document.createElement('img');
    img.src = gegevens.file_url.trim();
    img.alt = gegevens.title;
    img.className = 'w-full h-24 object-cover rounded-lg mb-2';
    wrapper.appendChild(img);
  }

  const plaats = document.createElement('div');
  plaats.className = 'text-xs text-amber-800 font-semibold mb-0.5';
  plaats.textContent = gegevens.location_name || 'Nederland';
  wrapper.appendChild(plaats);

  const titel = document.createElement('h4');
  titel.className = 'font-serif font-bold text-sm text-stone-900 leading-tight mb-2';
  titel.textContent = gegevens.title;
  wrapper.appendChild(titel);

  const link = document.createElement('a');
  link.href = `/item/${encodeURIComponent(String(gegevens.id))}`;
  link.className = 'text-xs font-semibold text-amber-800 hover:underline';
  link.textContent = 'Bekijk verhaal →';
  wrapper.appendChild(link);

  return wrapper;
};
