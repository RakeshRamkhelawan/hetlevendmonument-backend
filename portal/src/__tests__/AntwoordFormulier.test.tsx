import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AntwoordFormulier } from '../components/AntwoordFormulier';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: { getMijnAntwoorden: vi.fn(), slaAntwoordenOp: vi.fn() },
}));

const m = (f: unknown) => f as ReturnType<typeof vi.fn>;
const vragen = [
  { sleutel: 'vraag-1', sectie: 'Vragen bij het verhaal', tekst: 'Hoe heet Kwaku echt?' },
  { sleutel: 'denk-mee', sectie: 'Denk mee', tekst: 'Wat bedoelt de schrijver?' },
];

describe('Antwoorden van een leerling (BE-EP-055)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('slaat naam en antwoorden op met een token dat de browser bewaart', async () => {
    m(api.getMijnAntwoorden).mockResolvedValue({ naam: null, antwoorden: {}, feedback: null, bijgewerkt_op: null, verwijderd_na: null });
    m(api.slaAntwoordenOp).mockResolvedValue({ naam: 'Sam', antwoorden: { 'vraag-1': 'Kwaku' }, feedback: null, bijgewerkt_op: null, verwijderd_na: '2026-12-29T00:00:00Z' });
    render(<AntwoordFormulier contentId={7} vragen={vragen} />);
    fireEvent.change(screen.getByLabelText('Je voornaam of bijnaam'), { target: { value: 'Sam' } });
    fireEvent.change(screen.getByLabelText('Hoe heet Kwaku echt?'), { target: { value: 'Kwaku' } });
    fireEvent.click(screen.getByRole('button', { name: 'Antwoorden opslaan' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Opgeslagen'));
    const [id, token, data] = m(api.slaAntwoordenOp).mock.calls[0];
    expect(id).toBe(7);
    expect(token).toHaveLength(48);
    expect(localStorage.getItem('hlm_leerling_token')).toBe(token);
    expect(data).toEqual({ naam: 'Sam', antwoorden: { 'vraag-1': 'Kwaku' } });
  });

  it('toont eerder opgeslagen antwoorden en de feedback van de docent', async () => {
    m(api.getMijnAntwoorden).mockResolvedValue({ naam: 'Sam', antwoorden: { 'denk-mee': 'Niemand kent hem' }, feedback: 'Mooi verwoord!', bijgewerkt_op: null, verwijderd_na: null });
    render(<AntwoordFormulier contentId={7} vragen={vragen} />);
    expect(await screen.findByText('Mooi verwoord!')).toBeInTheDocument();
    expect(screen.getByLabelText('Wat bedoelt de schrijver?')).toHaveValue('Niemand kent hem');
  });

  it('legt uit dat een docentcode geen antwoorden kan opslaan', async () => {
    m(api.getMijnAntwoorden).mockResolvedValue({ naam: null, antwoorden: {}, feedback: null, bijgewerkt_op: null, verwijderd_na: null });
    m(api.slaAntwoordenOp).mockRejectedValue(new Error('API Error [403]: Alleen leerlingen slaan antwoorden op'));
    render(<AntwoordFormulier contentId={7} vragen={vragen} />);
    fireEvent.change(screen.getByLabelText('Je voornaam of bijnaam'), { target: { value: 'Sam' } });
    fireEvent.click(screen.getByRole('button', { name: 'Antwoorden opslaan' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Vraag je docent om een leerlingcode');
  });
});
