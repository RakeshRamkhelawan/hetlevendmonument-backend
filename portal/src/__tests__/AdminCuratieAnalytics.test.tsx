import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminCuratie } from '../pages/AdminCuratie';
import { api } from '../api/client';
import type { CurationAnalyticsResponse } from '../types';

vi.mock('../api/client', () => ({
  api: {
    getCuratieQueue: vi.fn(),
    getCuratieAnalytics: vi.fn(),
    approveContent: vi.fn(),
    rejectContent: vi.fn(),
    retagContent: vi.fn(),
    getTenantSlug: vi.fn(() => 'erfgoed'),
  },
}));

describe('FE-ANL-001: AdminCuratie Analytics & KPI Dashboard', () => {
  const mockAnalytics: CurationAnalyticsResponse = {
    status_counts: {
      pending: 4,
      approved: 18,
      rejected: 2,
    },
    total_content: 24,
    average_moderation_seconds: 3600, // 60 minuten
    tag_distribution: [
      {
        tag: 'Klederdracht',
        tag_type: 'THEME',
        count: 12,
        average_confidence: 0.92,
      },
      {
        tag: 'Paramaribo',
        tag_type: 'LOCATION',
        count: 7,
        average_confidence: 0.85,
      },
    ],
    newsletter: {
      total_subscribers: 85,
      verified_subscribers: 80,
    },
    education: {
      active_codes: 3,
      total_codes: 6,
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (api.getCuratieQueue as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    (api.getCuratieAnalytics as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockAnalytics);
  });

  it('haalt analytics op en rendert de KPI statistieken', async () => {
    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(api.getCuratieAnalytics).toHaveBeenCalledTimes(1);
    });

    const analyticsTab = await screen.findByRole('tab', { name: /kpi analytics & nde/i });
    fireEvent.click(analyticsTab);

    // Controleer aanwezigheid van KPI getallen
    expect(await screen.findByText('4')).toBeInTheDocument(); // pending count
    expect(screen.getByText('18')).toBeInTheDocument(); // approved count
    expect(screen.getByText('2')).toBeInTheDocument(); // rejected count
    expect(screen.getByText(/60 m|1.0 u|1 u/i)).toBeInTheDocument(); // average duration
  });

  it('toont AI tag distributie na openklappen van de accordion', async () => {
    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const analyticsTab = await screen.findByRole('tab', { name: /kpi analytics & nde/i });
    fireEvent.click(analyticsTab);

    // Wacht tot de accordion knop zichtbaar is
    const accordionBtn = await screen.findByRole('button', {
      name: /AI NDE-Thesaurus Distributie/i,
    });
    expect(accordionBtn).toBeInTheDocument();

    // Klik om uit te klappen
    fireEvent.click(accordionBtn);

    expect(await screen.findByText('Klederdracht')).toBeInTheDocument();
    expect(screen.getByText('Paramaribo')).toBeInTheDocument();
    expect(screen.getByText(/92%/i)).toBeInTheDocument(); // 0.92 = 92%
    expect(screen.getByText(/85%/i)).toBeInTheDocument(); // 0.85 = 85%
  });

  it('blijft functioneren als analytics ophalen mislukt', async () => {
    (api.getCuratieAnalytics as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Network error')
    );

    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(api.getCuratieQueue).toHaveBeenCalled();
    });

    // Pagina crasht niet, queue heading is nog steeds aanwezig
    expect(screen.getByRole('heading', { name: /curatie wachtrij/i })).toBeInTheDocument();
  });
});

