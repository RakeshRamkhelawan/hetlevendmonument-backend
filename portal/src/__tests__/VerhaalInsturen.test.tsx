/**
 * BE-EP-056: een verteller stuurt een verhaal in met foto of geluid.
 *
 * - Niet ingelogd: eerst e-mailadres en inloglink (met aanmelden), daarna terug.
 * - Ingelogd: bestand kiezen vanaf het apparaat, plek op de kaart, geen los e-mailveld.
 * - Na het opslaan van het verhaal wordt het bestand geupload; mislukt dat, dan kan het opnieuw.
 * - Na inloggen alleen terug naar een pad binnen deze site.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { SubmitStory } from '../pages/SubmitStory';
import { controleerBestand, MAX_BESTAND_BYTES } from '../components/BestandKiezer';
import { NA_INLOGGEN_SLEUTEL, neemNaInloggen, onthoudNaInloggen } from '../naInloggen';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    getAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    requestMagicLink: vi.fn(),
    submitContent: vi.fn(),
    uploadMedia: vi.fn(),
  },
}));

vi.mock('../components/PlekKiezer', () => ({
  PlekKiezer: ({ onKies }: { onKies: (p: { lat: number; lng: number }) => void }) => (
    <button type="button" onClick={() => onKies({ lat: 5.85, lng: -55.2 })}>
      Kies Paramaribo op de kaart
    </button>
  ),
}));

vi.mock('../components/CaptchaVeld', () => ({
  CaptchaVeld: ({ onToken }: { onToken: (t: string | null) => void }) => (
    <button type="button" onClick={() => onToken('captcha-ok')}>
      Ik ben een mens
    </button>
  ),
}));

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const toon = () =>
  render(
    <MemoryRouter>
      <SubmitStory />
    </MemoryRouter>,
  );

const foto = () => new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3])], 'oma.jpg', { type: 'image/jpeg' });

const vulVerplicht = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByLabelText(/titel van het verhaal/i), 'Oma in Paramaribo');
  await user.type(screen.getByLabelText(/uw verhaal of toelichting/i), 'Een herinnering.');
  await user.click(screen.getByLabelText(/auteursrechten & ethische verklaring/i));
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mocked.getAuthToken.mockReturnValue(null);
  mocked.requestMagicLink.mockResolvedValue({ message: 'ok' });
  mocked.submitContent.mockResolvedValue({ id: '77' });
  mocked.uploadMedia.mockResolvedValue({ file_url: 'x' });
});

describe('Niet ingelogd: eerst het e-mailadres', () => {
  it('toont stap 1 en nog geen formulier', () => {
    toon();
    expect(screen.getByText(/stap 1: uw e-mailadres/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/titel van het verhaal/i)).not.toBeInTheDocument();
  });

  it('vraagt een inloglink aan met aanmelden en onthoudt de weg terug', async () => {
    const user = userEvent.setup();
    toon();
    await user.type(screen.getByLabelText(/uw e-mailadres/i), 'verteller@example.org');
    await user.click(screen.getByRole('button', { name: /ik ben een mens/i }));
    await user.click(screen.getByRole('button', { name: /stuur mij een inloglink/i }));

    await waitFor(() =>
      expect(mocked.requestMagicLink).toHaveBeenCalledWith('verteller@example.org', 'captcha-ok', { aanmelden: true }),
    );
    expect(localStorage.getItem(NA_INLOGGEN_SLEUTEL)).toBe('/uploaden');
    expect(await screen.findByText(/kijk in uw e-mail/i)).toBeInTheDocument();
  });

  it('legt een captcha-fout in gewone taal uit', async () => {
    mocked.requestMagicLink.mockRejectedValue(new Error('API Error [400]: CAPTCHA_FAILED'));
    const user = userEvent.setup();
    toon();
    await user.type(screen.getByLabelText(/uw e-mailadres/i), 'verteller@example.org');
    await user.click(screen.getByRole('button', { name: /stuur mij een inloglink/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/vink eerst het vakje/i);
  });

  it('heeft geen axe-schendingen', async () => {
    const { container } = toon();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('Ingelogd: verhaal met bestand en plek', () => {
  beforeEach(() => {
    mocked.getAuthToken.mockReturnValue('jwt');
  });

  it('heeft geen los e-mailveld meer', () => {
    toon();
    expect(screen.queryByLabelText(/e-mailadres/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/breedtegraad/i)).not.toBeInTheDocument();
  });

  it('slaat eerst het verhaal op en uploadt daarna het gekozen bestand', async () => {
    const user = userEvent.setup();
    toon();
    await vulVerplicht(user);
    const bestand = foto();
    await user.upload(screen.getByLabelText(/foto, geluid of document kiezen/i), bestand);
    await user.click(screen.getByRole('button', { name: /kies paramaribo op de kaart/i }));
    await user.click(screen.getByRole('button', { name: /verstuur naar het erfgoedarchief/i }));

    await waitFor(() => expect(mocked.uploadMedia).toHaveBeenCalledWith('77', bestand, { extra: true }));
    expect(mocked.submitContent).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Oma in Paramaribo', latitude: 5.85, longitude: -55.2, media_type: 'image' }),
    );
    expect(mocked.submitContent.mock.invocationCallOrder[0]).toBeLessThan(mocked.uploadMedia.mock.invocationCallOrder[0]);
    expect(await screen.findByText(/hartelijk dank voor uw inzending/i)).toBeInTheDocument();
  });

  it('laat het bestand opnieuw proberen als de upload mislukt', async () => {
    mocked.uploadMedia.mockRejectedValueOnce(new Error('API Error [400]: File could not be processed'));
    const user = userEvent.setup();
    toon();
    await vulVerplicht(user);
    await user.upload(screen.getByLabelText(/foto, geluid of document kiezen/i), foto());
    await user.click(screen.getByRole('button', { name: /verstuur naar het erfgoedarchief/i }));

    expect(await screen.findByText(/dit bestand kunnen we niet lezen/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /bestand opnieuw proberen/i }));
    await waitFor(() => expect(mocked.uploadMedia).toHaveBeenCalledTimes(2));
  });

  it('uploadt meerdere bestanden na elkaar en probeert alleen het mislukte opnieuw (BE-EP-057)', async () => {
    const een = foto();
    const twee = new File([new Uint8Array([1, 2, 3])], 'opname.m4a', { type: 'audio/mp4' });
    const drie = new File([new Uint8Array([4, 5, 6])], 'brief.pdf', { type: 'application/pdf' });
    mocked.uploadMedia.mockImplementation(async (_id: string, f: File) => {
      if (f === twee && mocked.uploadMedia.mock.calls.length === 2) throw new Error('API Error [500]: File storage failed');
      return { file_url: 'x' };
    });
    const user = userEvent.setup();
    toon();
    await vulVerplicht(user);
    await user.upload(screen.getByLabelText(/foto, geluid of document kiezen/i), [een, twee, drie]);
    expect(screen.getAllByRole('button', { name: /verwijderen/i })).toHaveLength(3);
    await user.click(screen.getByRole('button', { name: /verstuur naar het erfgoedarchief/i }));

    await waitFor(() => expect(mocked.uploadMedia).toHaveBeenCalledTimes(3));
    expect(mocked.uploadMedia.mock.calls.map((c: unknown[]) => c[1])).toEqual([een, twee, drie]);
    expect(await screen.findByText(/opname\.m4a/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /bestand opnieuw proberen/i }));
    await waitFor(() => expect(mocked.uploadMedia).toHaveBeenCalledTimes(4));
    expect(mocked.uploadMedia.mock.calls[3][1]).toBe(twee);
  });

  it('laat niet meer dan 10 bestanden toe', async () => {
    const user = userEvent.setup();
    toon();
    const elf = Array.from({ length: 11 }, (_, i) => new File([new Uint8Array([0xff, 0xd8, i])], `f${i}.jpg`, { type: 'image/jpeg' }));
    await user.upload(screen.getByLabelText(/foto, geluid of document kiezen/i), elf);
    expect(screen.getAllByRole('button', { name: /verwijderen/i })).toHaveLength(10);
    expect(screen.getByRole('alert')).toHaveTextContent(/maximaal 10 bestanden/i);
    expect(screen.queryByLabelText(/nog een bestand toevoegen/i)).not.toBeInTheDocument();
  });

  it('gaat terug naar stap 1 als de inlog is verlopen, met behoud van het concept', async () => {
    mocked.submitContent.mockRejectedValue(new Error('API Error [401]: Unauthorized'));
    const user = userEvent.setup();
    toon();
    await vulVerplicht(user);
    await user.click(screen.getByRole('button', { name: /verstuur naar het erfgoedarchief/i }));

    expect(await screen.findByText(/stap 1: uw e-mailadres/i)).toBeInTheDocument();
    expect(mocked.clearAuthToken).toHaveBeenCalled();
    expect(localStorage.getItem('hlm_verhaal_concept')).toContain('Oma in Paramaribo');
  });

  it('heeft geen axe-schendingen', async () => {
    const { container } = toon();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('Bestandscontrole', () => {
  const maak = (naam: string, type: string, grootte = 10) => {
    const f = new File([new Uint8Array(1)], naam, { type });
    Object.defineProperty(f, 'size', { value: grootte });
    return f;
  };

  it('accepteert foto, m4a-opname en pdf', () => {
    expect(controleerBestand(maak('a.jpg', 'image/jpeg'))).toBeNull();
    expect(controleerBestand(maak('opname.m4a', 'audio/x-m4a'))).toBeNull();
    expect(controleerBestand(maak('brief.pdf', 'application/pdf'))).toBeNull();
    expect(controleerBestand(maak('IMG_0001.MOV', 'video/quicktime'))).toBeNull();
  });

  it('weigert HEIC, te grote en onbekende bestanden met uitleg', () => {
    expect(controleerBestand(maak('IMG_1.HEIC', 'image/heic'))).toMatch(/HEIC/);
    expect(controleerBestand(maak('groot.jpg', 'image/jpeg', MAX_BESTAND_BYTES + 1))).toMatch(/50 MB/);
    expect(controleerBestand(maak('app.exe', 'application/x-msdownload'))).toMatch(/niet opslaan/);
    expect(controleerBestand(maak('leeg.jpg', 'image/jpeg', 0))).toMatch(/leeg/);
  });
});

describe('Terug na inloggen: alleen binnen deze site', () => {
  beforeEach(() => localStorage.clear());

  it('bewaart een eigen pad en geeft het een keer terug', () => {
    onthoudNaInloggen('/uploaden');
    expect(neemNaInloggen()).toBe('/uploaden');
    expect(neemNaInloggen()).toBeNull();
  });

  it.each(['//kwaad.example', 'https://kwaad.example', '/\\kwaad.example', 'javascript:alert(1)'])(
    'weigert %s',
    (pad) => {
      onthoudNaInloggen(pad);
      expect(neemNaInloggen()).toBeNull();
      localStorage.setItem(NA_INLOGGEN_SLEUTEL, pad);
      expect(neemNaInloggen()).toBeNull();
    },
  );
});
