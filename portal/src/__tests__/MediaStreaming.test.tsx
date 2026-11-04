import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ContentDetail } from '../pages/ContentDetail';
import { api } from '../api/client';
import type { FoundationContentDetail } from '../types';

// Mock API client
vi.mock('../api/client', () => {
  const getMediaUrlMock = vi.fn((contentId: number | string, options?: { download?: boolean; stream?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.stream) params.set('stream', 'true');
    else params.set('redirect', 'true');
    if (options?.download) params.set('download', 'true');
    return `/api/v1/default/foundation/content/${contentId}/media?${params.toString()}`;
  });

  return {
    api: {
      getContentDetail: vi.fn(),
      getMediaUrl: getMediaUrlMock,
      getMediaInfo: vi.fn(),
    },
  };
});

describe('BE-EP-052: Media Streaming & Secure Download Client/UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockVideoContent: FoundationContentDetail = {
    id: 42,
    title: 'Historische Beelden Slag om Den Haag',
    summary: 'Zeldzame filmopnames uit het archief',
    description: 'Volledige beschrijving van de video.',
    body: 'Volledig transcript van de video-opname.',
    category: 'Film & Video',
    location_name: 'Den Haag',
    lat: 52.0705,
    lng: 4.3007,
    created_at: '2026-09-14T10:00:00Z',
    updated_at: '2026-09-14T10:00:00Z',
    language: 'nl',
    visibility: 'public',
    file_url: '/uploads/foundation/1/video.mp4',
    file_mime: 'video/mp4',
    file_size_bytes: 10485760,
    content_type: 'video',
    is_anonymous: false,
    creator_name: 'Stadsarchief',
    rights_confirmed: true,
    external_url: null,
    license: 'CC-BY-4.0',
    metadata: null,
    rejection_reason: null,
    ai_tagging_failed: false,
    moderation_score: 0.95,
    tags: [],
    status: 'approved',
  };

  const mockAudioContent: FoundationContentDetail = {
    id: 43,
    title: 'Mondeling Getuigenis Migratie',
    summary: 'Gesproken herinneringen aan de oversteek',
    description: 'Audio-opname van het interview.',
    body: 'Schriftelijk transcript van het gesprek.',
    category: 'Mondelinge Geschiedenis',
    location_name: 'Rotterdam',
    lat: 51.9225,
    lng: 4.4792,
    created_at: '2026-09-14T11:00:00Z',
    updated_at: '2026-09-14T11:00:00Z',
    language: 'nl',
    visibility: 'public',
    file_url: '/uploads/foundation/1/audio.mp3',
    file_mime: 'audio/mpeg',
    file_size_bytes: 5242880,
    content_type: 'audio',
    is_anonymous: false,
    creator_name: 'Erfgoeddrager',
    rights_confirmed: true,
    external_url: null,
    license: 'CC-BY-4.0',
    metadata: null,
    rejection_reason: null,
    ai_tagging_failed: false,
    moderation_score: 0.95,
    tags: [],
    status: 'approved',
  };

  it('genereert de juiste media stream en download URLs via api.getMediaUrl', () => {
    const streamUrl = api.getMediaUrl(42, { stream: true });
    expect(streamUrl).toContain('/content/42/media?stream=true');

    const downloadUrl = api.getMediaUrl(42, { download: true });
    expect(downloadUrl).toContain('/content/42/media?redirect=true&download=true');
  });

  it('rendert video player en veilige download-knop voor video content', async () => {
    vi.mocked(api.getContentDetail).mockResolvedValue(mockVideoContent);

    render(
      <MemoryRouter initialEntries={['/verhaal/42']}>
        <Routes>
          <Route path="/verhaal/:id" element={<ContentDetail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /Historische Beelden Slag om Den Haag/i })).toBeInTheDocument();
    });

    // Check video element exists with stream URL
    const video = document.querySelector('video');
    expect(video).toBeInTheDocument();
    expect(video?.getAttribute('src')).toContain('/content/42/media?stream=true');

    // Check download button exists with download URL
    const downloadLink = screen.getByRole('link', { name: /download/i });
    expect(downloadLink).toBeInTheDocument();
    expect(downloadLink.getAttribute('href')).toContain('download=true');
  });

  it('rendert audio player en veilige download-knop voor audio content', async () => {
    vi.mocked(api.getContentDetail).mockResolvedValue(mockAudioContent);

    render(
      <MemoryRouter initialEntries={['/verhaal/43']}>
        <Routes>
          <Route path="/verhaal/:id" element={<ContentDetail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /Mondeling Getuigenis Migratie/i })).toBeInTheDocument();
    });

    // Check audio element exists with stream URL
    const audio = document.querySelector('audio');
    expect(audio).toBeInTheDocument();
    expect(audio?.getAttribute('src')).toContain('/content/43/media?stream=true');

    // Check download button exists
    const downloadLink = screen.getByRole('link', { name: /download/i });
    expect(downloadLink).toBeInTheDocument();
    expect(downloadLink.getAttribute('href')).toContain('download=true');
  });
});
