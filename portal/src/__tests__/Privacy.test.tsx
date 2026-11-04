import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';

import { Privacy } from '../pages/Privacy';

const toon = () =>
  render(
    <MemoryRouter>
      <Privacy />
    </MemoryRouter>,
  );

describe('Privacyverklaring', () => {
  it('heeft een kop', () => {
    toon();

    expect(screen.getByRole('heading', { level: 1, name: 'Privacyverklaring' })).toBeTruthy();
  });

  it('verwijst naar de eigen inzendingen', () => {
    toon();

    expect(screen.getByRole('link', { name: 'Mijn inzendingen' }).getAttribute('href')).toBe('/mijn-inzendingen');
  });

  it('verwijst niet naar de open-datapagina als eigen gegevens', () => {
    const { container } = toon();

    expect(container.querySelector('a[href="/data-export"]')).toBeNull();
  });

  it('verwijst naar het meldformulier voor verwijdering', () => {
    toon();

    expect(screen.getByRole('link', { name: 'meldformulier' }).getAttribute('href')).toBe('/ntd');
  });

  it('heeft geen toegankelijkheidsfouten', async () => {
    const { container } = toon();

    const resultaat = await axe(container);

    expect(resultaat.violations).toEqual([]);
  });
});
