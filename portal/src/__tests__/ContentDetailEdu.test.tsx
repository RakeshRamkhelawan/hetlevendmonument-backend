import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ContentDetail } from '../pages/ContentDetail';
import { api } from '../api/client';
import type { FoundationContentDetail } from '../types';

vi.mock('../api/client', () => ({
  api: {
    getContentDetail: vi.fn(),
    getEduContentDetail: vi.fn(),
    getLesmateriaalDetail: vi.fn(),
    getAuthToken: vi.fn(() => null),
    getMijnAntwoorden: vi.fn(() => Promise.resolve({ naam: null, antwoorden: {}, feedback: null, bijgewerkt_op: null, verwijderd_na: null })),
    slaAntwoordenOp: vi.fn(),
    getMediaUrl: vi.fn(() => ''),
    getMediaInfo: vi.fn(),
  },
}));

const werkblad: FoundationContentDetail = {
  id: 7,
  title: 'Werkblad groep 7-8, les 1: Schiedam, 1602',
  summary: 'Wie zie je op het uithangbord?',
  description: 'Wie zie je op het uithangbord?',
  body: '## Wat echt gebeurde\n- In 1602 werd de VOC opgericht.',
  category: 'educatie',
  location_name: null,
  lat: null,
  lng: null,
  created_at: '2026-11-02T10:00:00Z',
  updated_at: '2026-11-02T10:00:00Z',
  language: 'nl',
  visibility: 'edu',
  file_url: null,
  file_mime: null,
  file_size_bytes: null,
  content_type: 'educational_workbook',
  is_anonymous: false,
  creator_name: 'Het Levend Monument (redactie)',
  rights_confirmed: true,
  external_url: null,
  license: 'CC-BY-4.0',
  metadata: null,
  rejection_reason: null,
  ai_tagging_failed: false,
  moderation_score: null,
  tags: [],
  status: 'approved',
};

const toon = () =>
  render(
    <MemoryRouter initialEntries={['/item/7']}>
      <Routes>
        <Route path="/item/:id" element={<ContentDetail />} />
      </Routes>
    </MemoryRouter>,
  );

describe('ContentDetail: werkbladen uit de educatieve omgeving', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('haalt een werkblad via de klassessie op als het niet openbaar is', async () => {
    vi.mocked(api.getContentDetail).mockRejectedValue(new Error('API Error [404]: Not found'));
    vi.mocked(api.getEduContentDetail).mockResolvedValue(werkblad);
    toon();
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /Schiedam, 1602/ })).toBeInTheDocument();
    });
    expect(screen.getByRole('heading', { name: 'Wat echt gebeurde' })).toBeInTheDocument();
    expect(screen.getByText('Lesmateriaal')).toBeInTheDocument();
  });

  it('toont de foutmelding als er ook geen klassessie is', async () => {
    vi.mocked(api.getContentDetail).mockRejectedValue(new Error('API Error [404]: Not found'));
    vi.mocked(api.getEduContentDetail).mockRejectedValue(new Error('API Error [401]: geen sessie'));
    toon();
    await waitFor(() => {
      expect(screen.queryByRole('heading', { level: 1, name: /Schiedam, 1602/ })).not.toBeInTheDocument();
      expect(api.getEduContentDetail).toHaveBeenCalled();
    });
  });

  it('toont het antwoordformulier bij een werkblad met vragen in een klassessie', async () => {
    vi.mocked(api.getContentDetail).mockRejectedValue(new Error('API Error [404]: Not found'));
    vi.mocked(api.getEduContentDetail).mockResolvedValue({
      ...werkblad,
      metadata: { vragen: [{ sleutel: 'vraag-1', sectie: 'Vragen bij het verhaal', tekst: 'Hoe heet Kwaku echt?' }] },
    });
    toon();
    expect(await screen.findByRole('region', { name: 'Jouw antwoorden' })).toBeInTheDocument();
    expect(screen.getByLabelText('Hoe heet Kwaku echt?')).toBeInTheDocument();
  });

  it('een ingelogde docent opent een werkblad zonder klascode, zonder antwoordformulier', async () => {
    vi.mocked(api.getContentDetail).mockRejectedValue(new Error('API Error [404]: Not found'));
    vi.mocked(api.getEduContentDetail).mockRejectedValue(new Error('API Error [401]: geen sessie'));
    vi.mocked(api.getAuthToken).mockReturnValue('jwt');
    vi.mocked(api.getLesmateriaalDetail).mockResolvedValue({
      ...werkblad,
      metadata: { vragen: [{ sleutel: 'vraag-1', sectie: 'Vragen bij het verhaal', tekst: 'Hoe heet Kwaku echt?' }] },
    });
    toon();
    expect(await screen.findByRole('heading', { level: 1, name: /Schiedam, 1602/ })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Jouw antwoorden' })).not.toBeInTheDocument();
  });
});
