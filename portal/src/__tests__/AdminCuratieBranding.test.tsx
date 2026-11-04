import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { AdminCuratie } from '../pages/AdminCuratie';
import { api } from '../api/client';
import type { PortalSettingsResponse } from '../types';

vi.mock('../api/client', () => ({
  api: {
    getCuratieQueue: vi.fn(),
    getCuratieAnalytics: vi.fn(),
    getPortalSettings: vi.fn(),
    updatePortalSettings: vi.fn(),
    approveContent: vi.fn(),
    rejectContent: vi.fn(),
    retagContent: vi.fn(),
    getTenantSlug: vi.fn(() => 'erfgoed'),
  },
}));

describe('FE-PAGE-014: AdminCuratie Branding & Portal Settings', () => {
  const mockSettings: PortalSettingsResponse = {
    platform_name_nl: 'Levend Monument Test Stichting',
    platform_name_en: 'Living Monument Heritage Foundation',
    primary_color: '#1a2f45',
    accent_color: '#e8b86d',
    logo_url: 'https://voorbeeld.nl/logo.png',
    favicon_url: 'https://voorbeeld.nl/favicon.ico',
    about_nl: 'Archivering en herdenking van cultureel erfgoed.',
    about_en: 'Archiving and remembering cultural heritage.',
    guidelines_nl: 'Respecteer elkaars verhalen.',
    guidelines_en: 'Respect each others stories.',
    contact_email: 'contact@stichting-erfgoed.nl',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (api.getCuratieQueue as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    (api.getCuratieAnalytics as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status_counts: { pending: 0, approved: 0, rejected: 0 },
      total_content: 0,
      average_moderation_seconds: 0,
      tag_distribution: [],
      newsletter: { total_subscribers: 0, verified_subscribers: 0 },
      education: { active_codes: 0, total_codes: 0 },
    });
    (api.getPortalSettings as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockSettings);
    (api.updatePortalSettings as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...mockSettings,
      platform_name_nl: 'Aangepaste Naam Stichting',
      primary_color: '#123456',
    });
  });

  it('navigeert naar het Branding & Instellingen tabblad en toont de instellingen', async () => {
    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const brandingTabBtn = await screen.findByRole('tab', { name: /branding & instellingen/i });
    expect(brandingTabBtn).toBeInTheDocument();

    fireEvent.click(brandingTabBtn);

    expect(await screen.findByRole('heading', { name: /white-label portaal branding/i })).toBeInTheDocument();
    expect(api.getPortalSettings).toHaveBeenCalledTimes(1);

    const titleInput = (await screen.findByLabelText(/platformnaam \(nederlands\)/i)) as HTMLInputElement;
    expect(titleInput.value).toBe('Levend Monument Test Stichting');

    const primaryColorInput = screen.getByLabelText(/primaire kleur \(hex\)/i) as HTMLInputElement;
    expect(primaryColorInput.value).toBe('#1a2f45');
  });

  it('wijzigt instellingen en verstuurt de update naar de API', async () => {
    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const brandingTabBtn = await screen.findByRole('tab', { name: /branding & instellingen/i });
    fireEvent.click(brandingTabBtn);

    const titleInput = await screen.findByLabelText(/platformnaam \(nederlands\)/i);
    fireEvent.change(titleInput, { target: { value: 'Aangepaste Naam Stichting' } });

    const primaryColorInput = screen.getByLabelText(/primaire kleur \(hex\)/i);
    fireEvent.change(primaryColorInput, { target: { value: '#123456' } });

    const submitBtn = await screen.findByRole('button', { name: /instellingen opslaan/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.updatePortalSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          platform_name_nl: 'Aangepaste Naam Stichting',
          primary_color: '#123456',
        })
      );
    });

    expect(await screen.findByText(/portaalinstellingen en white-label branding succesvol bijgewerkt!/i)).toBeInTheDocument();
  });

  it('toont een foutmelding als het opslaan via de API faalt', async () => {
    (api.updatePortalSettings as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Netwerkfout bij opslaan')
    );

    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const brandingTabBtn = await screen.findByRole('tab', { name: /branding & instellingen/i });
    fireEvent.click(brandingTabBtn);

    await screen.findByLabelText(/platformnaam \(nederlands\)/i);

    const submitBtn = await screen.findByRole('button', { name: /instellingen opslaan/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.updatePortalSettings).toHaveBeenCalled();
    });

    expect(await screen.findByText(/netwerkfout bij opslaan/i)).toBeInTheDocument();
  });

  it('voldoet aan WCAG 2.1 AA a11y richtlijnen (geen axe schendingen)', async () => {
    const { container } = render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const brandingTabBtn = await screen.findByRole('tab', { name: /branding & instellingen/i });
    fireEvent.click(brandingTabBtn);

    await screen.findByRole('heading', { name: /white-label portaal branding/i });
    await screen.findByLabelText(/platformnaam \(nederlands\)/i);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
