import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TeacherPortal } from '../pages/TeacherPortal';
import { api } from '../api/client';

// FE-EDU-002, sinds BE-EP-055 (2026-11-03): een docent maakt een klascode door een klas aan te
// maken; de code komt EENMALIG terug van POST /docent/klassen.

vi.mock('../components/CaptchaVeld', () => ({ CaptchaVeld: () => null }));

vi.mock('../api/client', () => ({
  api: {
    getAuthToken: vi.fn(() => 'jwt'),
    getDocentIk: vi.fn(),
    getKlassen: vi.fn(),
    getLesmateriaal: vi.fn(),
    getLesmateriaalDetail: vi.fn(),
    maakKlas: vi.fn(),
  },
}));

const m = (f: unknown) => f as ReturnType<typeof vi.fn>;
const klas = {
  id: 8, naam: '3 VWO Geschiedenis', niveau: 'onderbouw-vo', actief: true, verloopt_op: '2026-12-01T00:00:00Z',
  les_ids: [13], aantal_antwoorden: 0, aangemaakt_op: null, code: 'K7N2P9Q4',
};

const toon = () =>
  render(
    <MemoryRouter>
      <TeacherPortal />
    </MemoryRouter>,
  );

describe('FE-EDU-002: TeacherPortal Live Code Generation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    m(api.getAuthToken).mockReturnValue('jwt');
    m(api.getDocentIk).mockResolvedValue({ email: 'docent@school.nl', display_name: 'Docent', role: 'teacher', is_docent: true, aanvraag_status: null });
    m(api.getKlassen).mockResolvedValue([]);
    m(api.getLesmateriaal).mockResolvedValue([]);
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('rendert het formulier met klasnaam, niveau en geldigheid', async () => {
    toon();
    expect(await screen.findByLabelText('Naam van de klas')).toBeInTheDocument();
    expect(screen.getByLabelText('Niveau')).toBeInTheDocument();
    expect(screen.getByLabelText('Klascode geldig')).toBeInTheDocument();
  });

  it('roept api.maakKlas aan met de ingevoerde waarden en toont de gegenereerde code', async () => {
    m(api.maakKlas).mockResolvedValue(klas);
    toon();
    fireEvent.change(await screen.findByLabelText('Naam van de klas'), { target: { value: '3 VWO Geschiedenis' } });
    fireEvent.change(screen.getByLabelText('Niveau'), { target: { value: 'onderbouw-vo' } });
    fireEvent.change(screen.getByLabelText('Klascode geldig'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Klas en klascode maken' }));
    expect(await screen.findByTestId('klascode')).toHaveTextContent('K7N2P9Q4');
    expect(api.maakKlas).toHaveBeenCalledWith({ naam: '3 VWO Geschiedenis', niveau: 'onderbouw-vo', geldig_dagen: 7 });
  });

  it('kopieert de code naar het klembord bij klikken op de kopieerknop', async () => {
    m(api.maakKlas).mockResolvedValue(klas);
    toon();
    fireEvent.change(await screen.findByLabelText('Naam van de klas'), { target: { value: '3 VWO Geschiedenis' } });
    fireEvent.click(screen.getByRole('button', { name: 'Klas en klascode maken' }));
    fireEvent.click(await screen.findByRole('button', { name: /Kopieer/ }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('K7N2P9Q4');
    expect(await screen.findByText('Gekopieerd')).toBeInTheDocument();
  });

  it('toont een foutmelding als de API call faalt', async () => {
    m(api.maakKlas).mockRejectedValue(new Error('API Error [403]: Docentaccount vereist'));
    toon();
    fireEvent.change(await screen.findByLabelText('Naam van de klas'), { target: { value: 'Groep 8' } });
    fireEvent.click(screen.getByRole('button', { name: 'Klas en klascode maken' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Docentaccount vereist'));
  });
});
