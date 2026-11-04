import React, { useCallback, useEffect, useState } from 'react';
import { Archive, Download, Loader2, ShieldCheck } from 'lucide-react';

import { api } from '../api/client';
import type { ArchiveExportItem } from '../types';

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDatum = (iso: string): string =>
  new Date(iso).toLocaleString('nl-NL', { dateStyle: 'medium', timeStyle: 'short' });

export const ArchiefExportPanel: React.FC = () => {
  const [exports, setExports] = useState<ArchiveExportItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [melding, setMelding] = useState<string | null>(null);

  const laad = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getArchiveExports({ limit: 50 });
      setExports(res.items);
    } catch {
      setError('De lijst met archiefexports kon niet worden geladen.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void laad();
  }, [laad]);

  const maakExport = async () => {
    setIsCreating(true);
    setError(null);
    setMelding(null);
    try {
      const nieuw = await api.createArchiveExport();
      setMelding(`Archiefexport gemaakt: ${nieuw.item_count} items, ${formatBytes(nieuw.size_bytes)}.`);
      await laad();
    } catch {
      setError('De archiefexport is mislukt. Er is niets opgeslagen.');
    } finally {
      setIsCreating(false);
    }
  };

  const download = async (item: ArchiveExportItem) => {
    setDownloadingId(item.id);
    setError(null);
    try {
      const blob = await api.downloadArchiveExport(item.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${item.bag_name}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Pas na de klik vrijgeven: direct intrekken breekt de download in sommige browsers af.
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError('Downloaden is mislukt: het pakket is niet beschikbaar of niet meer ongeschonden.');
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <section aria-labelledby="archief-titel">
      <div className="bg-white p-6 rounded-2xl border border-stone-200 mb-6">
        <h2 id="archief-titel" className="font-serif text-xl font-bold text-stone-900 flex items-center gap-2">
          <Archive className="w-5 h-5 text-amber-800" aria-hidden="true" />
          Archief-export (BagIt)
        </h2>
        <p className="text-sm text-stone-600 mt-2 max-w-2xl">
          Elke export is een volledige momentopname van alle publieke, goedgekeurde verhalen, in het
          internationale archiefformaat BagIt 1.0, met Dublin Core per item. Elke zondagnacht gebeurt
          dit automatisch; met de knop hieronder maakt u er nu een.
        </p>
        <button
          type="button"
          onClick={maakExport}
          disabled={isCreating}
          className="mt-4 inline-flex items-center gap-2 bg-amber-800 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-amber-900 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-amber-500"
        >
          {isCreating ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Archive className="w-4 h-4" aria-hidden="true" />}
          {isCreating ? 'Bezig met exporteren...' : 'Maak nu een archiefexport'}
        </button>
        <div aria-live="polite" className="mt-3 text-sm">
          {melding && <p className="text-emerald-800">{melding}</p>}
          {error && <p className="text-rose-700" role="alert">{error}</p>}
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-stone-200 overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Eerdere archiefexports, nieuwste eerst</caption>
          <thead className="bg-stone-50 text-stone-600 text-left">
            <tr>
              <th scope="col" className="px-4 py-3 font-semibold">Gemaakt</th>
              <th scope="col" className="px-4 py-3 font-semibold">Items</th>
              <th scope="col" className="px-4 py-3 font-semibold">Grootte</th>
              <th scope="col" className="px-4 py-3 font-semibold">Hoe</th>
              <th scope="col" className="px-4 py-3 font-semibold">Controlegetal (SHA-256)</th>
              <th scope="col" className="px-4 py-3 font-semibold"><span className="sr-only">Actie</span></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} className="px-4 py-6 text-stone-500">Laden...</td></tr>
            )}
            {!isLoading && exports.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-stone-500">Nog geen archiefexports.</td></tr>
            )}
            {exports.map((item) => (
              <tr key={item.id} className="border-t border-stone-100">
                <td className="px-4 py-3 whitespace-nowrap">{formatDatum(item.created_at)}</td>
                <td className="px-4 py-3">{item.item_count}</td>
                <td className="px-4 py-3 whitespace-nowrap">{formatBytes(item.size_bytes)}</td>
                <td className="px-4 py-3">{item.trigger === 'schema' ? 'Automatisch' : 'Handmatig'}</td>
                <td className="px-4 py-3 font-mono text-xs text-stone-500" title={item.sha256}>
                  <span className="inline-flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-700" aria-hidden="true" />
                    {item.sha256.slice(0, 16)}...
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => void download(item)}
                    disabled={downloadingId === item.id}
                    aria-label={`Download archiefexport van ${formatDatum(item.created_at)}`}
                    className="inline-flex items-center gap-1 text-amber-800 font-semibold hover:underline disabled:opacity-60"
                  >
                    {downloadingId === item.id ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Download className="w-4 h-4" aria-hidden="true" />}
                    Download
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};
