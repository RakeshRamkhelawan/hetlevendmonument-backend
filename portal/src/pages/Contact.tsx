import React, { useState } from 'react';
import { Mail, MapPin, Phone, MessageSquare, CheckCircle2, HelpCircle, AlertCircle } from 'lucide-react';
import { api } from '../api/client';
import { HCaptchaWidget } from '../components/HCaptchaWidget';
import { ContactCategory } from '../types';

export const Contact: React.FC = () => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [category, setCategory] = useState<ContactCategory>('algemeen');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [hcaptchaToken, setHcaptchaToken] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referenceId, setReferenceId] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await api.submitContactForm({
        name,
        email,
        subject,
        category,
        message,
        hcaptcha_token: hcaptchaToken,
      });
      setReferenceId(res.reference_id);
      setSent(true);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Er is een fout opgetreden bij het verzenden van uw bericht.'
      );
    } finally {
      setLoading(false);
    }
  };

  const faqs = [
    {
      q: 'Hoe wordt mijn ingezonden verhaal beoordeeld?',
      a: 'Ons curatieteam controleert of de inzending voldoet aan onze ethische richtlijnen, de privacywetgeving (AVG) en auteursrechten. Vervolgens wordt het verrijkt met erfgoedtermen.',
    },
    {
      q: 'Kan ik mijn verhaal later nog aanpassen of laten verwijderen?',
      a: 'Jazeker. U kunt via onze Notice & Takedown procedure of via een e-mailbericht met vermelding van uw referentienummer te allen tijde correcties of verwijdering aanvragen.',
    },
    {
      q: 'Hoe kan onze school of instelling deelnemen?',
      a: 'Docenten kunnen direct via het Docenten Portaal een gratis klascode aanmaken. Voor grootschalige projecten of gastlessen kunt u via dit formulier contact opnemen.',
    },
  ];

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center max-w-2xl mx-auto mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-semibold uppercase tracking-wider mb-3">
            <MessageSquare className="w-4 h-4 text-amber-800" aria-hidden="true" />
            Contact &amp; Ondersteuning
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-stone-900 mb-3">Neem Contact met Ons Op</h1>
          <p className="text-stone-600 text-sm leading-relaxed">
            Heeft u vragen over het archief, een vraag over uw inzending of wilt u samenwerken als culturele instelling?
            We horen graag van u.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-10 mb-16">
          {/* Contact Details */}
          <div className="bg-white p-6 sm:p-8 rounded-3xl border border-stone-200 shadow-xs space-y-6">
            <h2 className="font-serif font-bold text-stone-900 text-lg">Directe Gegevens</h2>

            <div className="space-y-4 text-xs text-stone-600">
              <div className="flex items-start gap-3">
                <Mail className="w-4 h-4 text-amber-800 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <div>
                  <strong className="block text-stone-900 font-semibold mb-0.5">E-mailadres</strong>
                  <span>info@hetlevendmonument.nl</span>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <MapPin className="w-4 h-4 text-amber-800 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <div>
                  <strong className="block text-stone-900 font-semibold mb-0.5">Locatie</strong>
                  <span>Netwerk Digitaal Erfgoed Partnernetwerk<br />Nederland &amp; Suriname</span>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <Phone className="w-4 h-4 text-amber-800 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <div>
                  <strong className="block text-stone-900 font-semibold mb-0.5">Educatie Coördinatie</strong>
                  <span>educatie@hetlevendmonument.nl</span>
                </div>
              </div>
            </div>

            <div className="pt-6 border-t border-stone-100 text-[11px] text-stone-400">
              Wij streven ernaar om berichten binnen twee werkdagen te beantwoorden.
            </div>
          </div>

          {/* Contact Form Container */}
          <div className="lg:col-span-2 bg-white p-6 sm:p-8 rounded-3xl border border-stone-200 shadow-xs">
            <h2 className="sr-only">Contactformulier</h2>
            {sent ? (
              <div role="status" aria-live="polite" className="py-12 text-center">
                <div className="w-16 h-16 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2 className="w-8 h-8" aria-hidden="true" />
                </div>
                <h3 className="font-serif font-bold text-stone-900 text-2xl mb-2">Bericht Verzonden</h3>
                <p className="text-stone-600 text-sm max-w-md mx-auto mb-4">
                  Bedankt voor uw bericht. Ons team neemt zo spoedig mogelijk contact met u op via{' '}
                  <strong className="text-stone-800">{email}</strong>.
                </p>
                {referenceId && (
                  <div className="bg-stone-50 border border-stone-200 rounded-xl p-3 max-w-xs mx-auto mb-6 text-xs text-stone-600">
                    <span className="block text-stone-500 uppercase tracking-wider text-[10px] font-bold">Referentienummer</span>
                    <span className="font-mono font-bold text-stone-900 text-sm">{referenceId}</span>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setSent(false);
                    setReferenceId(null);
                    setMessage('');
                    setSubject('');
                    setHcaptchaToken(null);
                  }}
                  className="text-xs text-amber-800 font-semibold hover:underline"
                >
                  Nog een bericht sturen
                </button>
              </div>
            ) : (
              <div>
                {error && (
                  <div role="alert" aria-live="assertive" className="mb-4 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                    <span>{error}</span>
                  </div>
                )}
                <form onSubmit={handleSubmit} className="space-y-4" aria-label="Contactformulier">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="name" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                        Uw Naam <span className="text-red-600" aria-hidden="true">*</span>
                      </label>
                      <input
                        id="name"
                        type="text"
                        required
                        aria-required="true"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Voor- en achternaam"
                        className="w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                      />
                    </div>

                    <div>
                      <label htmlFor="email" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                        Uw E-mailadres <span className="text-red-600" aria-hidden="true">*</span>
                      </label>
                      <input
                        id="email"
                        type="email"
                        required
                        aria-required="true"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="naam@voorbeeld.nl"
                        className="w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="category" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                        Categorie <span className="text-red-600" aria-hidden="true">*</span>
                      </label>
                      <select
                        id="category"
                        value={category}
                        required
                        aria-required="true"
                        onChange={(e) => setCategory(e.target.value as ContactCategory)}
                        className="w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                      >
                        <option value="algemeen">Algemene vraag / Informatie</option>
                        <option value="educatie">Educatie &amp; Scholen</option>
                        <option value="donatie">Donaties &amp; Erfgoed Adoptie</option>
                        <option value="archief">Archief &amp; Verhalen</option>
                        <option value="samenwerking">Samenwerking &amp; Partners</option>
                      </select>
                    </div>

                    <div>
                      <label htmlFor="subject" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                        Onderwerp <span className="text-red-600" aria-hidden="true">*</span>
                      </label>
                      <input
                        id="subject"
                        type="text"
                        required
                        aria-required="true"
                        value={subject}
                        onChange={(e) => setSubject(e.target.value)}
                        placeholder="Waar gaat uw vraag over?"
                        className="w-full px-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                      />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="message" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                      Bericht <span className="text-red-600" aria-hidden="true">*</span>
                    </label>
                    <textarea
                      id="message"
                      required
                      aria-required="true"
                      rows={5}
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      placeholder="Schrijf hier uw toelichting of vraag..."
                      className="w-full px-4 py-3 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50 leading-relaxed"
                    />
                  </div>

                  <HCaptchaWidget onVerify={setHcaptchaToken} className="pt-2" />

                  <button
                    type="submit"
                    disabled={loading}
                    aria-busy={loading}
                    className="w-full bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm py-3 px-4 rounded-xl transition-colors disabled:opacity-50"
                  >
                    {loading ? 'Verzenden...' : 'Verstuur Bericht'}
                  </button>
                </form>
              </div>
            )}
          </div>
        </div>

        {/* FAQs */}
        <div className="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-xs">
          <div className="flex items-center gap-2 mb-6">
            <HelpCircle className="w-5 h-5 text-amber-800" aria-hidden="true" />
            <h2 className="font-serif font-bold text-stone-900 text-xl">Veelgestelde Vragen</h2>
          </div>
          <div className="divide-y divide-stone-100">
            {faqs.map((faq, i) => (
              <div key={i} className="py-4 first:pt-0 last:pb-0">
                <h3 className="font-serif font-bold text-stone-900 text-sm mb-1.5">{faq.q}</h3>
                <p className="text-xs text-stone-600 leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
