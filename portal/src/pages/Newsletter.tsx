import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Mail, CheckCircle2, AlertCircle, ShieldCheck, Sparkles, Loader2, UserMinus } from 'lucide-react';
import { api } from '../api/client';
import { HCaptchaWidget } from '../components/HCaptchaWidget';

export const Newsletter: React.FC = () => {
  const [searchParams] = useSearchParams();
  const confirmToken = searchParams.get('confirm');
  const confirmEmail = searchParams.get('email');
  const isUnsubscribe = searchParams.get('unsubscribe') === 'true';
  const unsubToken = searchParams.get('token');
  const unsubEmail = searchParams.get('email');

  // Subscription form state
  const [email, setEmail] = useState('');
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Double opt-in confirmation state
  const [confirming, setConfirming] = useState(false);
  const [confirmSuccess, setConfirmSuccess] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  // Unsubscribe state
  const [unsubmitting, setUnsubmitting] = useState(false);
  const [unsubSuccess, setUnsubSuccess] = useState(false);
  const [unsubError, setUnsubError] = useState<string | null>(null);

  useEffect(() => {
    // Handle double opt-in confirmation automatically on mount if query params are present
    if (confirmToken && confirmEmail && !isUnsubscribe) {
      const runConfirmation = async () => {
        setConfirming(true);
        setConfirmError(null);
        try {
          await api.confirmNewsletter(confirmEmail, confirmToken);
          setConfirmSuccess(true);
        } catch (err: unknown) {
          setConfirmError(
            err instanceof Error ? err.message : 'De bevestigingslink is ongeldig of verlopen.'
          );
        } finally {
          setConfirming(false);
        }
      };
      runConfirmation();
    }
  }, [confirmToken, confirmEmail, isUnsubscribe]);

  const handleUnsubscribeSubmit = async () => {
    if (!unsubEmail || !unsubToken) return;
    setUnsubmitting(true);
    setUnsubError(null);
    try {
      await api.unsubscribeNewsletter(unsubEmail, unsubToken);
      setUnsubSuccess(true);
    } catch (err: unknown) {
      setUnsubError(
        err instanceof Error ? err.message : 'Er is een fout opgetreden bij het uitschrijven.'
      );
    } finally {
      setUnsubmitting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    setLoading(true);
    setError(null);

    try {
      await api.subscribeNewsletter(email, undefined, undefined, captchaToken);
      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Er is een fout opgetreden bij het aanmelden.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[75vh] flex items-center justify-center py-16 px-4 bg-[#FDFBF7]">
      <div className="max-w-xl w-full bg-white rounded-3xl p-8 sm:p-12 border border-stone-200 shadow-sm">
        {/* State 1: Opt-in confirmation in progress or completed */}
        {confirmToken && confirmEmail && !isUnsubscribe ? (
          <div role="status" aria-live="polite" className="text-center">
            {confirming ? (
              <div className="py-8">
                <Loader2 className="w-12 h-12 text-amber-800 animate-spin mx-auto mb-4" aria-hidden="true" />
                <h2 className="font-serif text-2xl font-bold text-stone-900 mb-2">Inschrijving verifieren...</h2>
                <p className="text-stone-600 text-sm">Een ogenblik geduld, uw aanmelding wordt bevestigd.</p>
              </div>
            ) : confirmSuccess ? (
              <div>
                <div className="w-16 h-16 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2 className="w-8 h-8" aria-hidden="true" />
                </div>
                <h2 className="font-serif text-3xl font-bold text-stone-900 mb-2">Inschrijving Bevestigd!</h2>
                <p className="text-stone-600 text-sm leading-relaxed mb-6">
                  Uw e-mailadres <strong className="text-stone-800">{confirmEmail}</strong> is succesvol geverifieerd.
                  U ontvangt vanaf nu de periodieke updates, historische verhalen en aankondigingen van Het Levend Monument.
                </p>
                <p className="text-xs text-stone-400">U kunt dit tabblad veilig sluiten of verder bladeren door het erfgoedarchief.</p>
              </div>
            ) : (
              <div>
                <div className="w-16 h-16 bg-red-100 text-red-700 rounded-full flex items-center justify-center mx-auto mb-4">
                  <AlertCircle className="w-8 h-8" aria-hidden="true" />
                </div>
                <h2 className="font-serif text-2xl font-bold text-stone-900 mb-2">Bevestiging Niet Gelukt</h2>
                <p className="text-stone-600 text-sm leading-relaxed mb-6">
                  {confirmError || 'De verificatielink is mogelijk verlopen of reeds gebruikt.'}
                </p>
                <a
                  href="/nieuwsbrief"
                  className="inline-block bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm py-3 px-6 rounded-xl transition-colors"
                >
                  Opnieuw aanmelden
                </a>
              </div>
            )}
          </div>
        ) : isUnsubscribe && unsubEmail && unsubToken ? (
          /* State 2: Unsubscribe explicit confirmation (safe against automated email scanners) */
          <div role="status" aria-live="polite" className="text-center">
            {unsubSuccess ? (
              <div>
                <div className="w-16 h-16 bg-stone-100 text-stone-700 rounded-full flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2 className="w-8 h-8 text-stone-600" aria-hidden="true" />
                </div>
                <h2 className="font-serif text-2xl font-bold text-stone-900 mb-2">U bent uitgeschreven</h2>
                <p className="text-stone-600 text-sm leading-relaxed mb-6">
                  Het e-mailadres <strong className="text-stone-800">{unsubEmail}</strong> is succesvol verwijderd uit onze mailinglijst. U ontvangt geen verdere nieuwsbrieven van ons.
                </p>
              </div>
            ) : (
              <div>
                <div className="w-16 h-16 bg-amber-100 text-amber-900 rounded-full flex items-center justify-center mx-auto mb-4">
                  <UserMinus className="w-8 h-8 text-amber-800" aria-hidden="true" />
                </div>
                <h2 className="font-serif text-2xl font-bold text-stone-900 mb-2">Uitschrijven voor de nieuwsbrief</h2>
                <p className="text-stone-600 text-sm leading-relaxed mb-6">
                  Weet u zeker dat u zich wilt uitschrijven voor de nieuwsbrief van Het Levend Monument voor het adres <strong className="text-stone-800">{unsubEmail}</strong>?
                </p>
                {unsubError && (
                  <div role="alert" aria-live="assertive" className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
                    {unsubError}
                  </div>
                )}
                <button
                  onClick={handleUnsubscribeSubmit}
                  disabled={unsubmitting}
                  aria-busy={unsubmitting}
                  className="w-full bg-red-700 hover:bg-red-800 text-white font-semibold text-sm py-3 px-4 rounded-xl transition-colors disabled:opacity-50"
                >
                  {unsubmitting ? 'Verwerken...' : 'Ja, schrijf mij definitief uit'}
                </button>
              </div>
            )}
          </div>
        ) : success ? (
          /* State 3: Subscription form submitted (Double Opt-in instructions) */
          <div role="status" aria-live="polite" className="text-center">
            <div className="w-16 h-16 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle2 className="w-8 h-8" aria-hidden="true" />
            </div>
            <h2 className="font-serif text-3xl font-bold text-stone-900 mb-2">Bevestig uw inschrijving</h2>
            <p className="text-stone-600 text-sm leading-relaxed mb-6">
              Wij hebben een verificatie-e-mail verzonden naar <strong className="text-stone-800">{email}</strong>.
              Klik op de verificatielink in deze e-mail om uw aanmelding definitief te activeren conform de AVG-richtlijnen.
            </p>
            <p className="text-xs text-stone-500 mb-4">Geen e-mail ontvangen? Controleer ook uw spam- of ongewenste berichtenmap.</p>
            <button
              onClick={() => {
                setSuccess(false);
                setEmail('');
              }}
              className="text-xs text-amber-800 hover:underline font-semibold"
            >
              Ander e-mailadres aanmelden
            </button>
          </div>
        ) : (
          /* State 4: Default subscription form */
          <div>
            <div className="text-center mb-8">
              <div className="w-12 h-12 bg-amber-100 text-amber-900 rounded-full flex items-center justify-center mx-auto mb-3">
                <Mail className="w-6 h-6 text-amber-800" aria-hidden="true" />
              </div>
              <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-amber-800 bg-amber-50 px-2.5 py-0.5 rounded-full mb-2">
                <Sparkles className="w-3 h-3" aria-hidden="true" />
                Maandelijkse Kroniek
              </span>
              <h1 className="font-serif text-3xl font-bold text-stone-900 mb-2">Blijf Verbonden</h1>
              <p className="text-stone-600 text-sm max-w-md mx-auto leading-relaxed">
                Ontvang maandelijks nieuw ontdekte oral history opnames, historische analyses en aankondigingen van
                herdenkingsactiviteiten.
              </p>
            </div>

            {error && (
              <div id="newsletter-error" role="alert" aria-live="assertive" className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" aria-label="Nieuwsbrief aanmeldformulier">
              <div>
                <label htmlFor="email" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                  Uw E-mailadres <span className="text-red-600" aria-hidden="true">*</span>
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-stone-500 absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
                  <input
                    id="email"
                    type="email"
                    required
                    aria-required="true"
                    aria-invalid={!!error}
                    aria-describedby={error ? 'newsletter-error' : undefined}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="naam@voorbeeld.nl"
                    className="w-full pl-10 pr-4 py-3 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                  />
                </div>
              </div>

              <div className="space-y-2 pt-2">
                <span className="block text-xs font-bold uppercase tracking-wider text-stone-700">Interesses:</span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-stone-600">
                  <label className="flex items-center gap-2 p-2 rounded-lg border border-stone-100 hover:bg-stone-50 cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-amber-800" />
                    <span>Nieuwe verhalen &amp; audio</span>
                  </label>
                  <label className="flex items-center gap-2 p-2 rounded-lg border border-stone-100 hover:bg-stone-50 cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-amber-800" />
                    <span>Educatie &amp; Scholen</span>
                  </label>
                  <label className="flex items-center gap-2 p-2 rounded-lg border border-stone-100 hover:bg-stone-50 cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-amber-800" />
                    <span>Herdenkingen &amp; Evenementen</span>
                  </label>
                  <label className="flex items-center gap-2 p-2 rounded-lg border border-stone-100 hover:bg-stone-50 cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-amber-800" />
                    <span>Academisch &amp; Open Data</span>
                  </label>
                </div>
              </div>

              <HCaptchaWidget onVerify={setCaptchaToken} className="pt-2" />

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={loading}
                  aria-busy={loading}
                  className="w-full bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm py-3.5 px-4 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2 shadow-xs"
                >
                  {loading ? 'Aanmelden verwerken...' : 'Meld mij aan voor de nieuwsbrief'}
                </button>
              </div>

              <div className="flex items-start gap-2 pt-4 text-[11px] text-stone-400">
                <ShieldCheck className="w-4 h-4 text-stone-400 flex-shrink-0 mt-0.5" />
                <span>
                  Geen spam. Dubbele opt-in verificatie conform AVG. Uitschrijven kan op elk gewenst moment via de link onderaan elke nieuwsbrief.
                </span>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};
