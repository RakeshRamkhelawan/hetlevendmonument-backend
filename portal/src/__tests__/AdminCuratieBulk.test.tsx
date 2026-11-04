import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { AdminCuratie } from '../pages/AdminCuratie';
import { api } from '../api/client';
import type { CuratieQueueResponse, BulkModerationResponse } from '../types';

vi.mock('../api/client', () => ({
  api: {
    getCuratieQueue: vi.fn(),
    getCuratieAnalytics: vi.fn(),
    getPortalSettings: vi.fn(),
    updatePortalSettings: vi.fn(),
    approveContent: vi.fn(),
    rejectContent: vi.fn(),
    bulkApproveContent: vi.fn(),
    bulkRejectContent: vi.fn(),
    retagContent: vi.fn(),
    getCuratieTakedowns: vi.fn(),
    getCuratieTakedownDetail: vi.fn(),
    resolveCuratieTakedown: vi.fn(),
    restoreContent: vi.fn(),
    getTenantSlug: vi.fn(() => 'erfgoed'),
  },
}));

describe('FE-CUR-002: AdminCuratie Bulk Moderatie & Multi-Select', () => {
  const mockQueue: CuratieQueueResponse = {
    items: [
      {
        id: 101,
        title: 'Verhaal over Oude Haven',
        summary: 'Een historische beschrijving van de oude haven.',
        creator_name: 'Jan Jansen',
        is_anonymous: false,
        content_type: 'story',
        status: 'pending' as any,
        created_at: '2026-09-15T10:00:00Z',
        rejection_reason: null,
        ai_tagging_failed: false,
        moderation_score: 0.95,
        tags: [],
      },
      {
        id: 102,
        title: 'Historisch Schilderij Marktplein',
        summary: 'Schilderij van het marktplein in 1910.',
        creator_name: 'Maria Bakker',
        is_anonymous: false,
        content_type: 'artwork',
        status: 'pending' as any,
        created_at: '2026-09-15T10:30:00Z',
        rejection_reason: null,
        ai_tagging_failed: false,
        moderation_score: 0.88,
        tags: [],
      },
      {
        id: 103,
        title: 'Audio-opname Straatlied',
        summary: 'Gezongen volkslied uit 1930.',
        creator_name: null,
        is_anonymous: true,
        content_type: 'audio',
        status: 'pending' as any,
        created_at: '2026-09-15T11:00:00Z',
        rejection_reason: null,
        ai_tagging_failed: false,
        moderation_score: 0.72,
        tags: [],
      },
    ],
    total: 3,
    page: 1,
    page_size: 20,
  };

  const mockAnalytics = {
    status_counts: { pending: 3, approved: 10, rejected: 2 },
    total_content: 15,
    average_moderation_seconds: 300,
    tag_distribution: [],
    newsletter: { total_subscribers: 50, verified_subscribers: 45 },
    education: { active_codes: 5, total_codes: 10 },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getCuratieQueue).mockResolvedValue(mockQueue);
    vi.mocked(api.getCuratieAnalytics).mockResolvedValue(mockAnalytics);
  });

  const renderComponent = () =>
    render(
      <MemoryRouter>
        <AdminCuratie />
      </MemoryRouter>
    );

  it('toont selectievakjes per item en een "Alles selecteren" optie in de wachtrij', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Verhaal over Oude Haven')).toBeInTheDocument();
    });

    // Header "Alles selecteren"
    const selectAllCheckbox = screen.getByLabelText('Selecteer alle verhalen');
    expect(selectAllCheckbox).toBeInTheDocument();
    expect(selectAllCheckbox).not.toBeChecked();

    // Checkbox per item
    const item1Checkbox = screen.getByLabelText('Selecteer item: Verhaal over Oude Haven');
    const item2Checkbox = screen.getByLabelText('Selecteer item: Historisch Schilderij Marktplein');
    expect(item1Checkbox).toBeInTheDocument();
    expect(item2Checkbox).toBeInTheDocument();
    expect(item1Checkbox).not.toBeChecked();
  });

  it('toont de zwevende bulk-actiebalk zodra één of meer items zijn geselecteerd', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Verhaal over Oude Haven')).toBeInTheDocument();
    });

    // Toolbar is initieel niet aanwezig
    expect(screen.queryByRole('toolbar', { name: 'Bulk acties' })).not.toBeInTheDocument();

    // Selecteer item 1
    const item1Checkbox = screen.getByLabelText('Selecteer item: Verhaal over Oude Haven');
    fireEvent.click(item1Checkbox);

    // Toolbar verschijnt met status en actieknoppen
    const toolbar = screen.getByRole('toolbar', { name: 'Bulk acties' });
    expect(toolbar).toBeInTheDocument();
    expect(screen.getByText(/1 van de 3 item\(s\) geselecteerd/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Goedkeuren \(1\)/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Afwijzen \(1\)/i })).toBeInTheDocument();
  });

  it('togglet alle items bij het klikken op "Alles selecteren"', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Verhaal over Oude Haven')).toBeInTheDocument();
    });

    const selectAllCheckbox = screen.getByLabelText('Selecteer alle verhalen');
    fireEvent.click(selectAllCheckbox);

    // Nu moeten alle 3 de checkboxes aangevinkt zijn
    expect(selectAllCheckbox).toBeChecked();
    expect(screen.getByLabelText('Selecteer item: Verhaal over Oude Haven')).toBeChecked();
    expect(screen.getByLabelText('Selecteer item: Historisch Schilderij Marktplein')).toBeChecked();
    expect(screen.getByLabelText('Selecteer item: Audio-opname Straatlied')).toBeChecked();
    expect(screen.getByText(/3 van de 3 item\(s\) geselecteerd/i)).toBeInTheDocument();

    // Klik nogmaals om alles te deselecteren
    fireEvent.click(selectAllCheckbox);
    expect(selectAllCheckbox).not.toBeChecked();
    expect(screen.queryByRole('toolbar', { name: 'Bulk acties' })).not.toBeInTheDocument();
  });

  it('voert bulk-goedkeuring uit via api.bulkApproveContent en verwijdert goedgekeurde items', async () => {
    const mockApproveResponse: BulkModerationResponse = {
      total_requested: 2,
      processed_count: 2,
      success_ids: [101, 102],
      failed_items: [],
      message: '2 item(s) succesvol goedgekeurd.',
    };
    vi.mocked(api.bulkApproveContent).mockResolvedValue(mockApproveResponse);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Verhaal over Oude Haven')).toBeInTheDocument();
    });

    // Selecteer item 1 en 2
    fireEvent.click(screen.getByLabelText('Selecteer item: Verhaal over Oude Haven'));
    fireEvent.click(screen.getByLabelText('Selecteer item: Historisch Schilderij Marktplein'));

    const approveButton = screen.getByRole('button', { name: /Goedkeuren \(2\)/i });
    fireEvent.click(approveButton);

    await waitFor(() => {
      expect(api.bulkApproveContent).toHaveBeenCalledWith([101, 102]);
    });

    // Items 101 en 102 zijn uit de lijst verdwenen
    await waitFor(() => {
      expect(screen.queryByText('Verhaal over Oude Haven')).not.toBeInTheDocument();
      expect(screen.queryByText('Historisch Schilderij Marktplein')).not.toBeInTheDocument();
      expect(screen.getByText('Audio-opname Straatlied')).toBeInTheDocument();
    });

    expect(screen.getByText(/2 item\(s\) succesvol goedgekeurd en gepubliceerd!/i)).toBeInTheDocument();
  });

  it('opent de bulk-afwijsmodal, valideert DSA Art. 17 motivering en roept api.bulkRejectContent aan', async () => {
    const mockRejectResponse: BulkModerationResponse = {
      total_requested: 2,
      processed_count: 2,
      success_ids: [101, 102],
      failed_items: [],
      message: '2 item(s) afgewezen.',
    };
    vi.mocked(api.bulkRejectContent).mockResolvedValue(mockRejectResponse);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Verhaal over Oude Haven')).toBeInTheDocument();
    });

    // Selecteer item 1 en 2
    fireEvent.click(screen.getByLabelText('Selecteer item: Verhaal over Oude Haven'));
    fireEvent.click(screen.getByLabelText('Selecteer item: Historisch Schilderij Marktplein'));

    // Klik op Afwijzen in bulk toolbar
    const rejectButton = screen.getByRole('button', { name: /Afwijzen \(2\)/i });
    fireEvent.click(rejectButton);

    // Modal is geopend
    const modal = screen.getByRole('dialog');
    expect(modal).toBeInTheDocument();
    expect(screen.getByText(/Bulk Afwijzen \(2 items\)/i)).toBeInTheDocument();

    const textarea = screen.getByLabelText(/Gemeenschappelijke motivering/i);
    const submitBtn = screen.getByRole('button', { name: /Bevestig Afwijzing \(2\)/i });

    // Submit knop is disabled bij lege/te korte tekst
    expect(submitBtn).toBeDisabled();

    // Typ geldige motivering conform DSA Art. 17
    fireEvent.change(textarea, {
      target: { value: 'Inzendingen bevatten commerciële uitingen en schenden het collectiebeleid.' },
    });
    expect(submitBtn).not.toBeDisabled();

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.bulkRejectContent).toHaveBeenCalledWith(
        [101, 102],
        'Inzendingen bevatten commerciële uitingen en schenden het collectiebeleid.'
      );
    });

    // Modal is gesloten en items zijn verwijderd
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.queryByText('Verhaal over Oude Haven')).not.toBeInTheDocument();
    });
  });

  it('voldoet aan WCAG 2.1 AA toegankelijkheidseisen (0 a11y schendingen)', async () => {
    const { container } = renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Verhaal over Oude Haven')).toBeInTheDocument();
    });

    // Selecteer een item zodat de floating toolbar gerenderd wordt
    fireEvent.click(screen.getByLabelText('Selecteer item: Verhaal over Oude Haven'));

    const results = await axe(container);
    if (results.violations.length > 0) {
      console.log('AXE VIOLATIONS:', JSON.stringify(results.violations.map(v => ({ id: v.id, impact: v.impact, description: v.description, nodes: v.nodes.map(n => n.html) })), null, 2));
    }
    expect(results.violations).toHaveLength(0);
  });
});
