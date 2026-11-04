import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HCaptchaWidget } from '../components/HCaptchaWidget';
import { Login } from '../pages/Login';
import { Newsletter } from '../pages/Newsletter';
import { NoticeTakedown } from '../pages/NoticeTakedown';
import { api } from '../api/client';

// Mock API client
vi.mock('../api/client', () => ({
  api: {
    requestMagicLink: vi.fn(),
    subscribeNewsletter: vi.fn(),
    submitTakedown: vi.fn(),
    getContentDetail: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

describe('FE-SEC-010: HCaptchaWidget & Form Integratie', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('HCaptchaWidget Component', () => {
    it('draait in testmodus wanneer er geen sitekey geconfigureerd is en triggert mock token', () => {
      const onVerify = vi.fn();
      render(<HCaptchaWidget onVerify={onVerify} />);

      expect(screen.getByText(/bot-protectie: testmodus/i)).toBeInTheDocument();
      expect(onVerify).toHaveBeenCalledWith('mock-test-hcaptcha-token');
    });

    it('bevat een toegankelijke container met aria-label voor spambeveiliging', () => {
      const onVerify = vi.fn();
      render(<HCaptchaWidget onVerify={onVerify} />);

      const container = screen.getByLabelText(/spambeveiliging verificatie/i);
      expect(container).toBeInTheDocument();
    });
  });

  describe('Login Formulier hCaptcha Integratie', () => {
    it('verstuurt hcaptcha_token mee bij het aanvragen van een magic link', async () => {
      const user = userEvent.setup();
      vi.mocked(api.requestMagicLink).mockResolvedValue({ message: 'Link verzonden' });

      render(
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      );

      const magicTab = screen.getByRole('button', { name: /magic link/i });
      await user.click(magicTab);

      const emailInput = screen.getByLabelText(/e-mailadres/i);
      await user.type(emailInput, 'curator@erfgoed.nl');

      const submitButton = screen.getByRole('button', { name: /verstuur magic link/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(api.requestMagicLink).toHaveBeenCalledWith(
          'curator@erfgoed.nl',
          'mock-test-hcaptcha-token'
        );
      });
    });
  });

  describe('Newsletter Formulier hCaptcha Integratie', () => {
    it('verstuurt hcaptcha_token mee bij het inschrijven voor de nieuwsbrief', async () => {
      const user = userEvent.setup();
      vi.mocked(api.subscribeNewsletter).mockResolvedValue({ message: 'Inschrijving gelukt' });

      render(
        <MemoryRouter>
          <Newsletter />
        </MemoryRouter>
      );

      const emailInput = screen.getByLabelText(/uw e-mailadres/i);
      await user.type(emailInput, 'lezer@erfgoed.nl');

      const submitButton = screen.getByRole('button', { name: /meld mij aan voor de nieuwsbrief/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(api.subscribeNewsletter).toHaveBeenCalledWith(
          'lezer@erfgoed.nl',
          undefined,
          undefined,
          'mock-test-hcaptcha-token'
        );
      });
    });
  });

  describe('NoticeTakedown Formulier hCaptcha Integratie', () => {
    it('verstuurt hcaptcha_token mee bij een takedown verzoek', async () => {
      const user = userEvent.setup();
      vi.mocked(api.submitTakedown).mockResolvedValue({ id: 101, message: 'Ontvangen' });

      render(
        <MemoryRouter>
          <NoticeTakedown />
        </MemoryRouter>
      );

      await user.type(screen.getByLabelText(/id van het erfgoeditem/i), '42');
      await user.type(screen.getByLabelText(/toelichting en bewijsstukken/i), 'Inbreuk op auteursrecht en privacy van nabestaanden.');
      await user.type(screen.getByLabelText(/uw volledige naam/i), 'Jan Jansen');
      await user.type(screen.getByLabelText(/uw e-mailadres/i), 'jan@voorbeeld.nl');

      const checkbox = screen.getByRole('checkbox');
      await user.click(checkbox);

      const submitButton = screen.getByRole('button', { name: /dien notice & takedown in/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(api.submitTakedown).toHaveBeenCalledWith(
          expect.objectContaining({
            content_id: 42,
            contact_email: 'jan@voorbeeld.nl',
          }),
          'mock-test-hcaptcha-token'
        );
      });
    });
  });
});
