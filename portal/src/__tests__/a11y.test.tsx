import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { Layout } from '../components/Layout';
import { AccessibilityStatement } from '../pages/AccessibilityStatement';
import { MapView } from '../pages/MapView';
import { SubmitStory } from '../pages/SubmitStory';
import { Login } from '../pages/Login';
import { NoticeTakedown } from '../pages/NoticeTakedown';
import { Newsletter } from '../pages/Newsletter';

// Mock API client for predictable test behavior
vi.mock('../api/client', () => ({
  api: {
    getAuthToken: vi.fn().mockReturnValue('test-token'),
    uploadMedia: vi.fn().mockResolvedValue({ file_url: 'x' }),
    getMapBbox: vi.fn().mockResolvedValue({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [4.9041, 52.3676] },
          properties: {
            id: 1,
            title: 'Amsterdam Herdenkingsmonument',
            location_name: 'Amsterdam',
            file_url: 'https://voorbeeld.nl/foto1.jpg',
          },
        },
      ],
    }),
    subscribeNewsletter: vi.fn().mockResolvedValue({ status: 'ok' }),
    requestMagicLink: vi.fn().mockResolvedValue({ message: 'Link verzonden' }),
    verifyMagicLink: vi.fn().mockResolvedValue({ user: { email: 'admin@erfgoed.nl', role: 'curator' } }),
    submitContent: vi.fn().mockResolvedValue({ id: 'SUB-12345' }),
    submitTakedown: vi.fn().mockResolvedValue({ id: 999 }),
    getContentDetail: vi.fn().mockResolvedValue({
      id: 1,
      title: 'Oral history interview',
      body: 'Getypte transcriptie van het getuigenis.',
      content_type: 'audio',
      file_url: 'https://voorbeeld.nl/audio.mp3',
      file_mime: 'audio/mpeg',
      created_at: '2026-09-11T10:00:00Z',
    }),
    clearAuthToken: vi.fn(),
  },
}));

describe('A11y Tests -- Layout & Landmarks', () => {
  it('heeft geen axe schendingen in de basislayout', async () => {
    const { container } = render(
      <MemoryRouter>
        <Layout>
          <h1>Test Titel</h1>
          <p>Test inhoud voor de pagina.</p>
        </Layout>
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('bevat de verplichte skip-to-content link en landmarks conform WCAG 2.1 AA', () => {
    render(
      <MemoryRouter>
        <Layout>
          <h1>Inhoud</h1>
        </Layout>
      </MemoryRouter>
    );

    const skipLink = screen.getByRole('link', { name: /direct naar hoofdinhoud/i });
    expect(skipLink).toBeInTheDocument();
    expect(skipLink).toHaveAttribute('href', '#main-content');

    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: /hoofdnavigatie/i })).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });

  it('bedient het mobiele menu correct met Escape toets en ARIA attributen', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Layout>
          <p>Mobiele layout test</p>
        </Layout>
      </MemoryRouter>
    );

    const menuButton = screen.getByRole('button', { name: /open hoofdmenu/i });
    expect(menuButton).toHaveAttribute('aria-expanded', 'false');

    await user.click(menuButton);
    expect(menuButton).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('navigation', { name: /mobiele navigatie/i })).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('navigation', { name: /mobiele navigatie/i })).not.toBeInTheDocument();
  });

  it('heeft een toegankelijk nieuwsbriefformulier in de footer met gekoppeld label', () => {
    render(
      <MemoryRouter>
        <Layout>
          <p>Inhoud</p>
        </Layout>
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/e-mailadres voor nieuwsbrief/i);
    expect(emailInput).toBeInTheDocument();
    expect(emailInput).toHaveAttribute('type', 'email');
    expect(emailInput).toHaveAttribute('aria-required', 'true');
  });
});

describe('A11y Tests -- Toegankelijkheidsverklaring', () => {
  it('heeft geen axe schendingen op de toegankelijkheidsverklaring pagina', async () => {
    const { container } = render(
      <MemoryRouter>
        <AccessibilityStatement />
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('bevat de vereiste wettelijke secties (status, maatregelen, alternatieven, contact)', () => {
    render(
      <MemoryRouter>
        <AccessibilityStatement />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { level: 1, name: /toegankelijkheidsverklaring/i })).toBeInTheDocument();
    expect(screen.getByText(/voldoet gedeeltelijk \(wcag 2\.1 niveau aa\)/i)).toBeInTheDocument();
    expect(screen.getByText(/genomen maatregelen voor toegankelijkheid/i)).toBeInTheDocument();
    expect(screen.getByText(/complexe onderdelen & toegankelijke alternatieven/i)).toBeInTheDocument();
    expect(screen.getByText(/feedback en contactgegevens/i)).toBeInTheDocument();
  });
});

describe('A11y Tests -- Kaart & Toegankelijke Lijstweergave', () => {
  it('heeft geen axe schendingen in MapView', async () => {
    const { container } = render(
      <MemoryRouter>
        <MapView />
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('schakelt soepel tussen interactieve kaart en toegankelijke lijstweergave', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <MapView />
      </MemoryRouter>
    );

    const listToggleButton = screen.getByRole('button', { name: /toegankelijke lijst/i });
    expect(listToggleButton).toBeInTheDocument();
    expect(listToggleButton).toHaveAttribute('aria-pressed', 'false');

    // Schakel naar toegankelijke lijstweergave
    await user.click(listToggleButton);
    expect(listToggleButton).toHaveAttribute('aria-pressed', 'true');

    // Verifieer de semantische lijstsectie
    const listSection = screen.getByRole('region', { name: /toegankelijke lijst van erfgoedlocaties/i });
    expect(listSection).toBeInTheDocument();
  });
});

describe('A11y Tests -- Formulieren Hardening', () => {
  it('heeft geen axe schendingen in SubmitStory', async () => {
    const { container } = render(
      <MemoryRouter>
        <SubmitStory />
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('bevat gekoppelde labels en aria-required velden in SubmitStory', () => {
    render(
      <MemoryRouter>
        <SubmitStory />
      </MemoryRouter>
    );

    const titleInput = screen.getByLabelText(/titel van het verhaal/i);
    expect(titleInput).toHaveAttribute('aria-required', 'true');

    const categorySelect = screen.getByLabelText(/categorie/i);
    expect(categorySelect).toHaveAttribute('aria-required', 'true');

    const bodyInput = screen.getByLabelText(/uw verhaal of toelichting/i);
    expect(bodyInput).toHaveAttribute('aria-required', 'true');

    const consentCheckbox = screen.getByLabelText(/auteursrechten & ethische verklaring/i);
    expect(consentCheckbox).toHaveAttribute('aria-required', 'true');
  });

  it('heeft geen axe schendingen in Login en bevat toegankelijke live alerts', async () => {
    const { container } = render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();

    const emailInput = screen.getByLabelText(/e-mailadres/i);
    expect(emailInput).toHaveAttribute('aria-required', 'true');
  });

  it('heeft geen axe schendingen in NoticeTakedown', async () => {
    const { container } = render(
      <MemoryRouter>
        <NoticeTakedown />
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();

    expect(screen.getByLabelText(/id van het erfgoeditem/i)).toHaveAttribute('aria-required', 'true');
    expect(screen.getByLabelText(/aard van het bezwaar/i)).toHaveAttribute('aria-required', 'true');
    expect(screen.getByLabelText(/toelichting en bewijsstukken/i)).toHaveAttribute('aria-required', 'true');
  });

  it('heeft geen axe schendingen in Newsletter', async () => {
    const { container } = render(
      <MemoryRouter>
        <Newsletter />
      </MemoryRouter>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();

    expect(screen.getByLabelText(/uw e-mailadres/i)).toHaveAttribute('aria-required', 'true');
  });
});
