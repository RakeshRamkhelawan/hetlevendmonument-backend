import React, { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { CheckCircle2, AlertCircle, Scale, ArrowLeft } from 'lucide-react';
import { api } from '../api/client';
import { HCaptchaWidget } from '../components/HCaptchaWidget';

export const NoticeTakedown: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialContentId = searchParams.get('content_id') || '';
  const initialTitle = searchParams.get('title') || '';

  const [contentId, setContentId] = useState(initialContentId);
  const [reasonType, setReasonType] = useState('copyright');
  const [description, setDescription] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [declaration, setDeclaration] = useState(false);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [takedownReference, setTakedownReference] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (initialContentId) {
      setContentId(initialContentId);
    }
  }, [initialContentId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!declaration) {
      setErrorMessage('U dient te verklaren dat deze melding naar waarheid is ingevuld.');
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);

    const fullReason = `[${reasonType.toUpperCase()}] Door ${contactName}: ${description}`;

    try {
      const res = await api.submitTakedown(
        {
          content_id: parseInt(contentId, 10),
          reason: fullReason,
          contact_email: contactEmail,
        },
        captchaToken
      );
      setTakedownReference(res.id);
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error ? err.message : 'Er is een fout opgetreden bij het indienen van de melding.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <Link
          to="/ontdekken"
          className="inline-flex items-center gap-2 text-xs font-semibold text-stone-600 hover:text-stone-900 mb-6"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Terug naar de portal
        </Link>

        {/* Header */}
        <div className="mb-8">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-100 text-red-900 text-xs font-semibold uppercase tracking-wider mb-3">
            <Scale className="w-3.5 h-3.5 text-red-800" />
            Juridische Procedure
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-stone-900 mb-3">
            Notice &amp; Takedown Procedure
          </h1>
          <p className="text-stone-600 text-sm leading-relaxed">
            Het Levend Monument respecteert intellectuele eigendomsrechten, portretrechten en privacy. Indien u meent
            dat materiaal op dit platform inbreuk maakt op uw rechten, kunt u via onderstaand formulier een gemotiveerd
            bezwaar indienen conform de Nederlandse Gedragscode Notice and Takedown.
          </p>
        </div>

        {takedownReference ? (
          <div role="status" aria-live="polite" className="bg-white rounded-3xl p-8 sm:p-10 border border-stone-200 shadow-sm text-center">
            <div className="w-16 h-16 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle2 className="w-8 h-8" aria-hidden="true" />
            </div>
            <h2 className="font-serif text-2xl font-bold text-stone-900 mb-2">Melding Succesvol Ontvangen</h2>
            <p className="text-stone-600 text-sm leading-relaxed mb-6">
              Uw melding is geregistreerd onder referentie{' '}
              <strong className="text-stone-900 font-mono">#NTD-{takedownReference}</strong>. Ons juridisch team neemt uw
              verzoek binnen 48 uur in behandeling. Indien van toepassing wordt het betreffende item hangende het onderzoek
              tijdelijk onzichtbaar gemaakt.
            </p>
            <Link
              to="/ontdekken"
              className="inline-block bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm px-6 py-2.5 rounded-xl transition-colors"
            >
              Terug naar het overzicht
            </Link>
          </div>
        ) : (
          <div className="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm">
            {errorMessage && (
              <div id="ntd-error" role="alert" aria-live="assertive" className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span>{errorMessage}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6" aria-label="Notice and Takedown formulier">
              <div>
                <label htmlFor="contentId" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                  ID van het Erfgoeditem <span className="text-red-600" aria-hidden="true">*</span>
                </label>
                <input
                  id="contentId"
                  type="number"
                  required
                  aria-required="true"
                  aria-invalid={!!errorMessage && !contentId}
                  value={contentId}
                  onChange={(e) => setContentId(e.target.value)}
                  placeholder="Bijv. 12"
                  className="w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                />
                {initialTitle && (
                  <span className="block text-xs text-stone-600 mt-1 font-medium">Betreft: &quot;{initialTitle}&quot;</span>
                )}
              </div>

              <div>
                <label htmlFor="reasonType" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                  Aard van het Bezwaar <span className="text-red-600" aria-hidden="true">*</span>
                </label>
                <select
                  id="reasonType"
                  value={reasonType}
                  required
                  aria-required="true"
                  onChange={(e) => setReasonType(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                >
                  <option value="copyright">Auteursrechtinbreuk (Zonder toestemming gepubliceerd)</option>
                  <option value="privacy">Privacy &amp; Portretrecht (Herkenbaar zonder toestemming)</option>
                  <option value="defamation">Onjuiste feiten / Smaad &amp; Laster</option>
                  <option value="hate_speech">Haatspraak of discriminatie</option>
                  <option value="other">Overig bezwaar</option>
                </select>
              </div>

              <div>
                <label htmlFor="description" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                  Toelichting en Bewijsstukken <span className="text-red-600" aria-hidden="true">*</span>
                </label>
                <textarea
                  id="description"
                  required
                  aria-required="true"
                  aria-invalid={!!errorMessage && !description}
                  rows={5}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Beschrijf waarom u rechthebbende bent of waarom dit materiaal verwijderd dient te worden..."
                  className="w-full px-4 py-3 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50 leading-relaxed"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="contactName" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                    Uw Volledige Naam <span className="text-red-600" aria-hidden="true">*</span>
                  </label>
                  <input
                    id="contactName"
                    type="text"
                    required
                    aria-required="true"
                    aria-invalid={!!errorMessage && !contactName}
                    value={contactName}
                    onChange={(e) => setContactName(e.target.value)}
                    placeholder="Voor- en achternaam"
                    className="w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                  />
                </div>
                <div>
                  <label htmlFor="contactEmail" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                    Uw E-mailadres <span className="text-red-600" aria-hidden="true">*</span>
                  </label>
                  <input
                    id="contactEmail"
                    type="email"
                    required
                    aria-required="true"
                    aria-invalid={!!errorMessage && !contactEmail}
                    value={contactEmail}
                    onChange={(e) => setContactEmail(e.target.value)}
                    placeholder="naam@organisatie.nl"
                    className="w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                  />
                </div>
              </div>

              <div className="bg-stone-50 rounded-2xl p-4 border border-stone-200 flex items-start gap-3">
                <input
                  type="checkbox"
                  id="declaration"
                  required
                  aria-required="true"
                  checked={declaration}
                  onChange={(e) => setDeclaration(e.target.checked)}
                  className="w-4 h-4 rounded border-stone-300 text-amber-800 focus:ring-amber-700 mt-0.5 cursor-pointer"
                />
                <label htmlFor="declaration" className="text-xs text-stone-700 leading-relaxed cursor-pointer">
                  Ik verklaar dat de verstrekte informatie naar waarheid en beste weten is ingevuld en dat ik bevoegd ben
                  namens mezelf of de rechthebbende op te treden.
                </label>
              </div>

              <HCaptchaWidget onVerify={setCaptchaToken} className="pt-2" />

              <button
                type="submit"
                disabled={submitting}
                aria-busy={submitting}
                className="w-full bg-red-700 hover:bg-red-800 text-white font-semibold text-sm py-3.5 px-4 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2 shadow-xs"
              >
                {submitting ? 'Melding indienen...' : 'Dien Notice & Takedown In'}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};
