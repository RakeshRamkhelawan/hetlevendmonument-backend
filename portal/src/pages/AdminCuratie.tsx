import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  Shield,
  Check,
  X,
  RefreshCw,
  Eye,
  AlertTriangle,
  Clock,
  Sparkles,
  Users,
  GraduationCap,
  ChevronDown,
  ChevronUp,
  Palette,
  Sliders,
  Save,
  ShieldAlert,
  AlertCircle,
  Archive,
} from 'lucide-react';
import { api } from '../api/client';
import { ArchiefExportPanel } from '../components/ArchiefExportPanel';
import { DocentenBeheerPanel } from '../components/DocentenBeheerPanel';
import { TagBadge } from '../components/TagBadge';
import type {
  CuratieQueueItem,
  CurationAnalyticsResponse,
  PortalSettingsUpdateRequest,
  TakedownListItem,
} from '../types';

export const AdminCuratie: React.FC = () => {
  const [activeMainTab, setActiveMainTab] = useState<'curatie' | 'analytics' | 'archief' | 'settings' | 'takedowns' | 'docenten'>('curatie');
  const user = (() => {
    try {
      const u = localStorage.getItem('portal_user');
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  })();
  const userRole = (user?.role || (user === null ? 'admin' : 'curator')).toLowerCase();
  const isAdmin = userRole === 'admin';

  const getTabTitle = () => {
    switch (activeMainTab) {
      case 'analytics':
        return 'KPI Analytics & NDE';
      case 'settings':
        return 'Branding & Portaalinstellingen';
      case 'takedowns':
        return 'Notice & Takedown Moderatie';
      case 'archief':
        return 'Archief-export';
      case 'docenten':
        return 'Docenten';
      case 'curatie':
      default:
        return 'Curatie Wachtrij';
    }
  };

  useEffect(() => {
    if (!isAdmin && (activeMainTab === 'settings' || activeMainTab === 'takedowns')) {
      setActiveMainTab('curatie');
    }
    document.title = `${getTabTitle()} | Het Levend Monument`;
  }, [activeMainTab, isAdmin]);

  const [items, setItems] = useState<CuratieQueueItem[]>([]);
  const [analytics, setAnalytics] = useState<CurationAnalyticsResponse | null>(null);
  const [showTagDist, setShowTagDist] = useState(false);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<'pending' | 'approved' | 'rejected'>('pending');
  const [actionInProgress, setActionInProgress] = useState<number | null>(null);
  const [rejectingItem, setRejectingItem] = useState<CuratieQueueItem | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [notification, setNotification] = useState<string | null>(null);

  // Bulk Moderatie state (FE-CUR-002)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkActionInProgress, setBulkActionInProgress] = useState(false);
  const [bulkRejectModalOpen, setBulkRejectModalOpen] = useState(false);
  const [bulkRejectReason, setBulkRejectReason] = useState('');
  const [bulkRejectError, setBulkRejectError] = useState<string | null>(null);
  const selectAllCheckboxRef = useRef<HTMLInputElement>(null);

  // Notice & Takedown state (FE-CUR-001)
  const [takedowns, setTakedowns] = useState<TakedownListItem[]>([]);
  const [takedownLoading, setTakedownLoading] = useState(false);
  const [takedownStatusFilter, setTakedownStatusFilter] = useState<
    'all' | 'pending' | 'approved' | 'rejected' | 'escalated'
  >('all');
  const [selectedTakedown, setSelectedTakedown] = useState<TakedownListItem | null>(null);
  const [resolveOutcome, setResolveOutcome] = useState<'approved' | 'rejected' | 'escalated'>('approved');
  const [resolveNote, setResolveNote] = useState('');
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [resolveInProgress, setResolveInProgress] = useState(false);
  const [resolvingModalOpen, setResolvingModalOpen] = useState(false);

  // White-label settings state (FE-PAGE-014)
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState<{ success: boolean; message: string } | null>(null);
  const [settingsForm, setSettingsForm] = useState<PortalSettingsUpdateRequest>({
    platform_name_nl: '',
    platform_name_en: '',
    primary_color: '#1a2f45',
    accent_color: '#e8b86d',
    logo_url: '',
    favicon_url: '',
    guidelines_nl: '',
    guidelines_en: '',
    about_nl: '',
    about_en: '',
    contact_email: '',
  });

  const [queueError, setQueueError] = useState<string | null>(null);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [takedownError, setTakedownError] = useState<string | null>(null);

  const fetchAnalytics = async () => {
    setAnalyticsError(null);
    try {
      const data = await api.getCuratieAnalytics();
      setAnalytics(data);
    } catch (err) {
      console.error('Fout bij ophalen curatie analytics:', err);
      setAnalyticsError(err instanceof Error ? err.message : 'Fout bij ophalen analytics.');
    }
  };

  const fetchQueue = async () => {
    setLoading(true);
    setQueueError(null);
    try {
      const res = await api.getCuratieQueue({ status: statusFilter });
      setItems(res.items || []);
    } catch (err) {
      console.error('Fout bij ophalen curatielijst:', err);
      setQueueError(err instanceof Error ? err.message : 'Fout bij ophalen curatiewachtrij.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
    fetchAnalytics();
  }, [statusFilter]);

  // Synchroniseer indeterminate state van "Selecteer alles" checkbox
  useEffect(() => {
    if (selectAllCheckboxRef.current) {
      const isIndeterminate = selectedIds.size > 0 && selectedIds.size < items.length;
      selectAllCheckboxRef.current.indeterminate = isIndeterminate;
    }
  }, [selectedIds, items.length]);

  // Reset selectie bij statusfilter wijziging
  useEffect(() => {
    setSelectedIds(new Set());
  }, [statusFilter]);

  // Toetsenbord shortcut: Escape sluit bulk modal of wist selectie
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (bulkRejectModalOpen) {
          setBulkRejectModalOpen(false);
        } else if (selectedIds.size > 0) {
          setSelectedIds(new Set());
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [bulkRejectModalOpen, selectedIds.size]);

  const fetchTakedowns = async () => {
    setTakedownLoading(true);
    setTakedownError(null);
    try {
      const res = await api.getCuratieTakedowns({
        status: takedownStatusFilter === 'all' ? undefined : takedownStatusFilter,
      });
      setTakedowns(res.items || []);
    } catch (err) {
      console.error('Fout bij ophalen takedowns:', err);
      setTakedownError(err instanceof Error ? err.message : 'Fout bij ophalen takedowns.');
    } finally {
      setTakedownLoading(false);
    }
  };

  useEffect(() => {
    if (activeMainTab === 'takedowns') {
      fetchTakedowns();
    }
  }, [takedownStatusFilter, activeMainTab]);

  const handleOpenResolveModal = (
    td: TakedownListItem,
    defaultOutcome: 'approved' | 'rejected' | 'escalated' = 'approved'
  ) => {
    setSelectedTakedown(td);
    setResolveOutcome(defaultOutcome);
    setResolveNote(td.resolution_note || '');
    setResolveError(null);
    setResolvingModalOpen(true);
  };

  const handleResolveSubmit = async () => {
    if (!selectedTakedown) return;
    if (!resolveNote.trim() || resolveNote.trim().length < 5) {
      setResolveError('Vul een geldige motivering in van minimaal 5 tekens.');
      return;
    }

    setResolveInProgress(true);
    setResolveError(null);
    try {
      const res = await api.resolveCuratieTakedown(selectedTakedown.id, {
        status: resolveOutcome,
        resolution_note: resolveNote.trim(),
        notify_requester: true,
      });
      setNotification(`Melding #${selectedTakedown.id} is succesvol afgehandeld (${res.status}).`);
      setResolvingModalOpen(false);
      setSelectedTakedown(null);
      setResolveNote('');
      fetchTakedowns();
    } catch (err: unknown) {
      setResolveError(err instanceof Error ? err.message : 'Fout bij verwerken van besluit.');
    } finally {
      setResolveInProgress(false);
    }
  };

  const handleRestoreContent = async (contentId: number) => {
    try {
      await api.restoreContent(contentId);
      setNotification(`Item #${contentId} is hersteld naar het archief.`);
      fetchTakedowns();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Fout bij herstellen van item.');
    }
  };

  const fetchSettings = async () => {
    setSettingsLoading(true);
    try {
      const data = await api.getPortalSettings();
      setSettingsForm({
        platform_name_nl: data.platform_name_nl || '',
        platform_name_en: data.platform_name_en || '',
        primary_color: data.primary_color || '#1a2f45',
        accent_color: data.accent_color || '#e8b86d',
        logo_url: data.logo_url || '',
        favicon_url: data.favicon_url || '',
        guidelines_nl: data.guidelines_nl || '',
        guidelines_en: data.guidelines_en || '',
        about_nl: data.about_nl || '',
        about_en: data.about_en || '',
        contact_email: data.contact_email || '',
      });
    } catch (err) {
      console.error('Fout bij ophalen portaalinstellingen:', err);
    } finally {
      setSettingsLoading(false);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSettingsSaving(true);
    setSettingsStatus(null);
    try {
      const updated = await api.updatePortalSettings(settingsForm);
      setSettingsStatus({
        success: true,
        message: 'Portaalinstellingen en white-label branding succesvol bijgewerkt!',
      });
      setSettingsForm({
        platform_name_nl: updated.platform_name_nl,
        platform_name_en: updated.platform_name_en || '',
        primary_color: updated.primary_color,
        accent_color: updated.accent_color,
        logo_url: updated.logo_url || '',
        favicon_url: updated.favicon_url || '',
        guidelines_nl: updated.guidelines_nl || '',
        guidelines_en: updated.guidelines_en || '',
        about_nl: updated.about_nl || '',
        about_en: updated.about_en || '',
        contact_email: updated.contact_email || '',
      });
    } catch (err: unknown) {
      setSettingsStatus({
        success: false,
        message: err instanceof Error ? err.message : 'Fout bij opslaan van instellingen.',
      });
    } finally {
      setSettingsSaving(false);
    }
  };

  const handleApprove = async (id: number) => {
    setActionInProgress(id);
    try {
      await api.approveContent(id);
      setNotification(`Item #${id} is goedgekeurd en gepubliceerd!`);
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Fout bij goedkeuren.');
    } finally {
      setActionInProgress(null);
    }
  };

  const handleConfirmReject = async () => {
    if (!rejectingItem) return;
    setActionInProgress(rejectingItem.id);
    try {
      await api.rejectContent(rejectingItem.id, rejectReason);
      setNotification(`Item #${rejectingItem.id} is afgewezen.`);
      setItems((prev) => prev.filter((item) => item.id !== rejectingItem.id));
      setRejectingItem(null);
      setRejectReason('');
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Fout bij afwijzen.');
    } finally {
      setActionInProgress(null);
    }
  };

  const handleRetag = async (id: number) => {
    setActionInProgress(id);
    try {
      await api.retagContent(id);
      setNotification(`AI Her-tagging gestart voor item #${id}`);
      fetchQueue();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Fout bij her-taggen.');
    } finally {
      setActionInProgress(null);
    }
  };

  // Bulk Selection Handlers (FE-CUR-002)
  const handleToggleSelectAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map((i) => i.id)));
    }
  };

  const handleToggleSelectItem = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleClearSelection = () => {
    setSelectedIds(new Set());
  };

  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return;
    setBulkActionInProgress(true);
    try {
      const idsToApprove = Array.from(selectedIds);
      const res = await api.bulkApproveContent(idsToApprove);

      const successSet = new Set(res.success_ids);
      setItems((prev) => prev.filter((item) => !successSet.has(item.id)));
      setSelectedIds(new Set());

      let msg = `${res.success_ids.length} item(s) succesvol goedgekeurd en gepubliceerd!`;
      if (res.failed_items.length > 0) {
        msg += ` (${res.failed_items.length} item(s) overgeslagen)`;
      }
      setNotification(msg);
      fetchAnalytics();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Fout bij bulk goedkeuren.');
    } finally {
      setBulkActionInProgress(false);
    }
  };

  const handleOpenBulkRejectModal = () => {
    setBulkRejectReason('');
    setBulkRejectError(null);
    setBulkRejectModalOpen(true);
  };

  const handleConfirmBulkReject = async () => {
    if (!bulkRejectReason.trim() || bulkRejectReason.trim().length < 5) {
      setBulkRejectError('Vul een geldige motivering in van minimaal 5 tekens (DSA Art. 17).');
      return;
    }
    setBulkActionInProgress(true);
    setBulkRejectError(null);
    try {
      const idsToReject = Array.from(selectedIds);
      const res = await api.bulkRejectContent(idsToReject, bulkRejectReason.trim());

      const successSet = new Set(res.success_ids);
      setItems((prev) => prev.filter((item) => !successSet.has(item.id)));
      setSelectedIds(new Set());
      setBulkRejectModalOpen(false);
      setBulkRejectReason('');

      let msg = `${res.success_ids.length} item(s) afgewezen conform DSA Art. 17.`;
      if (res.failed_items.length > 0) {
        msg += ` (${res.failed_items.length} item(s) overgeslagen)`;
      }
      setNotification(msg);
      fetchAnalytics();
    } catch (err: unknown) {
      setBulkRejectError(err instanceof Error ? err.message : 'Fout bij bulk afwijzen.');
    } finally {
      setBulkActionInProgress(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-semibold uppercase tracking-wider mb-2">
              <Shield className="w-3.5 h-3.5 text-amber-800" />
              <span>
                Erfgoed Beheer &bull; Ingelogd als {user?.email || 'Medewerker'} ({isAdmin ? 'Administrator' : 'Curator'})
              </span>
            </div>
            <h1 className="font-serif text-3xl font-bold text-stone-900">{getTabTitle()}</h1>
            <p className="text-xs text-stone-500 mt-1">
              Beoordeel openbare inzendingen, controleer ethische standaarden en beheer erfgoedmetadata.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                fetchQueue();
                fetchAnalytics();
                if (activeMainTab === 'settings') {
                  fetchSettings();
                }
              }}
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl bg-white border border-stone-200 text-stone-700 hover:bg-stone-50 shadow-xs transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Verversen
            </button>
          </div>
        </div>

        {/* Global Notification Banner */}
        {notification && (
          <div
            role="status"
            className="mb-6 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs font-medium flex items-center justify-between shadow-xs"
          >
            <span>{notification}</span>
            <button onClick={() => setNotification(null)} className="text-amber-800 hover:underline text-xs">
              Sluiten
            </button>
          </div>
        )}

        {/* Main Navigation Tabs */}
        <div className="flex border-b border-stone-200 mb-8 space-x-6 text-sm" role="tablist" aria-label="Beheer secties">
          <button
            role="tab"
            aria-selected={activeMainTab === 'curatie'}
            onClick={() => setActiveMainTab('curatie')}
            className={`pb-3 font-semibold transition-colors flex items-center gap-2 relative ${
              activeMainTab === 'curatie' ? 'text-amber-800 border-b-2 border-amber-800' : 'text-stone-500 hover:text-stone-800'
            }`}
          >
            <Shield className="w-4 h-4" />
            <span>Curatie Wachtrij</span>
            {items.length > 0 && (
              <span className="bg-amber-100 text-amber-900 text-[11px] font-bold px-1.5 py-0.5 rounded-full">
                {items.length}
              </span>
            )}
          </button>

          <button
            role="tab"
            aria-selected={activeMainTab === 'analytics'}
            onClick={() => setActiveMainTab('analytics')}
            className={`pb-3 font-semibold transition-colors flex items-center gap-2 relative ${
              activeMainTab === 'analytics' ? 'text-amber-800 border-b-2 border-amber-800' : 'text-stone-500 hover:text-stone-800'
            }`}
          >
            <Sliders className="w-4 h-4" />
            <span>KPI Analytics &amp; NDE</span>
          </button>

          <button
            role="tab"
            aria-selected={activeMainTab === 'archief'}
            onClick={() => setActiveMainTab('archief')}
            className={`pb-3 font-semibold transition-colors flex items-center gap-2 relative ${
              activeMainTab === 'archief' ? 'text-amber-800 border-b-2 border-amber-800' : 'text-stone-500 hover:text-stone-800'
            }`}
          >
            <Archive className="w-4 h-4" />
            <span>Archief</span>
          </button>

          {isAdmin && (
            <>
              <button
                role="tab"
                aria-selected={activeMainTab === 'settings'}
                onClick={() => {
                  setActiveMainTab('settings');
                  fetchSettings();
                }}
                className={`pb-3 font-semibold transition-colors flex items-center gap-2 relative ${
                  activeMainTab === 'settings' ? 'text-amber-800 border-b-2 border-amber-800' : 'text-stone-500 hover:text-stone-800'
                }`}
              >
                <Palette className="w-4 h-4" />
                <span>Branding &amp; Instellingen</span>
              </button>

              <button
                role="tab"
                aria-selected={activeMainTab === 'takedowns'}
                onClick={() => setActiveMainTab('takedowns')}
                className={`pb-3 font-semibold transition-colors flex items-center gap-2 relative ${
                  activeMainTab === 'takedowns' ? 'text-amber-800 border-b-2 border-amber-800' : 'text-stone-500 hover:text-stone-800'
                }`}
              >
                <ShieldAlert className="w-4 h-4" />
                <span>Notice &amp; Takedown</span>
                {takedowns.filter((t) => t.status === 'pending').length > 0 && (
                  <span className="bg-rose-100 text-rose-800 text-[11px] font-bold px-1.5 py-0.5 rounded-full">
                    {takedowns.filter((t) => t.status === 'pending').length}
                  </span>
                )}
              </button>

              <button
                role="tab"
                aria-selected={activeMainTab === 'docenten'}
                onClick={() => setActiveMainTab('docenten')}
                className={`pb-3 font-semibold transition-colors flex items-center gap-2 relative ${
                  activeMainTab === 'docenten' ? 'text-amber-800 border-b-2 border-amber-800' : 'text-stone-500 hover:text-stone-800'
                }`}
              >
                <GraduationCap className="w-4 h-4" />
                <span>Docenten</span>
              </button>
            </>
          )}
        </div>

        {/* Curatie Wachtrij Tab */}
        {activeMainTab === 'curatie' && (
          <div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 mb-8">
              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Wachtrij</span>
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-stone-900">
                  {analytics ? analytics.status_counts.pending ?? 0 : items.length}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Te beoordelen inzendingen</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Goedgekeurd</span>
                  <Check className="w-4 h-4 text-emerald-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-emerald-700">
                  {analytics?.status_counts.approved ?? 0}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Gepubliceerd in portaal</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Afgewezen</span>
                  <X className="w-4 h-4 text-rose-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-rose-700">
                  {analytics?.status_counts.rejected ?? 0}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Niet goedgekeurd</p>
              </div>
            </div>


            {/* Filter Tabs */}
            <div className="flex border-b border-stone-200 mb-6 space-x-6 text-sm">
              {(['pending', 'approved', 'rejected'] as const).map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`pb-3 font-semibold transition-colors capitalize relative ${
                    statusFilter === st ? 'text-amber-800 border-b-2 border-amber-800' : 'text-stone-500 hover:text-stone-800'
                  }`}
                >
                  {st === 'pending' ? 'Wachtrij (In behandeling)' : st === 'approved' ? 'Goedgekeurd' : 'Afgewezen'}
                </button>
              ))}
            </div>

            {/* Items List */}
            <h2 className="sr-only">Overzicht van te beoordelen erfgoedstukken</h2>
            {loading ? (
              <div className="py-20 text-center">
                <div className="inline-block animate-spin w-8 h-8 border-4 border-amber-800 border-t-transparent rounded-full mb-3"></div>
                <p className="text-stone-500 text-sm">Wachtrij laden...</p>
              </div>
            ) : queueError ? (
              <div className="bg-rose-50 rounded-2xl p-10 border border-rose-200 text-center shadow-xs">
                <AlertCircle className="w-12 h-12 text-rose-600 mx-auto mb-3" />
                <h3 className="font-serif font-bold text-rose-900 text-lg mb-1">Fout bij ophalen curatiewachtrij</h3>
                <p className="text-xs text-rose-700 mb-4 max-w-md mx-auto">{queueError}</p>
                <button
                  type="button"
                  onClick={() => fetchQueue()}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-rose-800 hover:bg-rose-700 text-white text-xs font-bold rounded-xl transition-colors cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Opnieuw proberen
                </button>
              </div>
            ) : items.length === 0 ? (
              <div className="bg-white rounded-2xl p-12 border border-stone-200 text-center shadow-xs">
                <Shield className="w-12 h-12 text-stone-300 mx-auto mb-3" />
                <h3 className="font-serif font-bold text-stone-800 text-lg mb-1">Geen items in deze lijst</h3>
                <p className="text-xs text-stone-500">Er zijn op dit moment geen inzendingen met de status &quot;{statusFilter}&quot;.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Bulk Select All Header Toolbar */}
                {statusFilter === 'pending' && items.length > 0 && (
                  <div className="flex items-center justify-between bg-white border border-stone-200 px-5 py-3 rounded-2xl shadow-xs text-xs">
                    <label className="flex items-center gap-2.5 cursor-pointer font-medium text-stone-700 select-none">
                      <input
                        ref={selectAllCheckboxRef}
                        type="checkbox"
                        checked={items.length > 0 && selectedIds.size === items.length}
                        onChange={handleToggleSelectAll}
                        aria-label="Selecteer alle verhalen"
                        className="w-4 h-4 rounded text-amber-800 border-stone-300 focus:ring-amber-800 cursor-pointer"
                      />
                      <span>
                        Alles selecteren ({selectedIds.size} van de {items.length} geselecteerd)
                      </span>
                    </label>
                    {selectedIds.size > 0 && (
                      <button
                        type="button"
                        onClick={handleClearSelection}
                        className="text-stone-500 hover:text-stone-800 underline transition-colors cursor-pointer"
                      >
                        Selectie wissen
                      </button>
                    )}
                  </div>
                )}

                {items.map((item) => (
                  <div
                    key={item.id}
                    className={`bg-white rounded-2xl p-5 sm:p-6 border transition-colors shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-6 ${
                      selectedIds.has(item.id) ? 'border-amber-400 bg-amber-50/20 ring-1 ring-amber-400/30' : 'border-stone-200'
                    }`}
                  >
                    <div className="flex items-start gap-4 flex-grow">
                      {statusFilter === 'pending' && (
                        <div className="pt-1 flex-shrink-0">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(item.id)}
                            onChange={() => handleToggleSelectItem(item.id)}
                            aria-label={`Selecteer item: ${item.title}`}
                            className="w-4 h-4 rounded text-amber-800 border-stone-300 focus:ring-amber-800 cursor-pointer"
                          />
                        </div>
                      )}

                      <div className="flex-grow space-y-2">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-stone-500">
                        <span className="font-mono text-stone-400">#{item.id}</span>
                        <span className="bg-stone-100 px-2 py-0.5 rounded text-stone-700 font-medium">
                          {item.content_type}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {new Date(item.created_at).toLocaleDateString('nl-NL')}
                        </span>
                        <span>
                          Inzender: <strong>{item.is_anonymous ? 'Anoniem' : item.creator_name || 'Onbekend'}</strong>
                        </span>
                      </div>

                      <h3 className="font-serif font-bold text-stone-900 text-lg">
                        <Link to={`/item/${item.id}`} className="hover:text-amber-800">
                          {item.title}
                        </Link>
                      </h3>

                      {item.summary && <p className="text-xs text-stone-600 line-clamp-2">{item.summary}</p>}

                      {/* NDE Tags */}
                      {item.tags && item.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {item.tags.map((t) => (
                            <TagBadge key={t.id || t.tag} tag={t} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                    <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
                      <Link
                        to={`/item/${item.id}`}
                        target="_blank"
                        className="p-2.5 rounded-xl border border-stone-200 text-stone-600 hover:bg-stone-50 text-xs font-medium inline-flex items-center gap-1"
                      >
                        <Eye className="w-4 h-4" />
                        <span>Bekijken</span>
                      </Link>

                      <button
                        onClick={() => handleRetag(item.id)}
                        disabled={actionInProgress === item.id}
                        title="Voer AI NDE-tagger opnieuw uit"
                        className="p-2.5 rounded-xl border border-stone-200 text-stone-600 hover:bg-stone-50 text-xs font-medium inline-flex items-center gap-1 disabled:opacity-50"
                      >
                        <Sparkles className="w-4 h-4 text-amber-700" />
                        <span>AI Tag</span>
                      </button>

                      {statusFilter === 'pending' && (
                        <>
                          <button
                            onClick={() => handleApprove(item.id)}
                            disabled={actionInProgress === item.id}
                            className="bg-emerald-700 hover:bg-emerald-800 text-white px-3.5 py-2.5 rounded-xl text-xs font-bold inline-flex items-center gap-1.5 shadow-xs transition-colors disabled:opacity-50"
                          >
                            <Check className="w-4 h-4" />
                            Goedkeuren
                          </button>

                          <button
                            onClick={() => setRejectingItem(item)}
                            disabled={actionInProgress === item.id}
                            className="bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 px-3.5 py-2.5 rounded-xl text-xs font-bold inline-flex items-center gap-1.5 transition-colors disabled:opacity-50"
                          >
                            <X className="w-4 h-4" />
                            Afwijzen
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* KPI Analytics & NDE Tab */}
        {activeMainTab === 'analytics' && (
          <div>
            {analyticsError && (
              <div className="mb-6 p-4 bg-rose-50 border border-rose-200 rounded-2xl flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-rose-900">Fout bij ophalen analytics</p>
                  <p className="text-xs text-rose-700">{analyticsError}</p>
                </div>
                <button
                  type="button"
                  onClick={fetchAnalytics}
                  className="px-3 py-1.5 bg-white border border-rose-300 text-xs font-medium text-rose-800 rounded-lg hover:bg-rose-50 shadow-2xs"
                >
                  Opnieuw proberen
                </button>
              </div>
            )}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4 mb-8">
              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Wachtrij</span>
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-stone-900">
                  {analytics ? analytics.status_counts.pending ?? 0 : items.length}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Te beoordelen inzendingen</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Goedgekeurd</span>
                  <Check className="w-4 h-4 text-emerald-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-emerald-700">
                  {analytics?.status_counts.approved ?? 0}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Gepubliceerd in portaal</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Afgewezen</span>
                  <X className="w-4 h-4 text-rose-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-rose-700">
                  {analytics?.status_counts.rejected ?? 0}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Niet goedgekeurd</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Gem. Beoordelingstijd</span>
                  <Clock className="w-4 h-4 text-blue-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-stone-900">
                  {analytics?.average_moderation_seconds != null
                    ? analytics.average_moderation_seconds < 3600
                      ? `${Math.round(analytics.average_moderation_seconds / 60)} m`
                      : `${(analytics.average_moderation_seconds / 3600).toFixed(1)} u`
                    : '-'}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Doorlooptijd per item</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs col-span-2 lg:col-span-1">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Platform &amp; Edu</span>
                  <Users className="w-4 h-4 text-indigo-600" />
                </div>
                <div className="text-sm font-semibold text-stone-900 mt-1">
                  {analytics?.newsletter.total_subscribers ?? 0} abonnees
                </div>
                <div className="text-xs text-stone-500 flex items-center gap-1 mt-0.5">
                  <GraduationCap className="w-3.5 h-3.5 text-indigo-500" />
                  <span>{analytics?.education.active_codes ?? 0} actieve klassen</span>
                </div>
              </div>
            </div>

            {/* AI Tag Distributie & Kwaliteit Accordion */}
            {analytics && analytics.tag_distribution.length > 0 && (
              <div className="bg-white rounded-2xl border border-stone-200 shadow-xs mb-8 overflow-hidden">
                <button
                  onClick={() => setShowTagDist(!showTagDist)}
                  className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-stone-50/70 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-amber-600" />
                    <span className="font-semibold text-xs sm:text-sm text-stone-900">
                      AI NDE-Thesaurus Distributie &amp; Betrouwbaarheid ({analytics.tag_distribution.length} tags)
                    </span>
                  </div>
                  {showTagDist ? (
                    <ChevronUp className="w-4 h-4 text-stone-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-stone-400" />
                  )}
                </button>

                {showTagDist && (
                  <div className="px-5 pb-5 border-t border-stone-100">
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs mt-3">
                        <thead>
                          <tr className="text-stone-400 border-b border-stone-100">
                            <th className="pb-2 font-medium">Tag</th>
                            <th className="pb-2 font-medium">Categorie</th>
                            <th className="pb-2 font-medium">Aantal</th>
                            <th className="pb-2 font-medium">Gem. AI Betrouwbaarheid</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-stone-100 text-stone-700">
                          {analytics.tag_distribution.map((t, idx) => (
                            <tr key={idx} className="hover:bg-stone-50/50">
                              <td className="py-2.5 font-medium text-stone-900">{t.tag}</td>
                              <td className="py-2.5">
                                <span className="bg-stone-100 text-stone-600 px-2 py-0.5 rounded text-[11px] font-mono">
                                  {t.tag_type}
                                </span>
                              </td>
                              <td className="py-2.5 font-semibold">{t.count}x</td>
                              <td className="py-2.5">
                                <div className="flex items-center gap-2 max-w-[140px]">
                                  <div className="w-full bg-stone-100 rounded-full h-1.5 overflow-hidden">
                                    <div
                                      className="bg-amber-600 h-1.5 rounded-full"
                                      style={{ width: `${Math.round(t.average_confidence * 100)}%` }}
                                    />
                                  </div>
                                  <span className="text-[11px] font-mono text-stone-500">
                                    {Math.round(t.average_confidence * 100)}%
                                  </span>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Branding & Instellingen Tab (FE-PAGE-014) */}
        {activeMainTab === 'settings' && (
          <div className="space-y-8">
            {settingsStatus && (
              <div
                role="status"
                aria-live="polite"
                className={`p-4 rounded-xl text-xs font-semibold flex items-center justify-between ${
                  settingsStatus.success
                    ? 'bg-emerald-50 border border-emerald-200 text-emerald-900'
                    : 'bg-red-50 border border-red-200 text-red-900'
                }`}
              >
                <span>{settingsStatus.message}</span>
                <button
                  type="button"
                  onClick={() => setSettingsStatus(null)}
                  className="hover:underline text-xs"
                >
                  Sluiten
                </button>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
              {/* Formulier */}
              <div className="lg:col-span-7 bg-white p-6 sm:p-8 rounded-3xl border border-stone-200 shadow-xs">
                <div className="flex items-center gap-2.5 mb-6">
                  <Palette className="w-5 h-5 text-amber-800" />
                  <h2 className="font-serif text-xl font-bold text-stone-900">
                    White-Label Portaal Branding
                  </h2>
                </div>

                {settingsLoading ? (
                  <div className="py-12 text-center text-stone-500 text-xs">
                    Instellingen laden...
                  </div>
                ) : (
                  <form onSubmit={handleSaveSettings} className="space-y-5">
                    <div>
                      <label
                        htmlFor="platform_name_nl"
                        className="block text-xs font-semibold text-stone-700 mb-1"
                      >
                        Platformnaam (Nederlands) *
                      </label>
                      <input
                        id="platform_name_nl"
                        type="text"
                        required
                        maxLength={120}
                        value={settingsForm.platform_name_nl || ''}
                        onChange={(e) =>
                          setSettingsForm({ ...settingsForm, platform_name_nl: e.target.value })
                        }
                        placeholder="bijv. Stichting Ketikoti Vlaardingen"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-amber-800/20 focus:border-amber-800"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="platform_name_en"
                        className="block text-xs font-semibold text-stone-700 mb-1"
                      >
                        Platformnaam (Engels)
                      </label>
                      <input
                        id="platform_name_en"
                        type="text"
                        maxLength={120}
                        value={settingsForm.platform_name_en || ''}
                        onChange={(e) =>
                          setSettingsForm({ ...settingsForm, platform_name_en: e.target.value })
                        }
                        placeholder="bijv. Ketikoti Vlaardingen Heritage Foundation"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-amber-800/20 focus:border-amber-800"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label
                          htmlFor="primary_color"
                          className="block text-xs font-semibold text-stone-700 mb-1"
                        >
                          Primaire Kleur (Hex) *
                        </label>
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            id="primary_color_picker"
                            aria-label="Primaire kleur picker"
                            value={settingsForm.primary_color || '#1a2f45'}
                            onChange={(e) =>
                              setSettingsForm({ ...settingsForm, primary_color: e.target.value })
                            }
                            className="w-10 h-10 p-0.5 rounded-lg border border-stone-300 cursor-pointer bg-white"
                          />
                          <input
                            id="primary_color"
                            type="text"
                            required
                            pattern="^#[0-9a-fA-F]{6}$"
                            value={settingsForm.primary_color || '#1a2f45'}
                            onChange={(e) =>
                              setSettingsForm({ ...settingsForm, primary_color: e.target.value })
                            }
                            className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 font-mono text-xs text-stone-900 focus:outline-none focus:border-amber-800 uppercase"
                          />
                        </div>
                      </div>

                      <div>
                        <label
                          htmlFor="accent_color"
                          className="block text-xs font-semibold text-stone-700 mb-1"
                        >
                          Accentkleur (Hex) *
                        </label>
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            id="accent_color_picker"
                            aria-label="Accentkleur picker"
                            value={settingsForm.accent_color || '#e8b86d'}
                            onChange={(e) =>
                              setSettingsForm({ ...settingsForm, accent_color: e.target.value })
                            }
                            className="w-10 h-10 p-0.5 rounded-lg border border-stone-300 cursor-pointer bg-white"
                          />
                          <input
                            id="accent_color"
                            type="text"
                            required
                            pattern="^#[0-9a-fA-F]{6}$"
                            value={settingsForm.accent_color || '#e8b86d'}
                            onChange={(e) =>
                              setSettingsForm({ ...settingsForm, accent_color: e.target.value })
                            }
                            className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 font-mono text-xs text-stone-900 focus:outline-none focus:border-amber-800 uppercase"
                          />
                        </div>
                      </div>
                    </div>

                    <div>
                      <label
                        htmlFor="contact_email"
                        className="block text-xs font-semibold text-stone-700 mb-1"
                      >
                        Contact E-mailadres
                      </label>
                      <input
                        id="contact_email"
                        type="email"
                        maxLength={255}
                        value={settingsForm.contact_email || ''}
                        onChange={(e) =>
                          setSettingsForm({ ...settingsForm, contact_email: e.target.value })
                        }
                        placeholder="contact@organisatie.nl"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-amber-800/20 focus:border-amber-800"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label
                          htmlFor="logo_url"
                          className="block text-xs font-semibold text-stone-700 mb-1"
                        >
                          Logo URL (PNG / SVG)
                        </label>
                        <input
                          id="logo_url"
                          type="url"
                          maxLength={500}
                          value={settingsForm.logo_url || ''}
                          onChange={(e) =>
                            setSettingsForm({ ...settingsForm, logo_url: e.target.value })
                          }
                          placeholder="https://..."
                          className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 text-xs text-stone-900 focus:outline-none focus:border-amber-800"
                        />
                      </div>

                      <div>
                        <label
                          htmlFor="favicon_url"
                          className="block text-xs font-semibold text-stone-700 mb-1"
                        >
                          Favicon URL (.ico / .png)
                        </label>
                        <input
                          id="favicon_url"
                          type="url"
                          maxLength={500}
                          value={settingsForm.favicon_url || ''}
                          onChange={(e) =>
                            setSettingsForm({ ...settingsForm, favicon_url: e.target.value })
                          }
                          placeholder="https://..."
                          className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 text-xs text-stone-900 focus:outline-none focus:border-amber-800"
                        />
                      </div>
                    </div>

                    <div>
                      <label
                        htmlFor="about_nl"
                        className="block text-xs font-semibold text-stone-700 mb-1"
                      >
                        Over Ons Beschrijving (NL)
                      </label>
                      <textarea
                        id="about_nl"
                        rows={3}
                        value={settingsForm.about_nl || ''}
                        onChange={(e) =>
                          setSettingsForm({ ...settingsForm, about_nl: e.target.value })
                        }
                        placeholder="Beschrijf de stichting en het doel van het archief..."
                        className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 text-xs text-stone-900 focus:outline-none focus:border-amber-800"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="guidelines_nl"
                        className="block text-xs font-semibold text-stone-700 mb-1"
                      >
                        Inzendingsrichtlijnen (NL)
                      </label>
                      <textarea
                        id="guidelines_nl"
                        rows={3}
                        value={settingsForm.guidelines_nl || ''}
                        onChange={(e) =>
                          setSettingsForm({ ...settingsForm, guidelines_nl: e.target.value })
                        }
                        placeholder="Gedragsregels en inhoudelijke richtlijnen voor verhalen..."
                        className="w-full px-3.5 py-2.5 rounded-xl border border-stone-300 text-xs text-stone-900 focus:outline-none focus:border-amber-800"
                      />
                    </div>

                    <div className="pt-2">
                      <button
                        type="submit"
                        disabled={settingsSaving}
                        className="w-full sm:w-auto px-6 py-3 rounded-xl bg-amber-800 hover:bg-amber-900 text-white text-xs font-bold shadow-xs transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                      >
                        <Save className="w-4 h-4" />
                        <span>{settingsSaving ? 'Opslaan...' : 'Instellingen Opslaan'}</span>
                      </button>
                    </div>
                  </form>
                )}
              </div>

              {/* Live Preview Card */}
              <div className="lg:col-span-5 space-y-4">
                <div className="bg-white p-6 rounded-3xl border border-stone-200 shadow-xs">
                  <div className="flex items-center gap-2 mb-4 text-xs font-semibold text-stone-500 uppercase tracking-wider">
                    <Eye className="w-3.5 h-3.5" />
                    <span>Live Huisstijl Voorbeeld</span>
                  </div>

                  {/* Mini Browser Bar */}
                  <div className="border border-stone-200 rounded-2xl overflow-hidden shadow-xs">
                    <div
                      className="p-4 text-white flex items-center justify-between"
                      style={{ backgroundColor: settingsForm.primary_color || '#1a2f45' }}
                    >
                      <div className="flex items-center gap-2">
                        {settingsForm.logo_url ? (
                          <img
                            src={settingsForm.logo_url}
                            alt="Logo preview"
                            className="h-6 w-auto object-contain"
                          />
                        ) : (
                          <div
                            className="w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs"
                            style={{
                              backgroundColor: settingsForm.accent_color || '#e8b86d',
                              color: '#1a2f45',
                            }}
                          >
                            M
                          </div>
                        )}
                        <span className="font-serif font-bold text-sm truncate max-w-[180px]">
                          {settingsForm.platform_name_nl || 'Levend Monument'}
                        </span>
                      </div>

                      <span
                        className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                        style={{
                          backgroundColor: settingsForm.accent_color || '#e8b86d',
                          color: '#1a2f45',
                        }}
                      >
                        Voorbeeld
                      </span>
                    </div>

                    <div className="p-4 bg-stone-50 text-xs space-y-3">
                      <div className="bg-white p-3 rounded-xl border border-stone-200">
                        <h3 className="font-bold text-stone-900 mb-1 text-xs">
                          {settingsForm.platform_name_nl || 'Uw Erfgoedplatform'}
                        </h3>
                        <p className="text-[11px] text-stone-500 line-clamp-2">
                          {settingsForm.about_nl || 'Hier verschijnt de introductietekst van uw stichting.'}
                        </p>
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-stone-500 pt-1">
                        <span>Contact: {settingsForm.contact_email || 'geen e-mail ingesteld'}</span>
                        <span
                          className="font-bold text-xs"
                          style={{ color: settingsForm.primary_color || '#1a2f45' }}
                        >
                          Bekijk archief &rarr;
                        </span>
                      </div>
                    </div>
                  </div>

                  <p className="text-[11px] text-stone-400 mt-4 leading-relaxed">
                    De primaire kleur bepaalt de navigatie en headers. De accentkleur wordt toegepast op badges, actieve tabbladen en steunknoppen.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Notice & Takedown Moderatie Tab (FE-CUR-001) */}
        {activeMainTab === 'archief' && <ArchiefExportPanel />}
        {activeMainTab === 'docenten' && isAdmin && <DocentenBeheerPanel />}

        {activeMainTab === 'takedowns' && (
          <div>
            {/* KPI Cards for Takedowns */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 sm:gap-4 mb-8">
              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>In Behandeling</span>
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-amber-700">
                  {takedowns.filter((t) => t.status === 'pending').length}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Nieuwe meldingen</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Offline Gehaald</span>
                  <Check className="w-4 h-4 text-rose-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-rose-700">
                  {takedowns.filter((t) => t.status === 'approved').length}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Toegewezen verzoeken</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Afgewezen</span>
                  <X className="w-4 h-4 text-emerald-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-emerald-700">
                  {takedowns.filter((t) => t.status === 'rejected').length}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">Ongegrond bevonden</p>
              </div>

              <div className="bg-white p-4 rounded-2xl border border-stone-200 shadow-xs">
                <div className="flex items-center justify-between text-xs font-medium text-stone-500 mb-1">
                  <span>Geescaleerd</span>
                  <ShieldAlert className="w-4 h-4 text-purple-600" />
                </div>
                <div className="text-2xl font-serif font-bold text-purple-700">
                  {takedowns.filter((t) => t.status === 'escalated').length}
                </div>
                <p className="text-[11px] text-stone-400 mt-0.5">In bestuursberaad</p>
              </div>
            </div>

            {/* Filter Tabs */}
            <div className="flex border-b border-stone-200 mb-6 space-x-6 text-sm overflow-x-auto">
              {(
                [
                  { id: 'all', label: 'Alle Meldingen' },
                  { id: 'pending', label: 'In Behandeling' },
                  { id: 'approved', label: 'Offline Gehaald' },
                  { id: 'rejected', label: 'Afgewezen' },
                  { id: 'escalated', label: 'Geescaleerd' },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setTakedownStatusFilter(tab.id)}
                  className={`pb-3 font-semibold transition-colors whitespace-nowrap relative ${
                    takedownStatusFilter === tab.id
                      ? 'text-amber-800 border-b-2 border-amber-800'
                      : 'text-stone-500 hover:text-stone-800'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {takedownLoading ? (
              <div className="flex justify-center items-center py-20 text-stone-400">
                <RefreshCw className="w-6 h-6 animate-spin mr-2" />
                <span>Meldingen laden...</span>
              </div>
            ) : takedownError ? (
              <div className="bg-rose-50 rounded-2xl p-10 border border-rose-200 text-center shadow-xs">
                <AlertCircle className="w-12 h-12 text-rose-600 mx-auto mb-3" />
                <h3 className="font-serif font-bold text-rose-900 text-lg mb-1">Fout bij ophalen Notice &amp; Takedown meldingen</h3>
                <p className="text-xs text-rose-700 mb-4 max-w-md mx-auto">{takedownError}</p>
                <button
                  type="button"
                  onClick={() => fetchTakedowns()}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-rose-800 hover:bg-rose-700 text-white text-xs font-bold rounded-xl transition-colors cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Opnieuw proberen
                </button>
              </div>
            ) : takedowns.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-stone-200 p-8">
                <ShieldAlert className="w-12 h-12 text-stone-300 mx-auto mb-3" />
                <h3 className="text-base font-serif font-semibold text-stone-700">Geen meldingen gevonden</h3>
                <p className="text-stone-400 text-xs mt-1">
                  Er zijn momenteel geen Notice &amp; Takedown verzoeken met deze status.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {takedowns.map((td) => (
                  <div
                    key={td.id}
                    className="bg-white rounded-2xl border border-stone-200 p-5 shadow-xs transition-shadow hover:shadow-md"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-stone-500 bg-stone-100 px-2 py-0.5 rounded">
                          #NTD-{td.id}
                        </span>
                        <span className="text-xs text-stone-400">
                          {new Date(td.created_at).toLocaleDateString('nl-NL', {
                            day: 'numeric',
                            month: 'short',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                      <div>
                        {td.status === 'pending' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
                            In Behandeling
                          </span>
                        )}
                        {td.status === 'approved' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800">
                            Offline Gehaald
                          </span>
                        )}
                        {td.status === 'rejected' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
                            Afgewezen (Ongegrond)
                          </span>
                        )}
                        {td.status === 'escalated' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                            Geescaleerd
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                      <div className="bg-stone-50 p-3.5 rounded-xl border border-stone-200">
                        <div className="text-[11px] font-bold text-stone-500 uppercase tracking-wider mb-1">
                          Betreft Erfgoeditem
                        </div>
                        <div className="font-serif font-bold text-stone-900 text-sm">
                          {td.content_title || `Item #${td.content_id}`}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-stone-500 mt-1">
                          <span>ID: #{td.content_id}</span>
                          {td.content_type && <span>Type: {td.content_type}</span>}
                          {td.content_status && (
                            <span className="font-medium text-stone-600">Status: {td.content_status}</span>
                          )}
                        </div>
                        {td.content_status === 'removed' && (
                          <button
                            onClick={() => handleRestoreContent(td.content_id)}
                            className="mt-2 text-xs font-semibold text-emerald-700 hover:text-emerald-800 hover:underline cursor-pointer"
                          >
                            Herstel Item naar Archief
                          </button>
                        )}
                      </div>

                      <div className="bg-stone-50 p-3.5 rounded-xl border border-stone-200">
                        <div className="text-[11px] font-bold text-stone-500 uppercase tracking-wider mb-1">
                          Melder Contactgegevens
                        </div>
                        <div className="text-xs font-medium text-stone-800">
                          {td.requester_name}
                        </div>
                        <div className="text-xs text-stone-500">{td.requester_email}</div>
                      </div>
                    </div>

                    <div className="mb-4">
                      <div className="text-xs font-bold text-stone-700 mb-1">Juridische Grondslag &amp; Toelichting:</div>
                      <p className="text-xs text-stone-600 bg-stone-50 p-3 rounded-xl border border-stone-200 whitespace-pre-wrap">
                        {td.legal_basis}
                      </p>
                    </div>

                    {td.resolution_note && (
                      <div className="mb-4 border-l-4 border-amber-600 bg-amber-50/50 p-3 rounded-r-xl">
                        <div className="text-[11px] font-bold text-amber-900 uppercase">
                          Besluitnotitie Curator:
                        </div>
                        <p className="text-xs text-amber-950 mt-0.5 whitespace-pre-wrap">
                          {td.resolution_note}
                        </p>
                      </div>
                    )}

                    <div className="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-stone-100">
                      {td.status === 'pending' || td.status === 'escalated' ? (
                        <button
                          onClick={() => handleOpenResolveModal(td, 'approved')}
                          className="px-3.5 py-1.5 rounded-xl bg-amber-800 hover:bg-amber-900 text-white text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer"
                        >
                          <Check className="w-3.5 h-3.5" />
                          <span>Beoordelen / Afhandelen</span>
                        </button>
                      ) : (
                        <button
                          onClick={() => handleOpenResolveModal(td, td.status as any)}
                          className="px-3 py-1.5 rounded-xl border border-stone-200 text-xs font-medium text-stone-600 hover:bg-stone-50 cursor-pointer"
                        >
                          Herzien / Notitie Bijwerken
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Takedown Resolve Modal */}
        {resolvingModalOpen && selectedTakedown && (
          <div className="fixed inset-0 bg-stone-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="takedown-modal-title"
              className="bg-white rounded-3xl p-6 max-w-lg w-full shadow-2xl border border-stone-200"
            >
              <h3 id="takedown-modal-title" className="text-base font-serif font-bold text-stone-900 mb-1">
                Notice &amp; Takedown Melding Beoordelen
              </h3>
              <p className="text-stone-500 text-xs mb-4">
                Melding #{selectedTakedown.id} voor erfgoeditem #{selectedTakedown.content_id}:{' '}
                <span className="font-semibold text-stone-800">
                  {selectedTakedown.content_title || 'Erfgoeditem'}
                </span>
              </p>

              <div className="mb-4">
                <span className="block text-xs font-bold text-stone-700 mb-1.5">
                  Besluit &amp; Maatregel (DSA Art. 16/17):
                </span>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setResolveOutcome('approved')}
                    className={`p-2.5 rounded-xl text-xs font-semibold border transition-all text-center cursor-pointer ${
                      resolveOutcome === 'approved'
                        ? 'border-rose-600 bg-rose-50 text-rose-900 shadow-xs'
                        : 'border-stone-200 text-stone-600 hover:bg-stone-50'
                    }`}
                  >
                    Content Offline Halen
                  </button>
                  <button
                    type="button"
                    onClick={() => setResolveOutcome('rejected')}
                    className={`p-2.5 rounded-xl text-xs font-semibold border transition-all text-center cursor-pointer ${
                      resolveOutcome === 'rejected'
                        ? 'border-emerald-600 bg-emerald-50 text-emerald-900 shadow-xs'
                        : 'border-stone-200 text-stone-600 hover:bg-stone-50'
                    }`}
                  >
                    Melding Afwijzen
                  </button>
                  <button
                    type="button"
                    onClick={() => setResolveOutcome('escalated')}
                    className={`p-2.5 rounded-xl text-xs font-semibold border transition-all text-center cursor-pointer ${
                      resolveOutcome === 'escalated'
                        ? 'border-purple-600 bg-purple-50 text-purple-900 shadow-xs'
                        : 'border-stone-200 text-stone-600 hover:bg-stone-50'
                    }`}
                  >
                    Escaleren
                  </button>
                </div>
              </div>

              <div className="mb-4">
                <label htmlFor="resolve-note" className="block text-xs font-bold text-stone-700 mb-1">
                  Motivering van het besluit (verplicht, wordt verzonden aan melder):
                </label>
                <textarea
                  id="resolve-note"
                  rows={4}
                  required
                  value={resolveNote}
                  onChange={(e) => {
                    setResolveNote(e.target.value);
                    setResolveError(null);
                  }}
                  placeholder="Beschrijf de juridische of feitelijke overweging voor dit besluit (bijv. Auteursrecht geverifieerd via archiefbron; item offline conform art. 6:196c BW)..."
                  className="w-full px-4 py-2.5 text-xs rounded-xl border border-stone-300 focus:outline-none focus:border-amber-800"
                />
                {resolveError && (
                  <p role="alert" className="text-rose-600 text-xs font-medium mt-1">
                    {resolveError}
                  </p>
                )}
              </div>

              <div className="flex justify-end gap-3 pt-2 border-t border-stone-100">
                <button
                  type="button"
                  onClick={() => {
                    setResolvingModalOpen(false);
                    setSelectedTakedown(null);
                    setResolveNote('');
                    setResolveError(null);
                  }}
                  className="px-4 py-2 rounded-xl border border-stone-200 text-xs font-semibold text-stone-600 hover:bg-stone-50 cursor-pointer"
                >
                  Annuleren
                </button>
                <button
                  type="button"
                  onClick={handleResolveSubmit}
                  disabled={resolveInProgress}
                  className="bg-amber-800 hover:bg-amber-900 text-white px-4 py-2 rounded-xl text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {resolveInProgress ? 'Verwerken...' : 'Besluit Definitief Toepassen'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Reject Dialog Modal */}
        {rejectingItem && (
          <div className="fixed inset-0 z-50 bg-stone-900/50 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-lg w-full border border-stone-200 shadow-xl">
              <div className="w-12 h-12 bg-red-100 text-red-700 rounded-full flex items-center justify-center mb-4">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <h3 className="font-serif font-bold text-stone-900 text-xl mb-1">
                Item #{rejectingItem.id} Afwijzen
              </h3>
              <p className="text-stone-500 text-xs mb-4">
                Geef een reden op voor afwijzing (bijv. ongeschikte inhoud, onleesbaar of auteursrechtkwestie).
              </p>

              <textarea
                rows={4}
                required
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Reden van afwijzing..."
                className="w-full px-4 py-2.5 text-xs rounded-xl border border-stone-300 focus:outline-none focus:border-red-600 mb-4"
              />

              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setRejectingItem(null);
                    setRejectReason('');
                  }}
                  className="px-4 py-2 rounded-xl border border-stone-200 text-xs font-semibold text-stone-600 hover:bg-stone-50"
                >
                  Annuleren
                </button>
                <button
                  onClick={handleConfirmReject}
                  disabled={actionInProgress !== null}
                  className="bg-red-700 hover:bg-red-800 text-white px-4 py-2 rounded-xl text-xs font-bold transition-colors disabled:opacity-50"
                >
                  Bevestig Afwijzing
                </button>
              </div>
            </div>
          </div>
        )}
        {/* Floating Bulk Action Bar (FE-CUR-002) */}
        {statusFilter === 'pending' && selectedIds.size > 0 && (
          <div
            role="toolbar"
            aria-label="Bulk acties"
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-stone-900 text-white px-5 py-3.5 rounded-2xl shadow-2xl border border-stone-700 flex flex-wrap items-center justify-between gap-4 max-w-xl w-[92%]"
          >
            <div
              role="status"
              aria-live="polite"
              className="text-xs font-semibold text-stone-200 flex items-center gap-2"
            >
              <span className="inline-block w-2 h-2 rounded-full bg-amber-400"></span>
              <span>{selectedIds.size} van de {items.length} item(s) geselecteerd</span>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleBulkApprove}
                disabled={bulkActionInProgress}
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3.5 py-1.5 rounded-xl text-xs flex items-center gap-1.5 transition-colors disabled:opacity-50 cursor-pointer"
              >
                <Check className="w-3.5 h-3.5" />
                <span>{bulkActionInProgress ? 'Bezig...' : `Goedkeuren (${selectedIds.size})`}</span>
              </button>

              <button
                type="button"
                onClick={handleOpenBulkRejectModal}
                disabled={bulkActionInProgress}
                className="bg-rose-900/40 hover:bg-rose-900/60 text-rose-200 border border-rose-700 font-bold px-3.5 py-1.5 rounded-xl text-xs flex items-center gap-1.5 transition-colors disabled:opacity-50 cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
                <span>{bulkActionInProgress ? 'Bezig...' : `Afwijzen (${selectedIds.size})`}</span>
              </button>

              <button
                type="button"
                onClick={handleClearSelection}
                disabled={bulkActionInProgress}
                className="text-stone-400 hover:text-white text-xs px-2 py-1 transition-colors cursor-pointer"
                title="Deselecteer alles (Escape)"
              >
                Wissen
              </button>
            </div>
          </div>
        )}

        {/* Bulk Reject Dialog Modal (FE-CUR-002 / DSA Art. 17) */}
        {bulkRejectModalOpen && (
          <div className="fixed inset-0 z-50 bg-stone-900/50 backdrop-blur-xs flex items-center justify-center p-4">
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="bulk-reject-modal-title"
              className="bg-white rounded-3xl p-6 sm:p-8 max-w-lg w-full border border-stone-200 shadow-xl space-y-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-rose-100 text-rose-700 rounded-full flex items-center justify-center">
                    <AlertTriangle className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 id="bulk-reject-modal-title" className="font-serif font-bold text-stone-900 text-lg">
                      Bulk Afwijzen ({selectedIds.size} items)
                    </h3>
                    <p className="text-stone-500 text-xs">
                      Motiveringsplicht conform Digital Services Act (DSA Art. 17)
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setBulkRejectModalOpen(false)}
                  className="text-stone-400 hover:text-stone-600 p-1 rounded-lg cursor-pointer"
                  aria-label="Sluiten"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <p className="text-xs text-stone-600">
                Geef een duidelijke motivering op. Deze verklaring wordt geregistreerd bij alle <strong>{selectedIds.size}</strong> geselecteerde erfgoedstukken en gecommuniceerd aan de betrokken inzenders.
              </p>

              {bulkRejectError && (
                <div role="alert" className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl">
                  {bulkRejectError}
                </div>
              )}

              <div>
                <label htmlFor="bulk-reject-reason" className="block text-xs font-semibold text-stone-700 mb-1">
                  Gemeenschappelijke motivering * (minimaal 5 tekens)
                </label>
                <textarea
                  id="bulk-reject-reason"
                  aria-required="true"
                  rows={4}
                  maxLength={1000}
                  value={bulkRejectReason}
                  onChange={(e) => setBulkRejectReason(e.target.value)}
                  placeholder="Bijv. Deze inzendingen bevatten onvoldoende historische context conform het stichtingsbeleid..."
                  className="w-full px-4 py-2.5 text-xs rounded-xl border border-stone-300 focus:outline-none focus:border-rose-600"
                />
                <div className="flex justify-between text-[11px] text-stone-400 mt-1">
                  <span>Minimaal 5 tekens vereist</span>
                  <span>{bulkRejectReason.length} / 1000 tekens</span>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setBulkRejectModalOpen(false);
                    setBulkRejectReason('');
                  }}
                  disabled={bulkActionInProgress}
                  className="px-4 py-2 rounded-xl border border-stone-200 text-xs font-semibold text-stone-600 hover:bg-stone-50 cursor-pointer"
                >
                  Annuleren
                </button>
                <button
                  type="button"
                  onClick={handleConfirmBulkReject}
                  disabled={bulkActionInProgress || bulkRejectReason.trim().length < 5}
                  className="bg-rose-700 hover:bg-rose-800 text-white px-4 py-2 rounded-xl text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {bulkActionInProgress ? 'Bezig met afwijzen...' : `Bevestig Afwijzing (${selectedIds.size})`}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
