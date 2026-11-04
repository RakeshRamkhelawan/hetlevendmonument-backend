import React, { useState, useEffect } from 'react';
import {
  Heart,
  ShieldCheck,
  Sparkles,
  Lock,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Users,
  CreditCard,
  Calendar,
} from 'lucide-react';
import { api } from '../api/client';
import { HCaptchaWidget } from '../components/HCaptchaWidget';
import type { DonationFrequency, DonationStats } from '../types';

const PRESET_AMOUNTS = [
  { value: 5, label: '€5', desc: 'Onderhoud een Verhaal' },
  { value: 15, label: '€15', desc: 'Adopteer een Foto/Audioarchief' },
  { value: 25, label: '€25', desc: 'Educatiepakket voor een Klas' },
  { value: 50, label: '€50', desc: 'Erfgoedbehoud & Digitalisering' },
];

export const Donate: React.FC = () => {
  const [selectedPreset, setSelectedPreset] = useState<number | 'custom'>(15);
  const [customAmount, setCustomAmount] = useState<string>('');
  const [frequency, setFrequency] = useState<DonationFrequency>('one_time');
  const [donorEmail, setDonorEmail] = useState<string>('');
  const [donorName, setDonorName] = useState<string>('');
  const [isAnonymous, setIsAnonymous] = useState<boolean>(false);
  const [message, setMessage] = useState<string>('');
  const [hcaptchaToken, setHcaptchaToken] = useState<string | null>(null);

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<DonationStats | null>(null);
  const [isLoadingStats, setIsLoadingStats] = useState<boolean>(true);

  useEffect(() => {
    let isMounted = true;
    api
      .getDonationStats()
      .then((data) => {
        if (isMounted) {
          setStats(data);
          setIsLoadingStats(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setIsLoadingStats(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const calculateAmountCents = (): number => {
    if (selectedPreset === 'custom') {
      const parsed = parseFloat(customAmount.replace(',', '.'));
      if (isNaN(parsed) || parsed <= 0) return 0;
      return Math.round(parsed * 100);
    }
    return selectedPreset * 100;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const amountCents = calculateAmountCents();
    if (amountCents < 100) {
      setError('Het minimale donatiebedrag is €1,00.');
      return;
    }
    if (amountCents > 500000) {
      setError('Het maximale donatiebedrag via dit formulier is €5.000,00.');
      return;
    }
    if (!donorEmail.trim()) {
      setError('Vul alstublieft uw e-mailadres in voor de ontvangstbevestiging.');
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await api.createDonationCheckout({
        amount_cents: amountCents,
        frequency,
        donor_email: donorEmail.trim(),
        donor_name: isAnonymous ? undefined : donorName.trim() || undefined,
        is_anonymous: isAnonymous,
        message: message.trim() || undefined,
        hcaptcha_token: hcaptchaToken || undefined,
      });

      if (res.checkout_url) {
        window.location.href = res.checkout_url;
      } else {
        throw new Error('Geen betaal-URL ontvangen van de server.');
      }
    } catch (err: any) {
      setError(err?.message || 'Er is een fout opgetreden bij het starten van de betaling. Probeer het later opnieuw.');
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header Section */}
        <header className="text-center max-w-2xl mx-auto mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-semibold uppercase tracking-wider mb-4">
            <Heart className="w-3.5 h-3.5 text-amber-800 fill-amber-800" />
            Steun het Erfgoed
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-bold text-stone-900 mb-4 leading-tight">
            Help Mee het Levend Monument Levend te Houden
          </h1>
          <p className="text-stone-600 text-sm sm:text-base leading-relaxed">
            Met uw bijdrage zorgen we dat verhalen van onze gedeelde geschiedenis worden gearchiveerd,
            gedigitaliseerd en overgedragen aan volgende generaties in het onderwijs.
          </p>
        </header>

        {/* Live Transparency Stats Banner */}
        {stats && (
          <aside aria-label="Donatiestatistieken" className="bg-white rounded-2xl border border-stone-200 p-6 mb-12 shadow-xs">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-center">
              <div>
                <div className="text-2xl sm:text-3xl font-serif font-bold text-amber-900">
                  {`€${(stats.total_raised_cents / 100).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`}
                </div>
                <div className="text-xs text-stone-500 mt-1">Reeds bijeengebracht</div>
              </div>
              <div className="border-t sm:border-t-0 sm:border-l border-stone-200 pt-4 sm:pt-0 sm:pl-6">
                <div className="text-2xl sm:text-3xl font-serif font-bold text-stone-800">
                  {stats.total_donations_count}
                </div>
                <div className="text-xs text-stone-500 mt-1">Betrokken gevers</div>
              </div>
              <div className="border-t sm:border-t-0 sm:border-l border-stone-200 pt-4 sm:pt-0 sm:pl-6">
                <div className="text-2xl sm:text-3xl font-serif font-bold text-stone-800">
                  {stats.monthly_supporters_count}
                </div>
                <div className="text-xs text-stone-500 mt-1">Vaste vrienden van het monument</div>
              </div>
            </div>
          </aside>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Main Donation Form */}
          <main className="lg:col-span-7 bg-white rounded-3xl border border-stone-200 p-6 sm:p-8 shadow-xs">
            <form onSubmit={handleSubmit} className="space-y-6" noValidate>
              {error && (
                <div
                  role="alert"
                  aria-live="polite"
                  className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start gap-2.5"
                >
                  <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              {/* Frequency Selector */}
              <fieldset>
                <legend className="block text-xs font-semibold text-stone-800 uppercase tracking-wider mb-2">
                  Frequentie
                </legend>
                <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="Frequentie van donatie">
                  <button
                    type="button"
                    role="radio"
                    aria-checked={frequency === 'one_time'}
                    onClick={() => setFrequency('one_time')}
                    className={`flex items-center justify-center gap-2 py-3 px-4 rounded-xl text-xs font-semibold border transition-all ${
                      frequency === 'one_time'
                        ? 'border-amber-800 bg-amber-50 text-amber-950 ring-2 ring-amber-800/20'
                        : 'border-stone-200 bg-white text-stone-700 hover:border-stone-300'
                    }`}
                  >
                    <CreditCard className="w-4 h-4 text-amber-800" />
                    Eenmalig
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={frequency === 'monthly'}
                    onClick={() => setFrequency('monthly')}
                    className={`flex items-center justify-center gap-2 py-3 px-4 rounded-xl text-xs font-semibold border transition-all ${
                      frequency === 'monthly'
                        ? 'border-amber-800 bg-amber-50 text-amber-950 ring-2 ring-amber-800/20'
                        : 'border-stone-200 bg-white text-stone-700 hover:border-stone-300'
                    }`}
                  >
                    <Calendar className="w-4 h-4 text-amber-800" />
                    Maandelijks (Vriend)
                  </button>
                </div>
              </fieldset>

              {/* Amount Presets */}
              <fieldset>
                <legend className="block text-xs font-semibold text-stone-800 uppercase tracking-wider mb-2">
                  Kies uw bijdrage
                </legend>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  {PRESET_AMOUNTS.map((preset) => (
                    <button
                      key={preset.value}
                      type="button"
                      onClick={() => {
                        setSelectedPreset(preset.value);
                        setCustomAmount('');
                      }}
                      className={`p-3.5 rounded-2xl text-left border transition-all ${
                        selectedPreset === preset.value
                          ? 'border-amber-800 bg-amber-50/60 ring-2 ring-amber-800/20'
                          : 'border-stone-200 bg-white hover:border-stone-300'
                      }`}
                    >
                      <div className="font-serif font-bold text-base sm:text-lg text-stone-900">{preset.label}</div>
                      <div className="text-[11px] text-stone-500 mt-0.5 leading-snug">{preset.desc}</div>
                    </button>
                  ))}
                </div>

                {/* Custom Amount Button/Input */}
                <div className="mt-2">
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-stone-500 font-serif text-sm">
                      €
                    </span>
                    <input
                      type="text"
                      id="custom-amount-input"
                      placeholder="Ander bedrag (bijv. 30)"
                      value={customAmount}
                      onChange={(e) => {
                        setCustomAmount(e.target.value);
                        setSelectedPreset('custom');
                      }}
                      className={`w-full pl-8 pr-4 py-2.5 rounded-xl text-xs border transition-colors ${
                        selectedPreset === 'custom'
                          ? 'border-amber-800 ring-2 ring-amber-800/20 bg-amber-50/20'
                          : 'border-stone-200 bg-white'
                      }`}
                      aria-label="Vrij donatiebedrag in euro's"
                    />
                  </div>
                </div>
              </fieldset>

              {/* Donor Details */}
              <div className="space-y-4 pt-2 border-t border-stone-100">
                <div>
                  <label htmlFor="donor-email" className="block text-xs font-semibold text-stone-700 mb-1">
                    E-mailadres <span className="text-amber-800">*</span>
                  </label>
                  <input
                    type="email"
                    id="donor-email"
                    required
                    value={donorEmail}
                    onChange={(e) => setDonorEmail(e.target.value)}
                    placeholder="uw.email@voorbeeld.nl"
                    className="w-full px-3.5 py-2.5 rounded-xl text-xs border border-stone-200 focus:outline-hidden focus:ring-2 focus:ring-amber-800/20 focus:border-amber-800"
                  />
                  <p className="text-[11px] text-stone-500 mt-1">
                    Wordt uitsluitend gebruikt voor de officiële betaalbevestiging en fiscaal afschrift.
                  </p>
                </div>

                <div>
                  <label htmlFor="donor-name" className="block text-xs font-semibold text-stone-700 mb-1">
                    Naam of Organisatie
                  </label>
                  <input
                    type="text"
                    id="donor-name"
                    disabled={isAnonymous}
                    value={donorName}
                    onChange={(e) => setDonorName(e.target.value)}
                    placeholder={isAnonymous ? 'Anonieme donateur' : 'Bijv. Familie De Vries of Bedrijfsnaam'}
                    className={`w-full px-3.5 py-2.5 rounded-xl text-xs border border-stone-200 focus:outline-hidden focus:ring-2 focus:ring-amber-800/20 focus:border-amber-800 ${
                      isAnonymous ? 'bg-stone-100 text-stone-400 cursor-not-allowed' : 'bg-white'
                    }`}
                  />
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="is-anonymous"
                    checked={isAnonymous}
                    onChange={(e) => setIsAnonymous(e.target.checked)}
                    className="w-4 h-4 rounded text-amber-800 focus:ring-amber-800 border-stone-300"
                  />
                  <label htmlFor="is-anonymous" className="text-xs text-stone-700 cursor-pointer select-none">
                    Ik wil graag anoniem doneren (verberg mijn naam op de donateursmuur)
                  </label>
                </div>

                <div>
                  <label htmlFor="donor-message" className="block text-xs font-semibold text-stone-700 mb-1">
                    Persoonlijke boodschap (optioneel)
                  </label>
                  <textarea
                    id="donor-message"
                    rows={2}
                    maxLength={500}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Waarom steunt u het Levend Monument?"
                    className="w-full px-3.5 py-2.5 rounded-xl text-xs border border-stone-200 focus:outline-hidden focus:ring-2 focus:ring-amber-800/20 focus:border-amber-800 resize-none"
                  />
                </div>
              </div>

              {/* Bot Protection Widget */}
              <div className="pt-2">
                <HCaptchaWidget
                  onVerify={(token) => setHcaptchaToken(token)}
                  onExpire={() => setHcaptchaToken(null)}
                />
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full bg-amber-900 hover:bg-amber-950 text-white font-semibold text-xs py-3.5 px-6 rounded-xl transition-all shadow-sm flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Betaalsessie voorbereiden...</span>
                  </>
                ) : (
                  <>
                    <Lock className="w-3.5 h-3.5" />
                    <span>
                      Ga verder naar veilige betaling (€{(calculateAmountCents() / 100).toFixed(2)})
                    </span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                )}
              </button>

              <div className="flex items-center justify-center gap-2 text-[11px] text-stone-500">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-700" />
                <span>Veilig betalen via iDEAL, Bancontact of Creditcard met Stripe</span>
              </div>
            </form>
          </main>

          {/* Right Column: Impact & Recent Supporters */}
          <aside className="lg:col-span-5 space-y-6">
            {/* Impact Highlights Card */}
            <div className="bg-amber-900 text-white rounded-3xl p-6 sm:p-7 shadow-sm">
              <div className="w-8 h-8 rounded-lg bg-amber-800 flex items-center justify-center mb-3">
                <Sparkles className="w-4 h-4 text-amber-300" />
              </div>
              <h2 className="font-serif font-bold text-lg mb-2">Waarom uw steun telt</h2>
              <ul className="space-y-2.5 text-xs text-stone-200">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-amber-300 shrink-0 mt-0.5" />
                  <span>Behoud van authentieke getuigenissen en oral history.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-amber-300 shrink-0 mt-0.5" />
                  <span>Gratis educatieve lespakketten voor scholen en docenten.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-amber-300 shrink-0 mt-0.5" />
                  <span>Duurzame open-access archivering conform NDE erfgoedstandaarden.</span>
                </li>
              </ul>
            </div>

            {/* Supporters Wall */}
            <div className="bg-white rounded-3xl border border-stone-200 p-6 shadow-xs">
              <div className="flex items-center gap-2 mb-4">
                <Users className="w-4 h-4 text-amber-900" />
                <h2 className="font-serif font-bold text-sm text-stone-900">Recente Donateurs</h2>
              </div>

              {isLoadingStats ? (
                <div className="space-y-3">
                  <div className="h-10 bg-stone-100 rounded-xl animate-pulse" />
                  <div className="h-10 bg-stone-100 rounded-xl animate-pulse" />
                </div>
              ) : stats?.recent_donations && stats.recent_donations.length > 0 ? (
                <ul className="divide-y divide-stone-100">
                  {stats.recent_donations.map((item) => (
                    <li key={item.id} className="py-3 first:pt-0 last:pb-0">
                      <div className="flex justify-between items-baseline mb-1">
                        <span className="font-medium text-xs text-stone-900">
                          {item.donor_name || 'Vriend van het Monument'}
                        </span>
                        <span className="text-[11px] font-semibold text-amber-900">
                          €{(item.amount_cents / 100).toFixed(2)}
                        </span>
                      </div>
                      {item.message && (
                        <p className="text-[11px] text-stone-500 italic line-clamp-2">
                          &ldquo;{item.message}&rdquo;
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-stone-500 italic">
                  Word de eerste donateur en vereeuwig uw steun voor het erfgoed.
                </p>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};
