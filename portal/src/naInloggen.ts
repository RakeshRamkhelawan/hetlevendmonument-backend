/**
 * Waar iemand na het klikken op de inloglink terechtkomt (BE-EP-056).
 *
 * De link in de e-mail wijst altijd naar /inloggen. Een pagina die zelf een
 * inloglink aanvraagt (zoals "Deel je verhaal"), legt hier vast waar de
 * gebruiker daarna weer heen moet. Alleen paden binnen deze site: geen open
 * redirect naar een ander domein.
 */
export const NA_INLOGGEN_SLEUTEL = 'hlm_na_inloggen';

const isEigenPad = (pad: string) => pad.startsWith('/') && !pad.startsWith('//') && !pad.includes('\\');

export const onthoudNaInloggen = (pad: string): void => {
  if (!isEigenPad(pad)) return;
  try {
    localStorage.setItem(NA_INLOGGEN_SLEUTEL, pad);
  } catch {
    // Opslag niet beschikbaar (privevenster): dan gewoon de standaardpagina.
  }
};

/** Leest het bewaarde pad en wist het meteen; null als er niets (geldigs) is. */
export const neemNaInloggen = (): string | null => {
  try {
    const pad = localStorage.getItem(NA_INLOGGEN_SLEUTEL);
    localStorage.removeItem(NA_INLOGGEN_SLEUTEL);
    return pad && isEigenPad(pad) ? pad : null;
  } catch {
    return null;
  }
};
