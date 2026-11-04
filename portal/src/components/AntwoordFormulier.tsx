import React, { useEffect, useState } from 'react';
import { MessageSquare, Save } from 'lucide-react';
import { api } from '../api/client';
import type { WerkbladVraag } from '../types';

/**
 * Antwoorden van een leerling op een werkblad (BE-EP-055).
 *
 * Privacy: alleen een voornaam of bijnaam. De browser bewaart een willekeurig token zodat de
 * leerling zijn eigen antwoorden terugziet en kan aanpassen; er is geen account. Antwoorden
 * worden na 8 weken verwijderd.
 */

const TOKEN_SLEUTEL = 'hlm_leerling_token';
const NAAM_SLEUTEL = 'hlm_leerling_naam';

function leesOpslag(sleutel: string): string | null {
  try {
    return window.localStorage.getItem(sleutel);
  } catch {
    return null;
  }
}

function schrijfOpslag(sleutel: string, waarde: string): void {
  try {
    window.localStorage.setItem(sleutel, waarde);
  } catch {
    // Geen opslag (privevenster): het token blijft alleen voor deze pagina bestaan.
  }
}

let geheugenToken: string | null = null;

export function leerlingToken(): string {
  const bewaard = leesOpslag(TOKEN_SLEUTEL);
  if (bewaard && bewaard.length >= 16) return bewaard;
  if (geheugenToken) return geheugenToken;
  const bytes = new Uint8Array(24);
  window.crypto.getRandomValues(bytes);
  const token = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  geheugenToken = token;
  schrijfOpslag(TOKEN_SLEUTEL, token);
  return token;
}

export const AntwoordFormulier: React.FC<{ contentId: number; vragen: WerkbladVraag[] }> = ({ contentId, vragen }) => {
  const [naam, setNaam] = useState(leesOpslag(NAAM_SLEUTEL) || '');
  const [antwoorden, setAntwoorden] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<string | null>(null);
  const [verwijderdNa, setVerwijderdNa] = useState<string | null>(null);
  const [bezig, setBezig] = useState(false);
  const [melding, setMelding] = useState<{ soort: 'ok' | 'fout'; tekst: string } | null>(null);

  useEffect(() => {
    api
      .getMijnAntwoorden(contentId, leerlingToken())
      .then((res) => {
        if (res.naam) setNaam(res.naam);
        setAntwoorden(res.antwoorden || {});
        setFeedback(res.feedback);
        setVerwijderdNa(res.verwijderd_na);
      })
      .catch(() => undefined);
  }, [contentId]);

  const opslaan = async (e: React.FormEvent) => {
    e.preventDefault();
    setBezig(true);
    setMelding(null);
    try {
      const res = await api.slaAntwoordenOp(contentId, leerlingToken(), { naam: naam.trim(), antwoorden });
      schrijfOpslag(NAAM_SLEUTEL, naam.trim());
      setVerwijderdNa(res.verwijderd_na);
      setMelding({ soort: 'ok', tekst: 'Opgeslagen. Je docent kan je antwoorden nu lezen.' });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      const tekst = msg.includes('[403]')
        ? 'Met deze code kun je geen antwoorden opslaan. Vraag je docent om een leerlingcode.'
        : msg.replace(/^API Error \[\d+\]:\s*/, '') || 'Opslaan is niet gelukt. Probeer het opnieuw.';
      setMelding({ soort: 'fout', tekst });
    } finally {
      setBezig(false);
    }
  };

  const secties: Array<{ sectie: string; vragen: WerkbladVraag[] }> = [];
  vragen.forEach((v) => {
    const laatste = secties[secties.length - 1];
    if (laatste && laatste.sectie === v.sectie) laatste.vragen.push(v);
    else secties.push({ sectie: v.sectie, vragen: [v] });
  });

  return (
    <section aria-label="Jouw antwoorden" className="bg-white rounded-2xl p-6 sm:p-8 border border-amber-200 shadow-xs">
      <h2 className="font-serif text-xl font-bold text-stone-900 mb-1 flex items-center gap-2">
        <MessageSquare className="w-5 h-5 text-amber-800" aria-hidden="true" /> Jouw antwoorden
      </h2>
      <p className="text-xs text-stone-600 mb-6">
        Vul alleen je voornaam of een bijnaam in. Alleen je docent ziet je antwoorden. Ze worden na 8 weken
        automatisch verwijderd{verwijderdNa ? ` (op ${new Date(verwijderdNa).toLocaleDateString('nl-NL')})` : ''}.
      </p>

      {feedback && (
        <div className="mb-6 p-4 rounded-xl bg-emerald-50 border border-emerald-200">
          <p className="text-xs font-semibold text-emerald-900 mb-1">Feedback van je docent</p>
          <p className="text-sm text-emerald-950 whitespace-pre-line">{feedback}</p>
        </div>
      )}

      <form onSubmit={opslaan} className="space-y-6">
        <div>
          <label htmlFor="leerling-naam" className="block text-sm font-semibold text-stone-800 mb-1">
            Je voornaam of bijnaam
          </label>
          <input
            id="leerling-naam"
            required
            maxLength={40}
            autoComplete="off"
            value={naam}
            onChange={(e) => setNaam(e.target.value)}
            className="w-full sm:w-72 px-3 py-2 rounded-xl border border-stone-300 focus:outline-none focus:border-amber-700 text-sm"
          />
        </div>

        {secties.map((s) => (
          <fieldset key={s.sectie} className="space-y-4">
            <legend className="font-serif font-bold text-stone-900 mb-2">{s.sectie}</legend>
            {s.vragen.map((v) => (
              <div key={v.sleutel}>
                <label htmlFor={`antwoord-${v.sleutel}`} className="block text-sm text-stone-800 mb-1">
                  {v.tekst}
                </label>
                <textarea
                  id={`antwoord-${v.sleutel}`}
                  rows={3}
                  maxLength={2000}
                  value={antwoorden[v.sleutel] || ''}
                  onChange={(e) => setAntwoorden({ ...antwoorden, [v.sleutel]: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl border border-stone-300 focus:outline-none focus:border-amber-700 text-sm"
                />
              </div>
            ))}
          </fieldset>
        ))}

        {melding && (
          <div
            role={melding.soort === 'fout' ? 'alert' : 'status'}
            className={`p-3 rounded-xl text-sm ${melding.soort === 'fout' ? 'bg-red-50 border border-red-200 text-red-800' : 'bg-emerald-50 border border-emerald-200 text-emerald-900'}`}
          >
            {melding.tekst}
          </div>
        )}

        <button
          type="submit"
          disabled={bezig}
          className="inline-flex items-center gap-2 bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm px-5 py-2.5 rounded-xl disabled:opacity-50"
        >
          <Save className="w-4 h-4" aria-hidden="true" />
          {bezig ? 'Opslaan...' : 'Antwoorden opslaan'}
        </button>
      </form>
    </section>
  );
};
