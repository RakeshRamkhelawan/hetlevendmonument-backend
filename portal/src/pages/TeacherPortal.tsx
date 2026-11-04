import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  GraduationCap,
  KeyRound,
  MessageSquare,
  Plus,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';
import { CaptchaVeld } from '../components/CaptchaVeld';
import type { AntwoordItem, DocentIk, KlasItem, KlasMetCode, LesmateriaalItem, Niveau, WerkbladVraag } from '../types';

/**
 * Docentenportaal (BE-EP-055).
 * - Niet ingelogd: uitleg, inloggen, account aanvragen.
 * - Ingelogd zonder docentrol: status van de aanvraag of het aanvraagformulier.
 * - Docent: klassen met klascodes, lessen per klas, antwoorden met feedback, lesmateriaal als PDF.
 */

const NIVEAU_NAAM: Record<string, string> = { 'groep-7-8': 'Groep 7-8', 'onderbouw-vo': 'Onderbouw VO' };
const GELDIGHEID: Array<[number, string]> = [
  [1, '1 dag'],
  [7, '1 week'],
  [28, '4 weken'],
  [90, '3 maanden'],
  [180, '6 maanden'],
];

const datum = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString('nl-NL') : '');

const foutTekst = (err: unknown, standaard: string) => {
  const msg = err instanceof Error ? err.message : '';
  const detail = msg.replace(/^API Error \[\d+\]:\s*/, '');
  return detail && detail !== msg ? detail : standaard;
};

// ---------------------------------------------------------------------------- aanvraag

const AanvraagFormulier: React.FC<{ standaardEmail?: string }> = ({ standaardEmail = '' }) => {
  const [naam, setNaam] = useState('');
  const [email, setEmail] = useState(standaardEmail);
  const [school, setSchool] = useState('');
  const [functie, setFunctie] = useState('');
  const [toelichting, setToelichting] = useState('');
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [bezig, setBezig] = useState(false);
  const [klaar, setKlaar] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  const verstuur = async (e: React.FormEvent) => {
    e.preventDefault();
    setBezig(true);
    setFout(null);
    try {
      await api.vraagDocentaccountAan({
        name: naam.trim(),
        email: email.trim(),
        school: school.trim(),
        function: functie.trim() || undefined,
        motivation: toelichting.trim() || undefined,
        hcaptcha_token: captcha || undefined,
      });
      setKlaar(true);
    } catch (err) {
      setFout(foutTekst(err, 'Versturen is niet gelukt. Probeer het later opnieuw.'));
    } finally {
      setBezig(false);
    }
  };

  if (klaar) {
    return (
      <div role="status" className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-900">
        Dank u wel. Uw aanvraag is ontvangen. Na goedkeuring krijgt u een e-mail met een link om in te loggen.
      </div>
    );
  }

  const veld = 'w-full px-3 py-2 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm';
  return (
    <form onSubmit={verstuur} className="space-y-4" aria-label="Docentaccount aanvragen">
      {fout && (
        <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl">
          {fout}
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor="aanvraag-naam" className="block text-xs font-semibold text-stone-700 mb-1">
            Naam *
          </label>
          <input id="aanvraag-naam" required minLength={2} maxLength={200} value={naam} onChange={(e) => setNaam(e.target.value)} className={veld} />
        </div>
        <div>
          <label htmlFor="aanvraag-email" className="block text-xs font-semibold text-stone-700 mb-1">
            E-mailadres van school *
          </label>
          <input id="aanvraag-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={veld} />
        </div>
        <div>
          <label htmlFor="aanvraag-school" className="block text-xs font-semibold text-stone-700 mb-1">
            School *
          </label>
          <input id="aanvraag-school" required minLength={2} maxLength={200} value={school} onChange={(e) => setSchool(e.target.value)} className={veld} />
        </div>
        <div>
          <label htmlFor="aanvraag-functie" className="block text-xs font-semibold text-stone-700 mb-1">
            Functie (bijv. leerkracht groep 8)
          </label>
          <input id="aanvraag-functie" maxLength={200} value={functie} onChange={(e) => setFunctie(e.target.value)} className={veld} />
        </div>
      </div>
      <div>
        <label htmlFor="aanvraag-toelichting" className="block text-xs font-semibold text-stone-700 mb-1">
          Hoe wilt u het lesmateriaal gebruiken? (optioneel)
        </label>
        <textarea id="aanvraag-toelichting" rows={3} maxLength={2000} value={toelichting} onChange={(e) => setToelichting(e.target.value)} className={veld} />
      </div>
      <CaptchaVeld onToken={setCaptcha} />
      <p className="text-xs text-stone-500">
        Wij gebruiken uw gegevens alleen om uw aanvraag te beoordelen en uw account te beheren. Zie de{' '}
        <Link to="/privacy" className="text-amber-800 underline">
          privacyverklaring
        </Link>
        .
      </p>
      <button
        type="submit"
        disabled={bezig}
        className="bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm px-5 py-2.5 rounded-xl disabled:opacity-50"
      >
        {bezig ? 'Versturen...' : 'Aanvraag versturen'}
      </button>
    </form>
  );
};

// ---------------------------------------------------------------------------- klas maken

const KlasMaken: React.FC<{ onGemaakt: (k: KlasMetCode) => void }> = ({ onGemaakt }) => {
  const [naam, setNaam] = useState('');
  const [niveau, setNiveau] = useState<Niveau>('groep-7-8');
  const [dagen, setDagen] = useState(28);
  const [bezig, setBezig] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  const maak = async (e: React.FormEvent) => {
    e.preventDefault();
    setBezig(true);
    setFout(null);
    try {
      const klas = await api.maakKlas({ naam: naam.trim(), niveau, geldig_dagen: dagen });
      setNaam('');
      onGemaakt(klas);
    } catch (err) {
      setFout(foutTekst(err, 'De klas kon niet worden gemaakt.'));
    } finally {
      setBezig(false);
    }
  };

  const veld = 'w-full px-3 py-2 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-white';
  return (
    <form onSubmit={maak} className="bg-stone-50 border border-stone-200 rounded-2xl p-5 space-y-4" aria-label="Nieuwe klas">
      <h3 className="font-serif font-bold text-stone-900 flex items-center gap-2">
        <Plus className="w-4 h-4 text-amber-800" aria-hidden="true" /> Nieuwe klas
      </h3>
      {fout && (
        <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl">
          {fout}
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label htmlFor="klas-naam" className="block text-xs font-semibold text-stone-700 mb-1">
            Naam van de klas
          </label>
          <input id="klas-naam" required maxLength={100} placeholder="Bijv. groep 8B" value={naam} onChange={(e) => setNaam(e.target.value)} className={veld} />
        </div>
        <div>
          <label htmlFor="klas-niveau" className="block text-xs font-semibold text-stone-700 mb-1">
            Niveau
          </label>
          <select id="klas-niveau" value={niveau} onChange={(e) => setNiveau(e.target.value as Niveau)} className={veld}>
            <option value="groep-7-8">Groep 7-8</option>
            <option value="onderbouw-vo">Onderbouw VO</option>
          </select>
        </div>
        <div>
          <label htmlFor="klas-geldig" className="block text-xs font-semibold text-stone-700 mb-1">
            Klascode geldig
          </label>
          <select id="klas-geldig" value={dagen} onChange={(e) => setDagen(Number(e.target.value))} className={veld}>
            {GELDIGHEID.map(([d, label]) => (
              <option key={d} value={d}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="text-xs text-stone-500">Alle werkbladen van het niveau staan open. Dat kunt u daarna per klas aanpassen.</p>
      <button type="submit" disabled={bezig} className="bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm px-5 py-2.5 rounded-xl disabled:opacity-50">
        {bezig ? 'Bezig...' : 'Klas en klascode maken'}
      </button>
    </form>
  );
};

const CodeMelding: React.FC<{ klas: KlasMetCode; onSluit: () => void }> = ({ klas, onSluit }) => {
  const [gekopieerd, setGekopieerd] = useState(false);
  const kopieer = () => {
    navigator.clipboard?.writeText(klas.code).catch(() => undefined);
    setGekopieerd(true);
    setTimeout(() => setGekopieerd(false), 3000);
  };
  return (
    <div role="status" className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 space-y-3">
      <p className="text-sm text-emerald-950">
        Klascode voor <strong>{klas.naam}</strong>, geldig tot {datum(klas.verloopt_op)}:
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-3xl font-bold tracking-[0.3em] text-emerald-950 bg-white border border-emerald-200 rounded-xl px-4 py-2" data-testid="klascode">
          {klas.code}
        </span>
        <button type="button" onClick={kopieer} className="inline-flex items-center gap-1 text-sm font-semibold text-emerald-900 border border-emerald-300 rounded-lg px-3 py-2">
          {gekopieerd ? <Check className="w-4 h-4" aria-hidden="true" /> : <Copy className="w-4 h-4" aria-hidden="true" />}
          {gekopieerd ? 'Gekopieerd' : 'Kopieer'}
        </button>
      </div>
      <p className="text-xs text-emerald-900">
        Leerlingen gaan naar hetlevendmonument.nl/educatie en vullen deze code in. Schrijf de code op: u ziet hem maar
        een keer. Kwijt? Maak dan een nieuwe code voor dezelfde klas.
      </p>
      <button type="button" onClick={onSluit} className="text-xs text-emerald-900 underline">
        Sluiten
      </button>
    </div>
  );
};

// ---------------------------------------------------------------------------- per klas

const LessenKiezer: React.FC<{
  klas: KlasItem;
  werkbladen: LesmateriaalItem[];
  onOpgeslagen: (k: KlasItem) => void;
}> = ({ klas, werkbladen, onOpgeslagen }) => {
  const [gekozen, setGekozen] = useState<Set<number>>(new Set(klas.les_ids));
  const [bezig, setBezig] = useState(false);
  const [melding, setMelding] = useState<string | null>(null);
  const eigenNiveau = werkbladen.filter((w) => w.target_age_group === klas.niveau);
  const anderNiveau = werkbladen.filter((w) => w.target_age_group !== klas.niveau);

  const wissel = (id: number) => {
    const nieuw = new Set(gekozen);
    if (nieuw.has(id)) nieuw.delete(id);
    else nieuw.add(id);
    setGekozen(nieuw);
  };

  const opslaan = async () => {
    setBezig(true);
    setMelding(null);
    try {
      const k = await api.zetKlaslessen(klas.id, Array.from(gekozen));
      onOpgeslagen(k);
      setMelding('Opgeslagen. Leerlingen zien nu alleen de aangevinkte lessen.');
    } catch (err) {
      setMelding(foutTekst(err, 'Opslaan mislukt.'));
    } finally {
      setBezig(false);
    }
  };

  const lijst = (items: LesmateriaalItem[]) => (
    <ul className="space-y-1.5">
      {items.map((w) => (
        <li key={w.id}>
          <label className="flex items-start gap-2 text-sm text-stone-800">
            <input type="checkbox" checked={gekozen.has(w.id)} onChange={() => wissel(w.id)} className="mt-1" />
            <span>{w.title}</span>
          </label>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="space-y-3">
      <p className="text-xs text-stone-600">Vink aan welke werkbladen deze klas ziet. De rest is voor deze klas verborgen.</p>
      {lijst(eigenNiveau)}
      {anderNiveau.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-stone-600">Werkbladen van het andere niveau</summary>
          <div className="mt-2">{lijst(anderNiveau)}</div>
        </details>
      )}
      <div className="flex items-center gap-3">
        <button type="button" disabled={bezig} onClick={opslaan} className="bg-amber-800 hover:bg-amber-700 text-white text-xs font-semibold px-4 py-2 rounded-lg disabled:opacity-50">
          Lessen opslaan
        </button>
        {melding && (
          <span role="status" className="text-xs text-stone-700">
            {melding}
          </span>
        )}
      </div>
    </div>
  );
};

const FeedbackVeld: React.FC<{ antwoord: AntwoordItem; onOpgeslagen: (a: AntwoordItem) => void }> = ({ antwoord, onOpgeslagen }) => {
  const [tekst, setTekst] = useState(antwoord.feedback || '');
  const [bezig, setBezig] = useState(false);
  const [melding, setMelding] = useState<string | null>(null);
  const opslaan = async () => {
    setBezig(true);
    setMelding(null);
    try {
      onOpgeslagen(await api.geefFeedback(antwoord.id, tekst));
      setMelding('Feedback opgeslagen. De leerling ziet die bij het werkblad.');
    } catch (err) {
      setMelding(foutTekst(err, 'Opslaan mislukt.'));
    } finally {
      setBezig(false);
    }
  };
  return (
    <div className="space-y-2">
      <label htmlFor={`feedback-${antwoord.id}`} className="block text-xs font-semibold text-stone-700">
        Feedback voor {antwoord.leerling}
      </label>
      <textarea id={`feedback-${antwoord.id}`} rows={2} maxLength={2000} value={tekst} onChange={(e) => setTekst(e.target.value)} className="w-full text-sm border border-stone-200 rounded-lg p-2" />
      <div className="flex items-center gap-3">
        <button type="button" disabled={bezig} onClick={opslaan} className="text-xs font-semibold text-white bg-stone-800 hover:bg-stone-700 px-3 py-1.5 rounded-lg disabled:opacity-50">
          Feedback opslaan
        </button>
        {melding && <span className="text-xs text-stone-600">{melding}</span>}
      </div>
    </div>
  );
};

const AntwoordenLijst: React.FC<{ klas: KlasItem; werkbladen: LesmateriaalItem[]; vragen: Record<number, WerkbladVraag[]> }> = ({
  klas,
  werkbladen,
  vragen,
}) => {
  const lessen = werkbladen.filter((w) => klas.les_ids.includes(w.id));
  const [lesId, setLesId] = useState<number | null>(lessen[0]?.id ?? null);
  const [antwoorden, setAntwoorden] = useState<AntwoordItem[]>([]);
  const [laden, setLaden] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  useEffect(() => {
    if (!lesId) return;
    setLaden(true);
    setFout(null);
    api
      .getKlasantwoorden(klas.id, lesId)
      .then(setAntwoorden)
      .catch((err) => setFout(foutTekst(err, 'Laden mislukt.')))
      .finally(() => setLaden(false));
  }, [klas.id, lesId]);

  if (lessen.length === 0) return <p className="text-sm text-stone-600">Deze klas heeft nog geen lessen open.</p>;
  const vraagTekst = (sleutel: string) => (lesId ? vragen[lesId]?.find((v) => v.sleutel === sleutel) : undefined);

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor={`antwoorden-les-${klas.id}`} className="block text-xs font-semibold text-stone-700 mb-1">
          Werkblad
        </label>
        <select id={`antwoorden-les-${klas.id}`} value={lesId ?? ''} onChange={(e) => setLesId(Number(e.target.value))} className="text-sm border border-stone-200 rounded-lg px-2 py-1.5 bg-white max-w-full">
          {lessen.map((w) => (
            <option key={w.id} value={w.id}>
              {w.title}
            </option>
          ))}
        </select>
      </div>
      {fout && <p role="alert" className="text-sm text-red-700">{fout}</p>}
      {laden ? (
        <p className="text-sm text-stone-600">Laden...</p>
      ) : antwoorden.length === 0 ? (
        <p className="text-sm text-stone-600">Nog geen antwoorden op dit werkblad.</p>
      ) : (
        <ul className="space-y-4">
          {antwoorden.map((a) => (
            <li key={a.id} className="bg-white border border-stone-200 rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-stone-900">
                {a.leerling} <span className="font-normal text-xs text-stone-500">- bijgewerkt {datum(a.bijgewerkt_op)}, wordt verwijderd na {datum(a.verwijderd_na)}</span>
              </p>
              <dl className="space-y-2 text-sm">
                {Object.entries(a.antwoorden).map(([sleutel, tekst]) => (
                  <div key={sleutel}>
                    <dt className="text-xs font-semibold text-stone-600">{vraagTekst(sleutel)?.tekst || sleutel}</dt>
                    <dd className="text-stone-900 whitespace-pre-line">{tekst}</dd>
                  </div>
                ))}
              </dl>
              <FeedbackVeld antwoord={a} onOpgeslagen={(nieuw) => setAntwoorden(antwoorden.map((x) => (x.id === nieuw.id ? nieuw : x)))} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const KlasKaart: React.FC<{
  klas: KlasItem;
  werkbladen: LesmateriaalItem[];
  vragen: Record<number, WerkbladVraag[]>;
  onBijgewerkt: (k: KlasItem) => void;
  onNieuweCode: (k: KlasMetCode) => void;
}> = ({ klas, werkbladen, vragen, onBijgewerkt, onNieuweCode }) => {
  const [open, setOpen] = useState<'lessen' | 'antwoorden' | null>(null);
  const [bezig, setBezig] = useState(false);
  const [intrekVraag, setIntrekVraag] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  const nieuweCode = async () => {
    setBezig(true);
    setFout(null);
    try {
      onNieuweCode(await api.nieuweKlascode(klas.id, 28));
    } catch (err) {
      setFout(foutTekst(err, 'Nieuwe code maken mislukt.'));
    } finally {
      setBezig(false);
    }
  };

  const intrekken = async () => {
    setBezig(true);
    setFout(null);
    try {
      onBijgewerkt(await api.trekKlascodeIn(klas.id));
      setIntrekVraag(false);
    } catch (err) {
      setFout(foutTekst(err, 'Intrekken mislukt.'));
    } finally {
      setBezig(false);
    }
  };

  return (
    <li className="bg-white border border-stone-200 rounded-2xl p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-serif font-bold text-stone-900">{klas.naam}</h3>
          <p className="text-xs text-stone-600">
            {NIVEAU_NAAM[klas.niveau || ''] || 'Niveau onbekend'} - {klas.les_ids.length} les(sen) open - {klas.aantal_antwoorden} antwoord(en)
          </p>
          <p className={`text-xs font-semibold ${klas.actief ? 'text-emerald-800' : 'text-stone-500'}`}>
            {klas.actief ? `Klascode werkt tot ${datum(klas.verloopt_op)}` : 'Klascode werkt niet meer'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setOpen(open === 'lessen' ? null : 'lessen')} aria-expanded={open === 'lessen'} className="inline-flex items-center gap-1 text-xs font-semibold border border-stone-200 rounded-lg px-2.5 py-1.5">
            <BookOpen className="w-3.5 h-3.5" aria-hidden="true" /> Lessen {open === 'lessen' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          <button type="button" onClick={() => setOpen(open === 'antwoorden' ? null : 'antwoorden')} aria-expanded={open === 'antwoorden'} className="inline-flex items-center gap-1 text-xs font-semibold border border-stone-200 rounded-lg px-2.5 py-1.5">
            <MessageSquare className="w-3.5 h-3.5" aria-hidden="true" /> Antwoorden {open === 'antwoorden' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          <button type="button" disabled={bezig} onClick={nieuweCode} className="inline-flex items-center gap-1 text-xs font-semibold border border-stone-200 rounded-lg px-2.5 py-1.5 disabled:opacity-50">
            <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" /> Nieuwe code
          </button>
          {klas.actief &&
            (intrekVraag ? (
              <span className="inline-flex items-center gap-2">
                <button type="button" disabled={bezig} onClick={intrekken} className="text-xs font-semibold text-white bg-red-700 rounded-lg px-2.5 py-1.5">
                  Ja, code uitzetten
                </button>
                <button type="button" onClick={() => setIntrekVraag(false)} className="text-xs underline text-stone-600">
                  Annuleren
                </button>
              </span>
            ) : (
              <button type="button" onClick={() => setIntrekVraag(true)} className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 border border-red-200 rounded-lg px-2.5 py-1.5">
                <XCircle className="w-3.5 h-3.5" aria-hidden="true" /> Code uitzetten
              </button>
            ))}
        </div>
      </div>
      {fout && <p role="alert" className="text-sm text-red-700">{fout}</p>}
      {open === 'lessen' && <LessenKiezer klas={klas} werkbladen={werkbladen} onOpgeslagen={onBijgewerkt} />}
      {open === 'antwoorden' && <AntwoordenLijst klas={klas} werkbladen={werkbladen} vragen={vragen} />}
    </li>
  );
};

// ---------------------------------------------------------------------------- lesmateriaal

const LesmateriaalLijst: React.FC<{ items: LesmateriaalItem[] }> = ({ items }) => {
  const [fout, setFout] = useState<string | null>(null);
  const download = async (item: LesmateriaalItem) => {
    setFout(null);
    try {
      const blob = await api.downloadLesPdf(item.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${item.title.replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase()}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setFout('De PDF kon niet worden gemaakt. Probeer het later opnieuw.');
    }
  };
  const groepen = ['groep-7-8', 'onderbouw-vo'].map((n) => ({ n, items: items.filter((i) => i.target_age_group === n) }));
  return (
    <div className="space-y-6">
      {fout && <p role="alert" className="text-sm text-red-700">{fout}</p>}
      {groepen.map(({ n, items: lijst }) =>
        lijst.length === 0 ? null : (
          <div key={n}>
            <h3 className="font-serif font-bold text-stone-800 mb-2">{NIVEAU_NAAM[n]}</h3>
            <ul className="divide-y divide-stone-100 bg-white border border-stone-200 rounded-2xl">
              {lijst.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
                  <Link to={`/item/${i.id}`} className="text-stone-900 hover:text-amber-800 hover:underline">
                    {i.title}
                  </Link>
                  <button type="button" onClick={() => download(i)} className="inline-flex items-center gap-1 text-xs font-semibold text-amber-800 border border-amber-200 rounded-lg px-2.5 py-1.5">
                    <Download className="w-3.5 h-3.5" aria-hidden="true" /> PDF
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ),
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------- dashboard

const DocentDashboard: React.FC<{ ik: DocentIk }> = ({ ik }) => {
  const [klassen, setKlassen] = useState<KlasItem[]>([]);
  const [materiaal, setMateriaal] = useState<LesmateriaalItem[]>([]);
  const [vragen, setVragen] = useState<Record<number, WerkbladVraag[]>>({});
  const [nieuweCode, setNieuweCode] = useState<KlasMetCode | null>(null);
  const [fout, setFout] = useState<string | null>(null);

  const werkbladen = useMemo(() => materiaal.filter((m) => m.type === 'educational_workbook'), [materiaal]);

  const laad = useCallback(async () => {
    try {
      const [k, m] = await Promise.all([api.getKlassen(), api.getLesmateriaal()]);
      setKlassen(k);
      setMateriaal(m);
    } catch (err) {
      setFout(foutTekst(err, 'Laden mislukt.'));
    }
  }, []);

  useEffect(() => {
    laad();
  }, [laad]);

  // De vraagteksten (voor de antwoordenlijst) staan in de metadata van elk werkblad.
  useEffect(() => {
    werkbladen.forEach((w) => {
      if (vragen[w.id]) return;
      api
        .getLesmateriaalDetail(w.id)
        .then((d) => {
          const v = (d.metadata?.vragen as WerkbladVraag[] | undefined) || [];
          setVragen((oud) => ({ ...oud, [w.id]: v }));
        })
        .catch(() => undefined);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [werkbladen]);

  const vervang = (k: KlasItem) => setKlassen((oud) => oud.map((x) => (x.id === k.id ? { ...x, ...k } : x)));

  return (
    <div className="space-y-10">
      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-stone-200 space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-900 flex items-center justify-center">
            <KeyRound className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h2 className="font-serif text-xl font-bold text-stone-900">Mijn klassen</h2>
            <p className="text-xs text-stone-500">Ingelogd als {ik.display_name || ik.email}</p>
          </div>
        </div>
        {fout && <p role="alert" className="text-sm text-red-700">{fout}</p>}
        {nieuweCode && <CodeMelding klas={nieuweCode} onSluit={() => setNieuweCode(null)} />}
        <KlasMaken
          onGemaakt={(k) => {
            setNieuweCode(k);
            setKlassen((oud) => [k, ...oud]);
          }}
        />
        {klassen.length === 0 ? (
          <p className="text-sm text-stone-600">U heeft nog geen klassen.</p>
        ) : (
          <ul className="space-y-4">
            {klassen.map((k) => (
              <KlasKaart
                key={k.id}
                klas={k}
                werkbladen={werkbladen}
                vragen={vragen}
                onBijgewerkt={vervang}
                onNieuweCode={(nk) => {
                  setNieuweCode(nk);
                  vervang(nk);
                }}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-stone-200 space-y-4">
        <h2 className="font-serif text-xl font-bold text-stone-900">Lesmateriaal: Vijf verhalen over vrijheid</h2>
        <p className="text-sm text-stone-600">Docentenhandleidingen en werkbladen, ook als printbare PDF.</p>
        <LesmateriaalLijst items={materiaal} />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------- pagina

export const TeacherPortal: React.FC = () => {
  const [ik, setIk] = useState<DocentIk | null>(null);
  const [laden, setLaden] = useState(true);

  useEffect(() => {
    if (!api.getAuthToken()) {
      setLaden(false);
      return;
    }
    api
      .getDocentIk()
      .then(setIk)
      .catch(() => setIk(null))
      .finally(() => setLaden(false));
  }, []);

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-semibold uppercase tracking-wider mb-3">
            <GraduationCap className="w-4 h-4 text-amber-800" aria-hidden="true" />
            Voor scholen en docenten
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-stone-900 mb-3">Docentenportaal</h1>
          <p className="text-stone-600 text-sm leading-relaxed">
            Maak klassen en klascodes, kies welke lessen uw leerlingen zien en lees hun antwoorden. Met het lesmateriaal
            &quot;Vijf verhalen over vrijheid&quot; voor groep 7-8 en de onderbouw van het voortgezet onderwijs.
          </p>
        </div>

        {laden ? (
          <p className="text-center text-sm text-stone-600">Laden...</p>
        ) : ik?.is_docent ? (
          <DocentDashboard ik={ik} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-2 bg-white rounded-3xl p-6 border border-stone-200 space-y-3 h-fit">
              <h2 className="font-serif text-lg font-bold text-stone-900">Al een docentaccount?</h2>
              {ik ? (
                <p className="text-sm text-stone-700">
                  U bent ingelogd als {ik.email}, maar dit is nog geen docentaccount.
                  {ik.aanvraag_status === 'pending' && ' Uw aanvraag wordt bekeken; u krijgt bericht per e-mail.'}
                  {ik.aanvraag_status === 'rejected' && ' Uw vorige aanvraag is niet goedgekeurd. U kunt een nieuwe aanvraag doen.'}
                </p>
              ) : (
                <>
                  <p className="text-sm text-stone-700">Log in met uw e-mailadres. U krijgt een inloglink per e-mail.</p>
                  <Link to="/inloggen?redirect=/docenten" className="inline-block bg-stone-900 hover:bg-stone-800 text-white text-sm font-semibold px-4 py-2 rounded-xl">
                    Inloggen
                  </Link>
                </>
              )}
              <p className="text-xs text-stone-500 pt-2">
                Leerling? Ga naar{' '}
                <Link to="/educatie" className="text-amber-800 underline">
                  de leerlingomgeving
                </Link>{' '}
                en vul de klascode van uw docent in.
              </p>
            </div>
            <div className="lg:col-span-3 bg-white rounded-3xl p-6 border border-stone-200 space-y-4">
              <h2 className="font-serif text-lg font-bold text-stone-900">Docentaccount aanvragen</h2>
              {ik?.aanvraag_status === 'pending' ? (
                <p className="text-sm text-stone-700">Uw aanvraag is ontvangen en wordt bekeken.</p>
              ) : (
                <>
                  <p className="text-sm text-stone-700">
                    Met een docentaccount maakt u klascodes, zet u lessen open en leest u de antwoorden van uw leerlingen.
                    De stichting keurt elke aanvraag zelf goed.
                  </p>
                  <AanvraagFormulier standaardEmail={ik?.email} />
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
