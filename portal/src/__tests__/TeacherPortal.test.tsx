import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TeacherPortal } from '../pages/TeacherPortal';
import { api } from '../api/client';

vi.mock('../components/CaptchaVeld', () => ({
  CaptchaVeld: ({ onToken }: { onToken: (t: string) => void }) => (
    <button type="button" onClick={() => onToken('captcha-ok')}>
      captcha
    </button>
  ),
}));

vi.mock('../api/client', () => ({
  api: {
    getAuthToken: vi.fn(),
    getDocentIk: vi.fn(),
    vraagDocentaccountAan: vi.fn(),
    getKlassen: vi.fn(),
    getLesmateriaal: vi.fn(),
    getLesmateriaalDetail: vi.fn(),
    maakKlas: vi.fn(),
    downloadLesPdf: vi.fn(),
  },
}));

const m = (f: unknown) => f as ReturnType<typeof vi.fn>;
const toon = () =>
  render(
    <MemoryRouter>
      <TeacherPortal />
    </MemoryRouter>,
  );

describe('Docentenportaal (BE-EP-055)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('toont zonder login het aanvraagformulier en een inlogknop', async () => {
    m(api.getAuthToken).mockReturnValue(null);
    toon();
    expect(await screen.findByRole('form', { name: 'Docentaccount aanvragen' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Inloggen' }).getAttribute('href')).toBe('/inloggen?redirect=/docenten');
    expect(api.getDocentIk).not.toHaveBeenCalled();
  });

  it('verstuurt een aanvraag met het captcha-token', async () => {
    m(api.getAuthToken).mockReturnValue(null);
    m(api.vraagDocentaccountAan).mockResolvedValue({ message: 'ok' });
    toon();
    fireEvent.change(await screen.findByLabelText('Naam *'), { target: { value: 'Juf Anna' } });
    fireEvent.change(screen.getByLabelText('E-mailadres van school *'), { target: { value: 'anna@school.nl' } });
    fireEvent.change(screen.getByLabelText('School *'), { target: { value: 'De Vlinder' } });
    fireEvent.click(screen.getByRole('button', { name: 'captcha' }));
    fireEvent.click(screen.getByRole('button', { name: 'Aanvraag versturen' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Uw aanvraag is ontvangen'));
    expect(api.vraagDocentaccountAan).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Juf Anna', email: 'anna@school.nl', school: 'De Vlinder', hcaptcha_token: 'captcha-ok' }),
    );
  });

  it('een ingelogde bezoeker met een open aanvraag ziet de status, geen dashboard', async () => {
    m(api.getAuthToken).mockReturnValue('jwt');
    m(api.getDocentIk).mockResolvedValue({ email: 'a@b.nl', display_name: null, role: 'visitor', is_docent: false, aanvraag_status: 'pending' });
    toon();
    expect(await screen.findByText('Uw aanvraag is ontvangen en wordt bekeken.')).toBeInTheDocument();
    expect(api.getKlassen).not.toHaveBeenCalled();
  });

  it('een docent maakt een klas en ziet de klascode een keer', async () => {
    m(api.getAuthToken).mockReturnValue('jwt');
    m(api.getDocentIk).mockResolvedValue({ email: 'juf@school.nl', display_name: 'Juf', role: 'teacher', is_docent: true, aanvraag_status: 'approved' });
    m(api.getKlassen).mockResolvedValue([]);
    m(api.getLesmateriaal).mockResolvedValue([]);
    m(api.maakKlas).mockResolvedValue({
      id: 8, naam: 'Groep 8B', niveau: 'groep-7-8', actief: true, verloopt_op: '2026-12-01T00:00:00Z',
      les_ids: [7, 8], aantal_antwoorden: 0, aangemaakt_op: null, code: 'K7N2P9Q4',
    });
    toon();
    fireEvent.change(await screen.findByLabelText('Naam van de klas'), { target: { value: 'Groep 8B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Klas en klascode maken' }));
    expect(await screen.findByTestId('klascode')).toHaveTextContent('K7N2P9Q4');
    expect(api.maakKlas).toHaveBeenCalledWith({ naam: 'Groep 8B', niveau: 'groep-7-8', geldig_dagen: 28 });
    expect(screen.getByRole('heading', { name: 'Groep 8B' })).toBeInTheDocument();
  });
});
