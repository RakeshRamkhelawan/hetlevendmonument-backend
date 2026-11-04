import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { MemoryRouter } from 'react-router-dom';
import { About } from '../pages/About';
import { TenantProvider } from '../context/TenantContext';
import { api } from '../api/client';
import type { TenantPublicInfo, PortalSettingsResponse } from '../types';

// Mock API client
vi.mock('../api/client', () => ({
  api: {
    getPortalSettings: vi.fn(),
    resolveCurrentTenant: vi.fn(),
  },
}));

describe('FE-PAGE-016: Portal About Page White-Label Branding & Theming Injection', () => {
  const defaultTenant: TenantPublicInfo = {
    id: 1,
    name: 'Het Levend Monument',
    slug: 'default',
    domain: null,
    is_active: true,
  };

  const mockTenant: TenantPublicInfo = {
    id: 10,
    name: 'Stichting Ketikoti Vlaardingen',
    slug: 'ketikoti',
    domain: 'ketikoti.levend-monument.nl',
    is_active: true,
  };

  const mockSettings: PortalSettingsResponse = {
    platform_name_nl: 'Stichting Ketikoti Vlaardingen',
    platform_name_en: 'Ketikoti Vlaardingen Foundation',
    primary_color: '#8B4513',
    accent_color: '#D2691E',
    logo_url: 'https://example.com/logo-ketikoti.png',
    favicon_url: 'https://example.com/favicon.ico',
    about_nl: 'Wij bewaren en ontsluiten de levende koloniale en maritieme geschiedenis van Vlaardingen en haar diverse gemeenschappen.',
    about_en: 'We preserve and share the colonial and maritime heritage of Vlaardingen.',
    guidelines_nl: 'Inzendingen dienen respectvol te zijn en te voldoen aan onze ethische erfgoedstandaarden en AVG-voorschriften.',
    guidelines_en: 'Submissions must comply with ethical heritage standards.',
    contact_email: 'contact@ketikotivlaardingen.nl',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('rendert de standaard Levend Monument over-ons pagina bij ontbreken van custom instellingen', () => {
    vi.mocked(api.getPortalSettings).mockRejectedValueOnce(new Error('Settings not found'));

    render(
      <TenantProvider initialTenant={defaultTenant} initialSettings={null}>
        <MemoryRouter>
          <About />
        </MemoryRouter>
      </TenantProvider>
    );

    expect(screen.getByRole('heading', { level: 1, name: /een levende brug tussen verleden, heden en toekomst/i })).toBeInTheDocument();
    expect(screen.getByText(/over het levend monument/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /onze missie/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /ethisch & open/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /onze drie pijlers/i })).toBeInTheDocument();
  });

  it('injecteert dynamisch de stichtingsnaam, missie, richtlijnen en contact-email uit portalSettings', () => {
    render(
      <TenantProvider initialTenant={mockTenant} initialSettings={mockSettings}>
        <MemoryRouter>
          <About />
        </MemoryRouter>
      </TenantProvider>
    );

    // Platformnaam in badge en heading
    expect(screen.getAllByText(/over stichting ketikoti vlaardingen/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole('heading', { level: 1, name: /over stichting ketikoti vlaardingen/i })).toBeInTheDocument();

    // Aangepaste missietekst in hero en missiekaart
    expect(screen.getAllByText(/wij bewaren en ontsluiten de levende koloniale en maritieme geschiedenis/i).length).toBeGreaterThanOrEqual(1);

    // Stichtingslogo
    const logo = screen.getByAltText('Logo van Stichting Ketikoti Vlaardingen');
    expect(logo).toBeInTheDocument();
    expect(logo).toHaveAttribute('src', 'https://example.com/logo-ketikoti.png');

    // Community- en gedragsrichtlijnen kaart
    expect(screen.getByRole('heading', { level: 2, name: /community- & gedragsrichtlijnen/i })).toBeInTheDocument();
    expect(screen.getByText(/inzendingen dienen respectvol te zijn en te voldoen aan onze ethische erfgoedstandaarden/i)).toBeInTheDocument();

    // Officiële stichtingscorrespondentie mailto link
    expect(screen.getByText('contact@ketikotivlaardingen.nl')).toBeInTheDocument();
    const mailLink = screen.getByRole('link', { name: 'contact@ketikotivlaardingen.nl' });
    expect(mailLink).toHaveAttribute('href', 'mailto:contact@ketikotivlaardingen.nl');
  });

  it('haalt settings op via api.getPortalSettings indien nog niet aanwezig in context', async () => {
    vi.mocked(api.getPortalSettings).mockResolvedValueOnce(mockSettings);

    render(
      <TenantProvider initialTenant={mockTenant} initialSettings={null}>
        <MemoryRouter>
          <About />
        </MemoryRouter>
      </TenantProvider>
    );

    await waitFor(() => {
      expect(api.getPortalSettings).toHaveBeenCalled();
      expect(screen.getByRole('heading', { level: 1, name: /over stichting ketikoti vlaardingen/i })).toBeInTheDocument();
    });
  });

  it('voldoet 100% aan WCAG 2.1 AA richtlijnen (axe-core)', async () => {
    const { container } = render(
      <TenantProvider initialTenant={mockTenant} initialSettings={mockSettings}>
        <MemoryRouter>
          <About />
        </MemoryRouter>
      </TenantProvider>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
