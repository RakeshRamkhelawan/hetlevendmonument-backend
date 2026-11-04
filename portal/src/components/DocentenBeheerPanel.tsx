import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle, GraduationCap, RefreshCw, UserX, XCircle } from 'lucide-react';
import { api } from '../api/client';
import type { DocentAanvraagItem, DocentItem } from '../types';

/**
 * Beheertab "Docenten" (BE-EP-055): aanvragen goedkeuren of afwijzen, docenten bekijken en
 * hun rol intrekken. Alleen voor beheerders.
 */
export const DocentenBeheerPanel: React.FC = () => {
  const [aanvragen, setAanvragen] = useState<DocentAanvraagItem[]>([]);
  const [docenten, setDocenten] = useState<DocentItem[]>([]);
  const [filter, setFilter] = useState<'pending' | 'alle'>('pending');
  const [bezig, setBezig] = useState<number | null>(null);
  const [melding, setMelding] = useState<string | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [afwijsId, setAfwijsId] = useState<number | null>(null);
  const [reden, setReden] = useState('');
  const [intrekId, setIntrekId] = useState<number | null>(null);

  const laad = useCallback(async () => {
    setFout(null);
    try {
      const [a, d] = await Promise.all([api.getDocentaanvragen(filter), api.getDocenten()]);
      setAanvragen(a);
      setDocenten(d);
    } catch (err) {
      setFout(err instanceof Error ? err.message : 'Laden mislukt.');
    }
  }, [filter]);

  useEffect(() => {
    laad();
  }, [laad]);

  const goedkeuren = async (a: DocentAanvraagItem) => {
    setBezig(a.id);
    setMelding(null);
    try {
      await api.keurDocentaanvraagGoed(a.id);
      setMelding(`${a.name} is nu docent. Er is een welkomstmail met inloglink verstuurd naar ${a.email}.`);
      await laad();
    } catch (err) {
      setFout(err instanceof Error ? err.message : 'Goedkeuren mislukt.');
    } finally {
      setBezig(null);
    }
  };

  const afwijzen = async (a: DocentAanvraagItem) => {
    setBezig(a.id);
    setMelding(null);
    try {
      await api.wijsDocentaanvraagAf(a.id, reden.trim() || undefined);
      setMelding(`De aanvraag van ${a.name} is afgewezen.`);
      setAfwijsId(null);
      setReden('');
      await laad();
    } catch (err) {
      setFout(err instanceof Error ? err.message : 'Afwijzen mislukt.');
    } finally {
      setBezig(null);
    }
  };

  const intrekken = async (d: DocentItem) => {
    setBezig(-d.id);
    try {
      await api.trekDocentrolIn(d.id);
      setMelding(`${d.email} is geen docent meer. De klascodes van deze docent werken niet meer.`);
      setIntrekId(null);
      await laad();
    } catch (err) {
      setFout(err instanceof Error ? err.message : 'Intrekken mislukt.');
    } finally {
      setBezig(null);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <GraduationCap className="w-5 h-5 text-amber-800" aria-hidden="true" />
          <h2 className="font-serif text-xl font-bold text-stone-900">Aanvragen docentaccount</h2>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="docent-filter" className="text-xs text-stone-600">
            Toon
          </label>
          <select
            id="docent-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value as 'pending' | 'alle')}
            className="text-sm border border-stone-200 rounded-lg px-2 py-1"
          >
            <option value="pending">Open aanvragen</option>
            <option value="alle">Alle aanvragen</option>
          </select>
          <button
            type="button"
            onClick={laad}
            className="inline-flex items-center gap-1 text-xs font-semibold text-stone-700 border border-stone-200 rounded-lg px-2.5 py-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" /> Verversen
          </button>
        </div>
      </div>

      {melding && (
        <div role="status" className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-900">
          {melding}
        </div>
      )}
      {fout && (
        <div role="alert" className="p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-800">
          {fout}
        </div>
      )}

      {aanvragen.length === 0 ? (
        <p className="text-sm text-stone-600">Er zijn geen {filter === 'pending' ? 'open ' : ''}aanvragen.</p>
      ) : (
        <ul className="space-y-3">
          {aanvragen.map((a) => (
            <li key={a.id} className="bg-white border border-stone-200 rounded-2xl p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="text-sm text-stone-800 space-y-1">
                  <p className="font-semibold text-stone-900">
                    {a.name} <span className="font-normal text-stone-600">({a.email})</span>
                  </p>
                  <p>
                    {a.school}
                    {a.function ? `, ${a.function}` : ''}
                  </p>
                  {a.motivation && <p className="text-stone-600 whitespace-pre-line">{a.motivation}</p>}
                  <p className="text-xs text-stone-500">
                    Aangevraagd {a.created_at ? new Date(a.created_at).toLocaleDateString('nl-NL') : ''} - status:{' '}
                    {a.status === 'pending' ? 'open' : a.status === 'approved' ? 'goedgekeurd' : 'afgewezen'}
                  </p>
                </div>
                {a.status === 'pending' && (
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={bezig === a.id}
                      onClick={() => goedkeuren(a)}
                      className="inline-flex items-center gap-1 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-semibold px-3 py-2 rounded-lg disabled:opacity-50"
                    >
                      <CheckCircle className="w-4 h-4" aria-hidden="true" /> Goedkeuren
                    </button>
                    <button
                      type="button"
                      disabled={bezig === a.id}
                      onClick={() => {
                        setAfwijsId(afwijsId === a.id ? null : a.id);
                        setReden('');
                      }}
                      className="inline-flex items-center gap-1 border border-stone-300 text-stone-700 text-xs font-semibold px-3 py-2 rounded-lg disabled:opacity-50"
                    >
                      <XCircle className="w-4 h-4" aria-hidden="true" /> Afwijzen
                    </button>
                  </div>
                )}
              </div>
              {afwijsId === a.id && (
                <div className="mt-4 pt-4 border-t border-stone-100 space-y-2">
                  <label htmlFor={`reden-${a.id}`} className="block text-xs font-semibold text-stone-700">
                    Reden (optioneel, staat in de mail aan de aanvrager)
                  </label>
                  <textarea
                    id={`reden-${a.id}`}
                    value={reden}
                    onChange={(e) => setReden(e.target.value)}
                    rows={2}
                    maxLength={1000}
                    className="w-full text-sm border border-stone-200 rounded-lg p-2"
                  />
                  <button
                    type="button"
                    disabled={bezig === a.id}
                    onClick={() => afwijzen(a)}
                    className="text-xs font-semibold text-white bg-red-700 hover:bg-red-600 px-3 py-2 rounded-lg disabled:opacity-50"
                  >
                    Bevestig afwijzen
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <div>
        <h2 className="font-serif text-xl font-bold text-stone-900 mb-3">Docenten</h2>
        {docenten.length === 0 ? (
          <p className="text-sm text-stone-600">Nog geen docenten.</p>
        ) : (
          <ul className="divide-y divide-stone-100 bg-white border border-stone-200 rounded-2xl">
            {docenten.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
                <span>
                  <span className="font-semibold text-stone-900">{d.display_name || d.email}</span>{' '}
                  <span className="text-stone-600">({d.email})</span>
                  <span className="text-stone-500"> - {d.aantal_klassen} klas(sen)</span>
                </span>
                {intrekId === d.id ? (
                  <span className="flex items-center gap-2">
                    <span className="text-xs text-red-800">Klascodes werken dan niet meer.</span>
                    <button
                      type="button"
                      disabled={bezig === -d.id}
                      onClick={() => intrekken(d)}
                      className="text-xs font-semibold text-white bg-red-700 rounded-lg px-2.5 py-1.5 disabled:opacity-50"
                    >
                      Ja, intrekken
                    </button>
                    <button type="button" onClick={() => setIntrekId(null)} className="text-xs text-stone-600 underline">
                      Annuleren
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => setIntrekId(d.id)}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 border border-red-200 rounded-lg px-2.5 py-1.5"
                  >
                    <UserX className="w-3.5 h-3.5" aria-hidden="true" /> Docentrol intrekken
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};
