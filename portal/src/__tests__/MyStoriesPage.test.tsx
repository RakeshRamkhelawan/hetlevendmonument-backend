import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MyStories } from '../pages/MyStories';
import { api } from '../api/client';

describe('MyStories Page (WI-8, WI-10)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('toont vriendelijke lege toestand wanneer er nog geen inzendingen zijn', async () => {
    vi.spyOn(api, 'getMySubmissions').mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });

    render(
      <MemoryRouter>
        <MyStories />
      </MemoryRouter>
    );

    expect(screen.getByText('Uw inzendingen worden geladen...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Nog geen inzendingen')).toBeInTheDocument();
    });

    expect(screen.getByText('Deel uw eerste verhaal')).toBeInTheDocument();
  });

  it('toont ingezonden verhalen met juiste statusbadges', async () => {
    vi.spyOn(api, 'getMySubmissions').mockResolvedValueOnce({
      items: [
        {
          id: 101,
          title: 'Mijn herinnering aan de plantage',
          summary: 'Een verhaal over...',
          creator_name: 'Anoniem',
          is_anonymous: true,
          language: 'nl',
          content_type: 'story',
          status: 'pending',
          visibility: 'public',
          file_url: null,
          file_mime: null,
          file_size_bytes: null,
          lat: 5.8,
          lng: -55.2,
          location_name: 'Paramaribo',
          category: 'verhalen',
          created_at: '2026-09-16T10:00:00Z',
          updated_at: '2026-09-16T10:00:00Z',
        },
        {
          id: 102,
          title: 'Historische foto markt',
          summary: 'Foto uit 1970...',
          creator_name: 'Jan',
          is_anonymous: false,
          language: 'nl',
          content_type: 'image',
          status: 'approved',
          visibility: 'public',
          file_url: 'https://example.com/foto.jpg',
          file_mime: 'image/jpeg',
          file_size_bytes: 1024,
          lat: null,
          lng: null,
          location_name: 'Amsterdam',
          category: 'archief',
          created_at: '2026-09-15T12:00:00Z',
          updated_at: '2026-09-15T12:00:00Z',
        },
      ],
      total: 2,
      page: 1,
      page_size: 20,
    });

    render(
      <MemoryRouter>
        <MyStories />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Mijn herinnering aan de plantage')).toBeInTheDocument();
      expect(screen.getByText('Historische foto markt')).toBeInTheDocument();
    });

    expect(screen.getByText('In behandeling bij de redactie')).toBeInTheDocument();
    expect(screen.getByText('Goedgekeurd & Gepubliceerd')).toBeInTheDocument();
    expect(screen.getByText('Bekijk op platform')).toBeInTheDocument();
  });
});
