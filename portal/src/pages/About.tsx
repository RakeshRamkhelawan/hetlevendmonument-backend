import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Landmark, Compass, ShieldCheck, Sparkles, ArrowRight, Users, BookOpen, Mail } from 'lucide-react';
import { useTenant } from '../context/TenantContext';

export const About: React.FC = () => {
  const { tenant, settings, loadSettings } = useTenant();

  useEffect(() => {
    if (!settings) {
      void loadSettings();
    }
  }, [settings, loadSettings]);

  const platformName = settings?.platform_name_nl || tenant?.name || 'Het Levend Monument';
  const aboutText = settings?.about_nl;
  const guidelinesText = settings?.guidelines_nl;
  const contactEmail = settings?.contact_email;
  const logoUrl = settings?.logo_url;

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Hero */}
        <div className="text-center max-w-2xl mx-auto mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-semibold uppercase tracking-wider mb-4">
            <Landmark className="w-4 h-4 text-amber-800" aria-hidden="true" />
            Over {platformName}
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-bold text-stone-900 mb-4 leading-tight">
            {settings?.platform_name_nl ? `Over ${platformName}` : 'Een Levende Brug tussen Verleden, Heden en Toekomst'}
          </h1>
          <p className="text-stone-600 text-sm sm:text-base leading-relaxed">
            {aboutText ||
              'Het Levend Monument is een openbaar, participatief digitaal erfgoedarchief. We documenteren en bewaren de ongehoorde verhalen, stemmen en getuigenissen van onze gedeelde geschiedenis.'}
          </p>
        </div>

        {/* Featured Image or Logo */}
        {logoUrl ? (
          <div className="rounded-3xl overflow-hidden mb-14 border border-stone-200 shadow-xs bg-white p-6 sm:p-10 flex flex-col items-center justify-center">
            <img
              src={logoUrl}
              alt={`Logo van ${platformName}`}
              className="max-h-48 max-w-full object-contain mb-4"
              onError={(e) => {
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
            <span className="text-xs text-stone-500 font-medium tracking-wide uppercase">
              Officieel Erfgoedarchief &bull; {platformName}
            </span>
          </div>
        ) : (
          <div className="rounded-3xl overflow-hidden mb-14 border border-stone-200 shadow-sm">
            <img
              src="/over-gemeenschap.jpg"
              alt="Gemeenschap en Erfgoed"
              className="w-full h-80 sm:h-96 object-cover"
            />
          </div>
        )}

        {/* Mission Statement & Guidelines */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">
          <div className="bg-white p-6 sm:p-8 rounded-3xl border border-stone-200 shadow-xs">
            <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-900 flex items-center justify-center mb-4">
              <Compass className="w-5 h-5" aria-hidden="true" />
            </div>
            <h2 className="font-serif font-bold text-stone-900 text-xl mb-3">Onze Missie</h2>
            <p className="text-xs text-stone-600 leading-relaxed whitespace-pre-line">
              {aboutText ||
                'Geschiedenis wordt traditioneel verteld vanuit officiële overheidsdocumenten en gevestigde archieven. Het Levend Monument verrijkt dit beeld door de intieme, persoonlijke herinneringen van families, nakomelingen en gemeenschappen een permanente, gerespecteerde plek in het publieke domein te geven.'}
            </p>
          </div>

          <div className="bg-white p-6 sm:p-8 rounded-3xl border border-stone-200 shadow-xs">
            <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-900 flex items-center justify-center mb-4">
              <ShieldCheck className="w-5 h-5" aria-hidden="true" />
            </div>
            <h2 className="font-serif font-bold text-stone-900 text-xl mb-3">Ethisch &amp; Open</h2>
            <p className="text-xs text-stone-600 leading-relaxed">
              Alle bijdragen worden met de grootste zorg en discretie behandeld. Vertellers behouden te allen tijde
              zeggenschap over hun herinneringen en kunnen kiezen voor volledige anonimiteit. Alle openbare data wordt
              gestructureerd volgens de FAIR-principes en het Netwerk Digitaal Erfgoed (NDE).
            </p>
          </div>

          {guidelinesText && (
            <div className="col-span-1 md:col-span-2 bg-white p-6 sm:p-8 rounded-3xl border border-stone-200 shadow-xs">
              <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-900 flex items-center justify-center mb-4">
                <BookOpen className="w-5 h-5 text-amber-800" aria-hidden="true" />
              </div>
              <h2 className="font-serif font-bold text-stone-900 text-xl mb-3">Community- &amp; Gedragsrichtlijnen</h2>
              <p className="text-xs text-stone-600 leading-relaxed whitespace-pre-line">
                {guidelinesText}
              </p>
            </div>
          )}
        </div>

        {/* Pillars */}
        <div className="space-y-8 mb-16">
          <h2 className="font-serif text-2xl sm:text-3xl font-bold text-stone-900 text-center">Onze Drie Pijlers</h2>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div className="bg-white p-6 rounded-2xl border border-stone-200 shadow-xs text-center">
              <div className="w-12 h-12 rounded-full bg-stone-100 text-amber-800 flex items-center justify-center mx-auto mb-4">
                <Users className="w-6 h-6" aria-hidden="true" />
              </div>
              <h3 className="font-serif font-bold text-stone-900 text-base mb-2">Gemeenschap</h3>
              <p className="text-xs text-stone-500 leading-relaxed">
                Een platform voor en door de gemeenschap, waar individuele stemmen samenkomen in een collectief monument.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-stone-200 shadow-xs text-center">
              <div className="w-12 h-12 rounded-full bg-stone-100 text-amber-800 flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-6 h-6" aria-hidden="true" />
              </div>
              <h3 className="font-serif font-bold text-stone-900 text-base mb-2">Onderwijs</h3>
              <p className="text-xs text-stone-500 leading-relaxed">
                Direct inzetbaar lesmateriaal voor basisscholen, voortgezet onderwijs en mbo ter bevordering van historisch besef.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-stone-200 shadow-xs text-center">
              <div className="w-12 h-12 rounded-full bg-stone-100 text-amber-800 flex items-center justify-center mx-auto mb-4">
                <Sparkles className="w-6 h-6" aria-hidden="true" />
              </div>
              <h3 className="font-serif font-bold text-stone-900 text-base mb-2">Technologie</h3>
              <p className="text-xs text-stone-500 leading-relaxed">
                Geavanceerde geolocatiekaarten, OAI-PMH interoperabiliteit en AI-taxonomie voor landelijke erfgoedkoppeling.
              </p>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div className="bg-amber-900 text-white rounded-3xl p-8 sm:p-10 text-center shadow-md">
          <h2 className="font-serif text-2xl sm:text-3xl font-bold mb-3">Bouw mee aan het monument</h2>
          <p className="text-stone-300 text-sm max-w-lg mx-auto mb-6">
            Heeft u een familieverhaal, foto&apos;s uit het verleden of een audio-opname? Deel het vandaag en bewaar het voor
            toekomstige generaties.
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <Link
              to="/uploaden"
              className="bg-white text-stone-900 hover:bg-stone-100 font-semibold text-xs px-5 py-3 rounded-xl transition-colors inline-flex items-center gap-1.5"
            >
              Deel je Verhaal
              <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
            </Link>
            <Link
              to="/contact"
              className="bg-amber-950/70 hover:bg-amber-950 text-white font-semibold text-xs px-5 py-3 rounded-xl border border-amber-800 transition-colors"
            >
              Contact opnemen
            </Link>
          </div>
          {contactEmail && (
            <div className="mt-6 pt-6 border-t border-amber-800/60 flex items-center justify-center gap-2 text-xs text-amber-200">
              <Mail className="w-3.5 h-3.5" aria-hidden="true" />
              <span>
                Officiële stichtingscorrespondentie:{' '}
                <a href={`mailto:${contactEmail}`} className="underline font-semibold text-white hover:text-amber-100">
                  {contactEmail}
                </a>
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

