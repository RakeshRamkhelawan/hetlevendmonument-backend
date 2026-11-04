import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'vitest-axe';
import { MemoryRouter } from 'react-router-dom';
import { Donate } from '../pages/Donate';
import { api } from '../api/client';

// Mock API client
vi.mock('../api/client', () => ({
  api: {
    createDonationCheckout: vi.fn(),
    getDonationStats: vi.fn(),
  },
}));

describe('FE-PAGE-013: Donate Page Component & Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getDonationStats).mockResolvedValue({
      total_raised_cents: 42500,
      total_donations_count: 14,
      monthly_supporters_count: 5,
      recent_donations: [
        {
          id: 1,
          amount_cents: 2500,
          frequency: 'one_time',
          donor_name: 'Familie Van Dijk',
          message: 'Prachtig initiatief voor de stad.',
          created_at: '2026-09-12T10:00:00Z',
          is_anonymous: false,
        },
      ],
    });
  });

  it('rendert de donatiepagina met stichtingsstatistieken en bedragkiezers', async () => {
    render(
      <MemoryRouter>
        <Donate />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { name: /help mee het levend monument levend te houden/i })).toBeInTheDocument();
    expect(screen.getByText('€5')).toBeInTheDocument();
    expect(screen.getByText('€15')).toBeInTheDocument();
    expect(screen.getByText('€25')).toBeInTheDocument();
    expect(screen.getByText('€50')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Reeds bijeengebracht')).toBeInTheDocument();
      expect(screen.getByText('Betrokken gevers')).toBeInTheDocument();
      expect(screen.getByText('Vaste vrienden van het monument')).toBeInTheDocument();
      expect(screen.getByText(/Familie Van Dijk/i)).toBeInTheDocument();
    });
  });

  it('toont validatiefout bij een te laag donatiebedrag of ontbrekend e-mailadres', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Donate />
      </MemoryRouter>
    );

    const submitButton = screen.getByRole('button', { name: /ga verder naar veilige betaling/i });
    await user.click(submitButton);

    expect(screen.getByRole('alert')).toHaveTextContent(/vul alstublieft uw e-mailadres in/i);
  });

  it('schakelt anonieme modus correct in en maskeert het naaminvoerveld', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Donate />
      </MemoryRouter>
    );

    const nameInput = screen.getByLabelText(/naam of organisatie/i);
    expect(nameInput).not.toBeDisabled();

    const anonCheckbox = screen.getByLabelText(/ik wil graag anoniem doneren/i);
    await user.click(anonCheckbox);

    expect(nameInput).toBeDisabled();
    expect(nameInput).toHaveAttribute('placeholder', 'Anonieme donateur');
  });

  it('verstuurt succesvol een donatie checkout call met correcte centen', async () => {
    const user = userEvent.setup();
    vi.mocked(api.createDonationCheckout).mockResolvedValue({
      checkout_url: 'https://checkout.stripe.com/test_session',
      session_id: 'cs_test_123',
      amount_cents: 2500,
      frequency: 'monthly',
    });

    // Mock window.location.href assignment
    const originalLocation = window.location;
    delete (window as any).location;
    window.location = { ...originalLocation, href: '' } as any;

    render(
      <MemoryRouter>
        <Donate />
      </MemoryRouter>
    );

    // Kies maandelijks
    const monthlyBtn = screen.getByRole('radio', { name: /maandelijks/i });
    await user.click(monthlyBtn);

    // Kies €25 preset
    const preset25 = screen.getByText('€25');
    await user.click(preset25);

    // Vul email in
    const emailInput = screen.getByLabelText(/e-mailadres/i);
    await user.type(emailInput, 'donateur@stichting.nl');

    const submitBtn = screen.getByRole('button', { name: /ga verder naar veilige betaling/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(api.createDonationCheckout).toHaveBeenCalledWith({
        amount_cents: 2500,
        frequency: 'monthly',
        donor_email: 'donateur@stichting.nl',
        donor_name: undefined,
        is_anonymous: false,
        message: undefined,
        hcaptcha_token: 'mock-test-hcaptcha-token',
      });
      expect(window.location.href).toBe('https://checkout.stripe.com/test_session');
    });

    (window as any).location = originalLocation;
  });

  it('voldoet 100% aan WCAG 2.1 AA richtlijnen (axe-core)', async () => {
    const { container } = render(
      <MemoryRouter>
        <Donate />
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
