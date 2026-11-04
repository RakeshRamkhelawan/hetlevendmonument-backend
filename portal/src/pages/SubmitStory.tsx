import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, AlertCircle, MapPin, ShieldCheck, Sparkles, ArrowRight, Mail, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { CaptchaVeld } from '../components/CaptchaVeld';
import { BestandKiezer } from '../components/BestandKiezer';
import { PlekKiezer, type Plek } from '../components/PlekKiezer';
import { onthoudNaInloggen } from '../naInloggen';

/** Tekstvelden van een verhaal in wording; blijft bewaard als de pagina herlaadt (BE-EP-056). */
const CONCEPT_SLEUTEL = 'hlm_verhaal_concept';

interface Concept {
  title: string;
  category: string;
  body: string;
  authorName: string;
  isAnonymous: boolean;
  locationName: string;
  plek: Plek | null;
}

const LEEG: Concept = {
  title: '',
  category: 'verhalen',
  body: '',
  authorName: '',
  isAnonymous: false,
  locationName: '',
  plek: null,
};

const leesConcept = (): Concept => {
  try {
    const ruw = localStorage.getItem(CONCEPT_SLEUTEL);
    return ruw ? { ...LEEG, ...(JSON.parse(ruw) as Partial<Concept>) } : LEEG;
  } catch {
    return LEEG;
  }
};

const categories = [
  { id: 'verhalen', label: 'Persoonlijk Verhaal' },
  { id: 'herdenking', label: 'Herdenking & Monumenten' },
  { id: 'educatie', label: 'Educatief Erfgoed' },
  { id: 'kunst', label: 'Kunst & Expressie' },
  { id: 'archief', label: 'Historisch Document / Foto' },
];

/** Soort inhoud bij het gekozen bestand. */
const soortVoorBestand = (bestand: File | null): string => {
  if (!bestand) return 'text';
  if (bestand.type.startsWith('audio/')) return 'audio';
  return 'image';
};

/** Foutmelding van de server in gewone taal. */
const leesbareFout = (err: unknown, standaard: string): string => {
  const tekst = err instanceof Error ? err.message : '';
  if (/captcha/i.test(tekst)) return "Vink eerst het vakje 'Ik ben een mens' aan, wacht op het vinkje en probeer het opnieuw.";
  if (/File type not allowed/i.test(tekst)) return 'Dit soort bestand kunnen we niet opslaan. Kies een foto, geluidsopname, video of PDF.';
  if (/could not be processed/i.test(tekst)) return 'Dit bestand kunnen we niet lezen. Probeer een ander bestand.';
  if (/413|too large|te groot/i.test(tekst)) return 'Dit bestand is te groot. Kies een bestand kleiner dan 50 MB.';
  if (/401|unauthor|expired|verlopen/i.test(tekst)) return 'U bent niet meer ingelogd. Vraag een nieuwe inloglink aan.';
  return standaard;
};

const veld =
  'w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 bg-stone-50/50 text-stone-900 text-sm';
const label = 'block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5';

/** Stap 1 voor wie niet is ingelogd: e-mailadres en inloglink (BE-EP-056). */
const AanmeldStap: React.FC = () => {
  const [email, setEmail] = useState('');
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [bezig, setBezig] = useState(false);
  const [verstuurd, setVerstuurd] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  const verstuur = async (e: React.FormEvent) => {
    e.preventDefault();
    setBezig(true);
    setFout(null);
    try {
      onthoudNaInloggen('/uploaden');
      await api.requestMagicLink(email.trim(), captcha, { aanmelden: true });
      setVerstuurd(true);
    } catch (err: unknown) {
      setFout(leesbareFout(err, 'Het versturen van de inloglink is niet gelukt. Probeer het opnieuw.'));
    } finally {
      setBezig(false);
    }
  };

  if (verstuurd) {
    return (
      <div role="status" className="text-center space-y-4">
        <div className="w-14 h-14 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto">
          <Mail className="w-7 h-7" aria-hidden="true" />
        </div>
        <h2 className="font-serif text-2xl font-bold text-stone-900">Kijk in uw e-mail</h2>
        <p className="text-stone-700 text-sm leading-relaxed max-w-md mx-auto">
          We hebben een inloglink gestuurd naar <strong>{email.trim()}</strong>. Klik op de link in de e-mail. U komt
          dan terug op deze pagina en kunt uw verhaal insturen. De link werkt 15 minuten.
        </p>
        <p className="text-stone-600 text-xs">
          Geen e-mail gekregen? Kijk in de map met ongewenste mail, of{' '}
          <button type="button" onClick={() => setVerstuurd(false)} className="font-semibold text-amber-800 underline">
            vraag een nieuwe link aan
          </button>
          .
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={verstuur} className="space-y-5" aria-label="Inloglink aanvragen om een verhaal in te sturen">
      <div>
        <h2 className="font-serif text-2xl font-bold text-stone-900 mb-2">Stap 1: uw e-mailadres</h2>
        <p className="text-stone-700 text-sm leading-relaxed">
          Om een verhaal met foto of geluid in te sturen, hebt u een inloglink nodig. U hoeft geen wachtwoord te
          onthouden. Met dezelfde link volgt u later de status van uw verhaal.
        </p>
      </div>
      {fout && (
        <div role="alert" className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex gap-2">
          <AlertCircle className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
          <span>{fout}</span>
        </div>
      )}
      <div>
        <label htmlFor="aanmeld-email" className={label}>
          Uw e-mailadres <span className="text-red-600" aria-hidden="true">*</span>
        </label>
        <input
          id="aanmeld-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="naam@voorbeeld.nl"
          className={veld}
        />
      </div>
      <CaptchaVeld onToken={setCaptcha} />
      <button
        type="submit"
        disabled={bezig || !email.trim()}
        className="w-full bg-amber-800 hover:bg-amber-700 text-white font-semibold text-base py-3 px-6 rounded-2xl disabled:opacity-50 flex items-center justify-center gap-2"
      >
        <Mail className="w-5 h-5" aria-hidden="true" />
        {bezig ? 'Versturen...' : 'Stuur mij een inloglink'}
      </button>
    </form>
  );
};

export const SubmitStory: React.FC = () => {
  const [ingelogd, setIngelogd] = useState(() => !!api.getAuthToken());
  const [concept, setConcept] = useState<Concept>(leesConcept);
  // BE-EP-057: tot MAX_BESTANDEN bestanden; na een mislukte upload blijven alleen die over.
  const [bestanden, setBestanden] = useState<File[]>([]);
  const [consentGiven, setConsentGiven] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [voortgang, setVoortgang] = useState<string | null>(null);
  const [submittedId, setSubmittedId] = useState<string | null>(null);
  const [uploadFout, setUploadFout] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(CONCEPT_SLEUTEL, JSON.stringify(concept));
    } catch {
      // Opslag niet beschikbaar: het concept blijft alleen in deze pagina.
    }
  }, [concept]);

  const zet = <K extends keyof Concept>(sleutel: K, waarde: Concept[K]) =>
    setConcept((c) => ({ ...c, [sleutel]: waarde }));

  /**
   * Bestanden na elkaar uploaden (BE-EP-057). Steeds met extra=true: de server maakt het
   * eerste geslaagde bestand het hoofdbestand en de rest extra bestanden. Wat mislukt,
   * blijft staan om opnieuw te proberen.
   */
  const uploadBestanden = async (id: string, lijst: File[]) => {
    setUploadFout(null);
    const mislukt: File[] = [];
    let laatsteFout: unknown = null;
    for (let i = 0; i < lijst.length; i++) {
      setVoortgang(lijst.length > 1 ? `Bestand ${i + 1} van ${lijst.length} wordt opgeslagen...` : 'Uw bestand wordt opgeslagen...');
      try {
        await api.uploadMedia(id, lijst[i], { extra: true });
      } catch (err: unknown) {
        mislukt.push(lijst[i]);
        laatsteFout = err;
      }
    }
    setBestanden(mislukt);
    if (mislukt.length > 0) {
      setUploadFout(leesbareFout(laatsteFout, 'Het bestand kon niet worden opgeslagen. Probeer het opnieuw.'));
    }
    setVoortgang(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!consentGiven) {
      setErrorMessage('U dient akkoord te gaan met de voorwaarden voor open erfgoed en publicatie.');
      return;
    }
    setSubmitting(true);
    setErrorMessage(null);
    try {
      setVoortgang('Uw verhaal wordt opgeslagen...');
      const res = await api.submitContent({
        title: concept.title,
        category: concept.category,
        body: concept.body,
        author_name: concept.isAnonymous ? undefined : concept.authorName || undefined,
        is_anonymous: concept.isAnonymous,
        location_name: concept.locationName || undefined,
        latitude: concept.plek?.lat,
        longitude: concept.plek?.lng,
        media_type: soortVoorBestand(bestanden[0] ?? null),
      });
      setSubmittedId(res.id);
      try {
        localStorage.removeItem(CONCEPT_SLEUTEL);
      } catch {
        // niets
      }
      if (bestanden.length > 0) await uploadBestanden(res.id, bestanden);
    } catch (err: unknown) {
      if (err instanceof Error && /401|unauthor|expired|verlopen/i.test(err.message)) {
        // Inlog verlopen: terug naar stap 1. Het concept blijft bewaard.
        api.clearAuthToken();
        setIngelogd(false);
        return;
      }
      setErrorMessage(leesbareFout(err, 'Er is iets misgegaan bij het versturen. Controleer uw invoer en probeer opnieuw.'));
    } finally {
      setVoortgang(null);
      setSubmitting(false);
    }
  };

  if (submittedId) {
    return (
      <div className="min-h-[80vh] flex items-center justify-center py-16 px-4 bg-[#FDFBF7]">
        <div className="max-w-xl w-full bg-white rounded-3xl p-8 sm:p-10 border border-stone-200 shadow-sm text-center">
          <div className="w-16 h-16 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto mb-6 shadow-inner">
            <CheckCircle2 className="w-8 h-8" />
          </div>
          <h2 className="font-serif text-3xl font-bold text-stone-900 mb-3">Hartelijk dank voor uw inzending!</h2>
          <p className="text-stone-600 leading-relaxed mb-6">
            Uw verhaal is opgeslagen en ligt nu bij de curatoren van de stichting. Zodra het is beoordeeld, komt het op
            Het Levend Monument. De status ziet u bij Mijn Inzendingen.
          </p>
          {voortgang && (
            <p role="status" className="mb-4 text-sm text-stone-700">
              {voortgang}
            </p>
          )}
          {uploadFout && bestanden.length > 0 && (
            <div role="alert" className="mb-6 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-sm text-left space-y-3">
              <p>
                Uw verhaal is opgeslagen, maar{' '}
                {bestanden.length === 1 ? 'een bestand nog niet' : `${bestanden.length} bestanden nog niet`}:{' '}
                {bestanden.map((b) => b.name).join(', ')}. {uploadFout}
              </p>
              <button
                type="button"
                onClick={() => uploadBestanden(submittedId, bestanden)}
                className="inline-flex items-center gap-2 font-semibold text-amber-900 underline"
              >
                <RefreshCw className="w-4 h-4" aria-hidden="true" />
                {bestanden.length === 1 ? 'Bestand opnieuw proberen' : 'Bestanden opnieuw proberen'}
              </button>
            </div>
          )}
          <div className="bg-stone-50 rounded-2xl p-4 border border-stone-200 mb-8 text-xs text-stone-500 font-mono select-all">
            Referentienummer: <span className="text-stone-800 font-bold">{submittedId}</span>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/mijn-inzendingen"
              className="bg-stone-100 hover:bg-stone-200 text-stone-800 font-semibold text-sm px-6 py-3 rounded-xl transition-colors inline-flex items-center justify-center gap-2"
            >
              Bekijk in Mijn Inzendingen
            </Link>
            <Link
              to="/ontdekken"
              className="bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm px-6 py-3 rounded-xl transition-colors inline-flex items-center justify-center gap-2"
            >
              Ontdek andere verhalen
              <ArrowRight className="w-4 h-4" />
            </Link>
            <button
              onClick={() => {
                setSubmittedId(null);
                setUploadFout(null);
                setBestanden([]);
                setConsentGiven(false);
                setConcept(LEEG);
              }}
              className="bg-stone-100 hover:bg-stone-200 text-stone-700 font-semibold text-sm px-6 py-3 rounded-xl transition-colors"
            >
              Nog een verhaal delen
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-10">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-semibold uppercase tracking-wider mb-3">
            <Sparkles className="w-3.5 h-3.5 text-amber-800" />
            Samen Geschiedenis Schrijven
          </span>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-stone-900 mb-3">
            Deel uw herinnering of erfgoedmateriaal
          </h1>
          <p className="text-stone-600 text-sm max-w-xl mx-auto leading-relaxed">
            Heeft u een verhaal, getuigenis, foto, geluidsopname of document? Draag bij aan het levende collectieve
            geheugen van onze gemeenschap.
          </p>
        </div>

        <div className="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm">
          {!ingelogd ? (
            <AanmeldStap />
          ) : (
            <>
              <div className="mb-6 p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-700 flex-shrink-0" />
                U bent ingelogd. Uw verhaal komt in "Mijn Inzendingen", waar u de status kunt volgen.
              </div>

              {errorMessage && (
                <div id="submit-error" role="alert" aria-live="assertive" className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <span>{errorMessage}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-6" aria-label="Erfgoed inzenden formulier">
                <div>
                  <label htmlFor="title" className={label}>
                    Titel van het verhaal <span className="text-red-600" aria-hidden="true">*</span>
                  </label>
                  <input
                    id="title"
                    type="text"
                    required
                    aria-required="true"
                    value={concept.title}
                    onChange={(e) => zet('title', e.target.value)}
                    placeholder="Bijv. De aankomst van mijn grootouders in 1954"
                    className={veld}
                  />
                </div>

                <div>
                  <label htmlFor="category" className={label}>
                    Categorie <span className="text-red-600" aria-hidden="true">*</span>
                  </label>
                  <select
                    id="category"
                    value={concept.category}
                    required
                    aria-required="true"
                    onChange={(e) => zet('category', e.target.value)}
                    className={veld}
                  >
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="body" className={label}>
                    Uw Verhaal of Toelichting <span className="text-red-600" aria-hidden="true">*</span>
                  </label>
                  <textarea
                    id="body"
                    required
                    aria-required="true"
                    rows={6}
                    value={concept.body}
                    onChange={(e) => zet('body', e.target.value)}
                    placeholder="Beschrijf de gebeurtenis, herinnering, personen en context..."
                    className={`${veld} leading-relaxed`}
                  />
                </div>

                <fieldset>
                  <legend className={label}>Foto, geluid of document (optioneel)</legend>
                  <BestandKiezer bestanden={bestanden} onWijzig={setBestanden} />
                </fieldset>

                <fieldset className="space-y-3">
                  <legend className={label}>Waar speelt het verhaal zich af? (optioneel)</legend>
                  <div>
                    <label htmlFor="locationName" className="block text-xs text-stone-700 mb-1">
                      Plaatsnaam
                    </label>
                    <div className="relative">
                      <MapPin className="w-4 h-4 text-stone-400 absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
                      <input
                        id="locationName"
                        type="text"
                        value={concept.locationName}
                        onChange={(e) => zet('locationName', e.target.value)}
                        placeholder="Bijv. Paramaribo, Nieuw Nickerie of Vlaardingen"
                        className={`${veld} pl-10`}
                      />
                    </div>
                  </div>
                  <p className="text-xs text-stone-600">
                    Tik of klik op de kaart om de plek aan te wijzen. Weet u het niet precies? Dan laat u de kaart leeg.
                  </p>
                  <PlekKiezer plek={concept.plek} onKies={(p) => zet('plek', p)} />
                </fieldset>

                <div className="border-t border-stone-100 pt-6 space-y-4">
                  <div>
                    <label htmlFor="authorName" className={label}>
                      Uw naam (zoals die bij het verhaal mag staan)
                    </label>
                    <input
                      id="authorName"
                      type="text"
                      disabled={concept.isAnonymous}
                      value={concept.authorName}
                      onChange={(e) => zet('authorName', e.target.value)}
                      placeholder="Voor- en achternaam"
                      className={`${veld} disabled:opacity-50`}
                    />
                  </div>
                  <div className="flex items-center gap-3 pt-1">
                    <input
                      type="checkbox"
                      id="isAnonymous"
                      checked={concept.isAnonymous}
                      onChange={(e) => zet('isAnonymous', e.target.checked)}
                      className="w-4 h-4 rounded border-stone-300 text-amber-800 focus:ring-amber-700 cursor-pointer"
                    />
                    <label htmlFor="isAnonymous" className="text-xs text-stone-700 font-medium cursor-pointer">
                      Plaats dit verhaal anoniem (uw naam wordt niet publiek weergegeven op het portaal)
                    </label>
                  </div>
                </div>

                <div className="border-t border-stone-100 pt-6">
                  <div className="bg-stone-50 rounded-2xl p-4 border border-stone-200 flex items-start gap-3">
                    <input
                      type="checkbox"
                      id="consent"
                      required
                      aria-required="true"
                      checked={consentGiven}
                      onChange={(e) => setConsentGiven(e.target.checked)}
                      className="w-4 h-4 rounded border-stone-300 text-amber-800 focus:ring-amber-700 mt-0.5 cursor-pointer"
                    />
                    <label htmlFor="consent" className="text-xs text-stone-700 leading-relaxed cursor-pointer">
                      <span className="font-semibold text-stone-900">Auteursrechten &amp; Ethische Verklaring:</span> Ik
                      verklaar dat ik bevoegd ben om dit materiaal ter beschikking te stellen aan het erfgoedarchief van
                      Het Levend Monument onder een <span className="font-semibold text-stone-900">Creative Commons CC-BY 4.0</span>{' '}
                      licentie, en dat eventuele levende personen herkenbaar in beeld of tekst hun toestemming hebben
                      verleend.
                    </label>
                  </div>
                </div>

                <div className="pt-4">
                  <button
                    type="submit"
                    disabled={submitting}
                    aria-busy={submitting}
                    className="w-full bg-amber-800 hover:bg-amber-700 text-white font-serif font-bold text-base py-3.5 px-6 rounded-2xl transition-colors shadow-xs disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {submitting ? (
                      <>
                        <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" aria-hidden="true" />
                        <span>{voortgang ?? 'Inzending verwerken...'}</span>
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="w-5 h-5" aria-hidden="true" />
                        <span>Verstuur naar het Erfgoedarchief</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
