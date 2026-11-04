import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'vitest-axe';
import { MemoryRouter } from 'react-router-dom';
import { Contact } from '../pages/Contact';
import { api } from '../api/client';

// Mock API client
vi.mock('../api/client', () => ({
  api: {
    submitContactForm: vi.fn(),
  },
}));

describe('FE-PAGE-015: Contact & Community Support Page Component & Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('rendert de contactpagina met directe contactgegevens, formulier en faqs', () => {
    render(
      <MemoryRouter>
        <Contact />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { level: 1, name: /neem contact met ons op/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /directe gegevens/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /veelgestelde vragen/i })).toBeInTheDocument();

    expect(screen.getByLabelText(/uw naam/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/uw e-mailadres/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/categorie/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/onderwerp/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/bericht/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /verstuur bericht/i })).toBeInTheDocument();
  });

  it('verstuurt het contactformulier succesvol en toont het referentienummer', async () => {
    const user = userEvent.setup();
    vi.mocked(api.submitContactForm).mockResolvedValue({
      reference_id: 'CON-20260912-A1B2',
      status: 'received',
      message: 'Uw bericht is succesvol ontvangen.',
      created_at: '2026-09-12T12:00:00Z',
    });

    render(
      <MemoryRouter>
        <Contact />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/uw naam/i), 'Jan de Vries');
    await user.type(screen.getByLabelText(/uw e-mailadres/i), 'jan@voorbeeld.nl');
    await user.selectOptions(screen.getByLabelText(/categorie/i), 'educatie');
    await user.type(screen.getByLabelText(/onderwerp/i), 'Gastles Primair Onderwijs');
    await user.type(screen.getByLabelText(/bericht/i), 'Graag willen wij informatie ontvangen over lesmateriaal.');

    const submitBtn = screen.getByRole('button', { name: /verstuur bericht/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(api.submitContactForm).toHaveBeenCalledWith({
        name: 'Jan de Vries',
        email: 'jan@voorbeeld.nl',
        category: 'educatie',
        subject: 'Gastles Primair Onderwijs',
        message: 'Graag willen wij informatie ontvangen over lesmateriaal.',
        hcaptcha_token: 'mock-test-hcaptcha-token',
      });
      expect(screen.getByRole('heading', { name: /bericht verzonden/i })).toBeInTheDocument();
      expect(screen.getByText('CON-20260912-A1B2')).toBeInTheDocument();
      expect(screen.getByText(/jan@voorbeeld.nl/i)).toBeInTheDocument();
    });

    // Resetknop 'Nog een bericht sturen'
    const resetBtn = screen.getByRole('button', { name: /nog een bericht sturen/i });
    await user.click(resetBtn);

    expect(screen.getByLabelText(/uw naam/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/uw naam/i)).toHaveValue('Jan de Vries');
    expect(screen.getByLabelText(/onderwerp/i)).toHaveValue('');
    expect(screen.getByLabelText(/bericht/i)).toHaveValue('');
  });

  it('toont een toegankelijke foutmelding bij een API fout zonder velden te wissen', async () => {
    const user = userEvent.setup();
    vi.mocked(api.submitContactForm).mockRejectedValue(
      new Error('E-mailservice tijdelijk niet beschikbaar.')
    );

    render(
      <MemoryRouter>
        <Contact />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/uw naam/i), 'Jan de Vries');
    await user.type(screen.getByLabelText(/uw e-mailadres/i), 'jan@voorbeeld.nl');
    await user.type(screen.getByLabelText(/onderwerp/i), 'Vraag');
    await user.type(screen.getByLabelText(/bericht/i), 'Test bericht');

    const submitBtn = screen.getByRole('button', { name: /verstuur bericht/i });
    await user.click(submitBtn);

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toHaveTextContent(/e-mailservice tijdelijk niet beschikbaar/i);
    });

    // Velden blijven intact
    expect(screen.getByLabelText(/uw naam/i)).toHaveValue('Jan de Vries');
    expect(screen.getByLabelText(/bericht/i)).toHaveValue('Test bericht');
  });

  it('voldoet 100% aan WCAG 2.1 AA richtlijnen (axe-core)', async () => {
    const { container } = render(
      <MemoryRouter>
        <Contact />
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
