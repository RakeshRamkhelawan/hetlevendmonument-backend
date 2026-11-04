import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NotFound } from '../pages/NotFound';

describe('NotFound 404 Page (WI-10)', () => {
  it('toont duidelijke 404 foutboodschap en warme styling', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Pagina niet gevonden');
    expect(screen.getByText('404')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Zoek een verhaal, locatie of monument...')).toBeInTheDocument();
  });

  it('bevat navigatieknoppen naar Home en Erfgoedkaart', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );

    const homeLink = screen.getByRole('link', { name: /naar de homepage/i });
    expect(homeLink).toHaveAttribute('href', '/');

    const mapLink = screen.getByRole('link', { name: /open erfgoedkaart/i });
    expect(mapLink).toHaveAttribute('href', '/kaart');
  });
});
