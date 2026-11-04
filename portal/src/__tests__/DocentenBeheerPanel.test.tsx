import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocentenBeheerPanel } from '../components/DocentenBeheerPanel';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    getDocentaanvragen: vi.fn(),
    getDocenten: vi.fn(),
    keurDocentaanvraagGoed: vi.fn(),
    wijsDocentaanvraagAf: vi.fn(),
    trekDocentrolIn: vi.fn(),
  },
}));

const m = (f: unknown) => f as ReturnType<typeof vi.fn>;
const aanvraag = {
  id: 4, name: 'Juf Anna', email: 'anna@school.nl', school: 'De Vlinder', function: null, motivation: null,
  status: 'pending' as const, created_at: '2026-11-03T08:00:00Z', decided_at: null,
};

describe('Beheertab Docenten (BE-EP-055)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    m(api.getDocentaanvragen).mockResolvedValue([aanvraag]);
    m(api.getDocenten).mockResolvedValue([]);
  });

  it('keurt een aanvraag goed en meldt dat de welkomstmail is verstuurd', async () => {
    m(api.keurDocentaanvraagGoed).mockResolvedValue({ ...aanvraag, status: 'approved' });
    render(<DocentenBeheerPanel />);
    fireEvent.click(await screen.findByRole('button', { name: /Goedkeuren/ }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('welkomstmail'));
    expect(api.keurDocentaanvraagGoed).toHaveBeenCalledWith(4);
  });

  it('afwijzen vraagt eerst om bevestiging en stuurt de reden mee', async () => {
    m(api.wijsDocentaanvraagAf).mockResolvedValue({ ...aanvraag, status: 'rejected' });
    render(<DocentenBeheerPanel />);
    fireEvent.click(await screen.findByRole('button', { name: /Afwijzen/ }));
    expect(api.wijsDocentaanvraagAf).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Reden/), { target: { value: 'Geen school gevonden' } });
    fireEvent.click(screen.getByRole('button', { name: 'Bevestig afwijzen' }));
    await waitFor(() => expect(api.wijsDocentaanvraagAf).toHaveBeenCalledWith(4, 'Geen school gevonden'));
  });
});
