import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EduPortal } from '../pages/EduPortal';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    getEduSession: vi.fn(),
    getEduContent: vi.fn(),
    validateEduAccess: vi.fn(),
    getContentList: vi.fn(),
  },
}));

describe('FE-EDU-003: EduPortal Code Validation & User-Friendly Errors', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getEduSession as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(null);
    (api.getEduContent as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [], total: 0 });
    (api.getContentList as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [], total: 0 });
    localStorage.setItem('portal_token', 'valid-admin-jwt-token');
  });

  it('toont duidelijke Nederlandse foutmelding bij ongeldige of verlopen code (401)', async () => {
    (api.validateEduAccess as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('API Error [401]: Invalid or expired code')
    );

    render(
      <MemoryRouter>
        <EduPortal />
      </MemoryRouter>
    );

    const input = screen.getByPlaceholderText(/bijv\. 4mah8xyd/i);
    fireEvent.change(input, { target: { value: 'TESTCODE' } });

    const submitBtn = screen.getByRole('button', { name: /inloggen/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText('De ingevoerde toegangscode is ongeldig of verlopen. Controleer de 8-tekens code met uw docent.')
      ).toBeInTheDocument();
    });

    // Verifieer dat er GEEN rauwe Engelse fouttekst getoond wordt
    expect(screen.queryByText(/API Error/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Invalid or expired code/i)).not.toBeInTheDocument();

    // Verifieer dat het portal_token van de beheerder NIET gewist is
    expect(localStorage.getItem('portal_token')).toBe('valid-admin-jwt-token');
  });

  it('toont vriendelijke rate-limit foutmelding bij 429 status', async () => {
    (api.validateEduAccess as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('API Error [429]: Rate limit exceeded')
    );

    render(
      <MemoryRouter>
        <EduPortal />
      </MemoryRouter>
    );

    const input = screen.getByPlaceholderText(/bijv\. 4mah8xyd/i);
    fireEvent.change(input, { target: { value: 'TESTCODE' } });

    const submitBtn = screen.getByRole('button', { name: /inloggen/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText('Te veel pogingen. Wacht een minuut voordat u het opnieuw probeert.')
      ).toBeInTheDocument();
    });
  });

  it('activeert educatieve sessie bij een geldige klascode', async () => {
    (api.validateEduAccess as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      status: 'valid',
      message: 'Access granted',
    });
    (api.getEduSession as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      is_active: true,
      role: 'student',
      session_id: 'session-xyz',
    });

    render(
      <MemoryRouter>
        <EduPortal />
      </MemoryRouter>
    );

    const input = screen.getByPlaceholderText(/bijv\. 4mah8xyd/i);
    fireEvent.change(input, { target: { value: 'K7N2P9Q4' } });

    const submitBtn = screen.getByRole('button', { name: /inloggen/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Klassikale Sessie Geactiveerd')).toBeInTheDocument();
    });
  });

  it('haalt de werkbladen op na een geldige klascode en groepeert ze per niveau', async () => {
    (api.validateEduAccess as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ status: 'valid' });
    (api.getEduSession as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({ is_active: true, role: 'student', session_id: 's' });
    (api.getEduContent as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({
        items: [
          { id: 8, title: 'Werkblad groep 7-8, les 2: Curacao, 1795', summary: null, content_type: 'educational_workbook', target_age_group: 'groep-7-8' },
          { id: 7, title: 'Werkblad groep 7-8, les 1: Schiedam, 1602', summary: null, content_type: 'educational_workbook', target_age_group: 'groep-7-8' },
          { id: 13, title: 'Werkblad onderbouw vo, les 1: Schiedam, 1602', summary: null, content_type: 'educational_workbook', target_age_group: 'onderbouw-vo' },
        ],
        total: 3,
      });

    render(
      <MemoryRouter>
        <EduPortal />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText(/bijv\. 4mah8xyd/i), { target: { value: 'K7N2P9Q4' } });
    fireEvent.click(screen.getByRole('button', { name: /inloggen/i }));

    await waitFor(() => {
      expect(screen.getByText('Werkblad groep 7-8, les 1: Schiedam, 1602')).toBeInTheDocument();
    });
    expect(api.getEduContent).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('heading', { name: 'Groep 7-8' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Onderbouw VO' })).toBeInTheDocument();
    const titels = screen.getAllByRole('heading', { level: 4 }).map((h) => h.textContent);
    expect(titels.indexOf('Werkblad groep 7-8, les 1: Schiedam, 1602')).toBeLessThan(
      titels.indexOf('Werkblad groep 7-8, les 2: Curacao, 1795'),
    );
  });

  it('toont de actieve sessie ook met het echte API-antwoord (alleen role en expires_at)', async () => {
    (api.getEduSession as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      role: 'student',
      expires_at: '2026-12-02T22:20:10Z',
    });

    render(
      <MemoryRouter>
        <EduPortal />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Klassikale Sessie Geactiveerd')).toBeInTheDocument();
    });
  });
});
