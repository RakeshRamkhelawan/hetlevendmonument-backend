/**
 * BE-EP-057: extra bestanden op de verhaalpagina, en het bekijken van een inzending die nog
 * niet openbaar is (curator of inzender).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { ExtraBestanden, HoofdMedia, isBeveiligd } from '../components/VerhaalMedia';
import { api } from '../api/client';
import type { FoundationContentDetail } from '../types';

vi.mock('../api/client', () => ({
  api: {
    getMediaUrl: vi.fn((id: number, o?: { stream?: boolean }) => `/media/${id}${o?.stream ? '?stream' : ''}`),
    getBestandMediaUrl: vi.fn((id: number, b: number, o?: { stream?: boolean }) => `/media/${id}/${b}${o?.stream ? '?stream' : ''}`),
    getMediaInfo: vi.fn(),
    getBestandMediaInfo: vi.fn(),
  },
}));

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const verhaal = (status: string): FoundationContentDetail =>
  ({
    id: 5,
    title: 'Oma in Paramaribo',
    status,
    content_type: 'story',
    file_url: 'x',
    file_mime: 'image/jpeg',
    bestanden: [
      { id: 900, volgorde: 2, file_mime: 'image/png', file_size_bytes: 10 },
      { id: 901, volgorde: 3, file_mime: 'audio/mp4', file_size_bytes: 10 },
      { id: 902, volgorde: 4, file_mime: 'application/pdf', file_size_bytes: 10 },
    ],
  }) as unknown as FoundationContentDetail;

beforeEach(() => {
  vi.clearAllMocks();
  mocked.getMediaInfo.mockResolvedValue({ url: 'https://sas/hoofd' });
  mocked.getBestandMediaInfo.mockImplementation(async (_id: number, b: number) => ({ url: `https://sas/${b}` }));
});

describe('isBeveiligd', () => {
  it('alleen niet-openbare statussen', () => {
    expect(isBeveiligd('pending')).toBe(true);
    expect(isBeveiligd('rejected')).toBe(true);
    expect(isBeveiligd('removed')).toBe(true);
    expect(isBeveiligd('approved')).toBe(false);
    expect(isBeveiligd(undefined)).toBe(false);
  });
});

describe('Openbaar verhaal', () => {
  it('toont de extra bestanden met de directe URL, op volgorde, zonder token-aanvraag', () => {
    render(<ExtraBestanden content={verhaal('approved')} beveiligd={false} />);
    expect(screen.getByAltText(/afbeelding 2 bij/i)).toHaveAttribute('src', '/media/5/900');
    expect(screen.getByLabelText(/geluidsopname 3 bij/i)).toHaveAttribute('src', '/media/5/901?stream');
    expect(screen.getByRole('link', { name: /document 4 openen/i })).toHaveAttribute('href', '/media/5/902');
    expect(mocked.getBestandMediaInfo).not.toHaveBeenCalled();
  });

  it('toont niets zonder extra bestanden', () => {
    const { container } = render(<ExtraBestanden content={{ ...verhaal('approved'), bestanden: [] }} beveiligd={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('heeft geen axe-schendingen', async () => {
    const { container } = render(<ExtraBestanden content={verhaal('approved')} beveiligd={false} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('Inzending die nog niet openbaar is', () => {
  it('haalt voor elk bestand eerst met het token een tijdelijke URL op', async () => {
    render(
      <>
        <HoofdMedia content={verhaal('pending')} beveiligd />
        <ExtraBestanden content={verhaal('pending')} beveiligd />
      </>,
    );
    await waitFor(() => expect(screen.getByAltText(/afbeelding 2 bij/i)).toHaveAttribute('src', 'https://sas/900'));
    expect(screen.getByAltText(/historische afbeelding/i)).toHaveAttribute('src', 'https://sas/hoofd');
    expect(mocked.getMediaInfo).toHaveBeenCalledWith(5);
    expect(mocked.getBestandMediaInfo).toHaveBeenCalledTimes(3);
  });

  it('toont geen bestand als het ophalen mislukt', async () => {
    mocked.getBestandMediaInfo.mockRejectedValue(new Error('404'));
    render(<ExtraBestanden content={verhaal('pending')} beveiligd />);
    await waitFor(() => expect(mocked.getBestandMediaInfo).toHaveBeenCalled());
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});
