import { describe, expect, it } from 'vitest';

import { buildPopupContent, isVeiligAfbeeldingsadres } from '../components/map-popup';

describe('kaart-popup (FE-SEC-011)', () => {
  it('voert een titel met HTML niet uit maar toont hem als tekst', () => {
    const el = buildPopupContent({ id: 1, title: '<img src=x onerror="alert(1)">' });

    expect(el.querySelector('img[onerror]')).toBeNull();
  });

  it('toont de titel letterlijk', () => {
    const el = buildPopupContent({ id: 1, title: '<b>vet</b>' });

    expect(el.querySelector('h4')?.textContent).toBe('<b>vet</b>');
  });

  it('voert een plaatsnaam met HTML niet uit', () => {
    const el = buildPopupContent({ id: 1, title: 't', location_name: '<script>alert(1)</script>' });

    expect(el.querySelector('script')).toBeNull();
  });

  it('weigert een javascript-adres als afbeelding', () => {
    expect(isVeiligAfbeeldingsadres('javascript:alert(1)')).toBe(false);
  });

  it('weigert een adres zonder schema dat naar een ander domein wijst', () => {
    expect(isVeiligAfbeeldingsadres('//kwaad.example/x.png')).toBe(false);
  });

  it('weigert een adres met een backslash dat naar een ander domein wijst', () => {
    expect(isVeiligAfbeeldingsadres('/\\kwaad.example/x.png')).toBe(false);
  });

  it('accepteert een https-adres', () => {
    expect(isVeiligAfbeeldingsadres('https://opslag.example/x.jpg')).toBe(true);
  });

  it('accepteert een pad op dezelfde site', () => {
    expect(isVeiligAfbeeldingsadres('/uploads/foundation/1/2/a.jpg')).toBe(true);
  });

  it('laat geen afbeelding zien bij een onveilig adres', () => {
    const el = buildPopupContent({ id: 1, title: 't', file_url: 'javascript:alert(1)' });

    expect(el.querySelector('img')).toBeNull();
  });

  it('codeert het id in de link', () => {
    const el = buildPopupContent({ id: '1"><x', title: 't' });

    expect(el.querySelector('a')?.getAttribute('href')).toBe('/item/1%22%3E%3Cx');
  });
});
