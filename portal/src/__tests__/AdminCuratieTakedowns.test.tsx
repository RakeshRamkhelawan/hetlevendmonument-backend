import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { AdminCuratie } from '../pages/AdminCuratie';
import { api } from '../api/client';
import type { TakedownListResponse } from '../types';

vi.mock('../api/client', () => ({
  api: {
    getCuratieQueue: vi.fn(),
    getCuratieAnalytics: vi.fn(),
    getPortalSettings: vi.fn(),
    updatePortalSettings: vi.fn(),
    approveContent: vi.fn(),
    rejectContent: vi.fn(),
    retagContent: vi.fn(),
    getCuratieTakedowns: vi.fn(),
    getCuratieTakedownDetail: vi.fn(),
    resolveCuratieTakedown: vi.fn(),
    restoreContent: vi.fn(),
    getTenantSlug: vi.fn(() => 'erfgoed'),
  },
}));

describe('FE-CUR-001: AdminCuratie Notice & Takedown Management', () => {
  const mockTakedowns: TakedownListResponse = {
    items: [
      {
        id: 10,
        content_id: 42,
        content_title: 'Historische Havenfoto 1920',
        content_type: 'artwork',
        content_status: 'approved',
        requester_name: 'Pieter Post',
        requester_email: 'pieter@example.com',
        legal_basis: 'Inbreuk op auteursrecht familiearchief',
        status: 'pending',
        resolution_note: null,
        resolved_at: null,
        created_at: '2026-09-15T10:00:00Z',
      },
      {
        id: 11,
        content_id: 43,
        content_title: 'Mijn Oorlogsverhaal',
        content_type: 'story',
        content_status: 'removed',
        requester_name: 'Anoniem',
        requester_email: 'claim@example.com',
        legal_basis: 'Privacy en AVG bezwaar',
        status: 'approved',
        resolution_note: 'Content offline gehaald conform NTD gedragscode.',
        resolved_at: '2026-09-15T11:00:00Z',
        created_at: '2026-09-14T09:00:00Z',
      },
    ],
    total: 2,
    page: 1,
    page_size: 20,
    status_filter: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (api.getCuratieQueue as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    (api.getCuratieAnalytics as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(null);
    (api.getCuratieTakedowns as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockTakedowns);
  });

  it('toont de Notice & Takedown tab en laadt binnengekomen meldingen', async () => {
    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const takedownTab = await screen.findByRole('tab', { name: /takedown/i });
    expect(takedownTab).toBeInTheDocument();
    fireEvent.click(takedownTab);

    await waitFor(() => {
      expect(api.getCuratieTakedowns).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText(/Historische Havenfoto 1920/i)).toBeInTheDocument();
    expect(screen.getByText(/Inbreuk op auteursrecht familiearchief/i)).toBeInTheDocument();
    expect(screen.getByText(/Pieter Post/i)).toBeInTheDocument();
  });

  it('kan filteren op meldingstatus (pending, approved, rejected, escalated)', async () => {
    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const takedownTab = await screen.findByRole('tab', { name: /takedown/i });
    fireEvent.click(takedownTab);

    await waitFor(() => {
      expect(api.getCuratieTakedowns).toHaveBeenCalledTimes(1);
    });

    const pendingFilterBtn = screen.getByRole('button', { name: /in behandeling/i });
    fireEvent.click(pendingFilterBtn);

    await waitFor(() => {
      expect(api.getCuratieTakedowns).toHaveBeenCalledWith({ status: 'pending' });
    });
  });

  it('opent afhandelingsmodal en valideert verplichte motivering', async () => {
    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const takedownTab = await screen.findByRole('tab', { name: /takedown/i });
    fireEvent.click(takedownTab);

    const actionBtn = await screen.findByRole('button', { name: /beoordelen|afhandelen/i });
    fireEvent.click(actionBtn);

    // Modal moet zichtbaar zijn
    expect(await screen.findByText(/Melding Beoordelen/i)).toBeInTheDocument();

    // Versturen zonder motivering
    const submitBtn = screen.getByRole('button', { name: /besluit definitief toepassen/i });
    fireEvent.click(submitBtn);

    expect(await screen.findByText(/vul een geldige motivering in/i)).toBeInTheDocument();
    expect(api.resolveCuratieTakedown).not.toHaveBeenCalled();
  });

  it('verwerkt een toewijzing succesvol en werkt de melding bij', async () => {
    (api.resolveCuratieTakedown as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 10,
      content_id: 42,
      status: 'approved',
      content_status: 'removed',
      resolution_note: 'Auteursrechtclaim geverifieerd; content offline gehaald.',
      resolved_at: '2026-09-15T12:00:00Z',
      message: 'Notice & Takedown melding succesvol afgehandeld.',
    });

    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const takedownTab = await screen.findByRole('tab', { name: /takedown/i });
    fireEvent.click(takedownTab);

    const actionBtn = await screen.findByRole('button', { name: /beoordelen|afhandelen/i });
    fireEvent.click(actionBtn);

    const textarea = screen.getByLabelText(/motivering/i);
    fireEvent.change(textarea, {
      target: { value: 'Auteursrechtclaim geverifieerd; content offline gehaald.' },
    });

    const submitBtn = screen.getByRole('button', { name: /besluit definitief toepassen/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.resolveCuratieTakedown).toHaveBeenCalledWith(10, {
        status: 'approved',
        resolution_note: 'Auteursrechtclaim geverifieerd; content offline gehaald.',
        notify_requester: true,
      });
    });

    expect(await screen.findByText(/succesvol afgehandeld/i)).toBeInTheDocument();
  });

  it('voldoet aan WCAG 2.1 AA toegankelijkheidsrichtlijnen', async () => {
    const { container } = render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

    const takedownTab = await screen.findByRole('tab', { name: /takedown/i });
    fireEvent.click(takedownTab);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
