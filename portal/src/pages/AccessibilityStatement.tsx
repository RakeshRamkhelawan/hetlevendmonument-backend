import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, CheckCircle2, AlertTriangle, ArrowLeft, Mail, FileText, Compass, ExternalLink } from 'lucide-react';

export const AccessibilityStatement: React.FC = () => {
  return (
    <article className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <Link
          to="/ontdekken"
          className="inline-flex items-center gap-2 text-xs font-semibold text-stone-700 hover:text-stone-900 bg-white px-3 py-1.5 rounded-xl border border-stone-200 transition-colors shadow-xs mb-8"
        >
          <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
          Terug naar verhalen
        </Link>

        {/* Header Block */}
        <header className="mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-100 text-emerald-900 text-xs font-semibold uppercase tracking-wider mb-4 border border-emerald-200">
            <ShieldCheck className="w-4 h-4 text-emerald-700" aria-hidden="true" />
            Wettelijke Verantwoording
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-bold text-stone-900 leading-tight mb-4">
            Toegankelijkheidsverklaring
          </h1>
          <p className="text-stone-700 text-base leading-relaxed max-w-3xl">
            Het Levend Monument zet zich in om haar digitale diensten drempelvrij en universeel toegankelijk te maken
            voor iedereen, inclusief mensen met een visuele, auditieve, motorische of cognitieve beperking, conform het{' '}
            <strong>Besluit digitale toegankelijkheid overheid</strong> en de Europese norm <strong>EN 301 549</strong>.
          </p>
        </header>

        {/* Status Card */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-stone-200 shadow-xs mb-10">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-6 border-b border-stone-100">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-stone-600 block mb-1">
                Toegankelijkheidsstatus
              </span>
              <h2 className="font-serif text-2xl font-bold text-stone-900 flex items-center gap-2">
                <span className="w-8 h-8 rounded-lg bg-emerald-700 text-white inline-flex items-center justify-center text-sm font-sans font-bold">
                  B
                </span>
                Voldoet Gedeeltelijk (WCAG 2.1 Niveau AA)
              </h2>
            </div>
            <div className="text-xs text-stone-600 bg-stone-50 px-3 py-2 rounded-xl border border-stone-200">
              Laatste auditdatum: <strong>11 september 2026</strong>
            </div>
          </div>

          <p className="text-sm text-stone-700 leading-relaxed mt-4">
            Deze verklaring is van toepassing op het openbare webportaal van <strong>Het Levend Monument</strong>. De
            status <em>Voldoet Gedeeltelijk</em> betekent dat de kern van de applicatie is ontworpen en getest conform
            WCAG 2.1 AA, en dat voor complexe componenten (zoals de GIS-kaart en archiefmedia) volwaardige toegankelijke
            alternatieven zijn ingericht.
          </p>
        </div>

        {/* Maatregelen & Standaarden */}
        <section aria-labelledby="maatregelen-heading" className="space-y-6 mb-10">
          <h2 id="maatregelen-heading" className="font-serif text-2xl font-bold text-stone-900 flex items-center gap-2">
            <CheckCircle2 className="w-6 h-6 text-amber-800" aria-hidden="true" />
            Genomen Maatregelen voor Toegankelijkheid
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl p-6 border border-stone-200 shadow-xs">
              <h3 className="font-serif font-bold text-stone-900 text-base mb-2">
                Toetsenbordnavigatie &amp; Focus
              </h3>
              <p className="text-xs text-stone-700 leading-relaxed mb-3">
                Alle functionaliteiten zijn volledig bedienbaar zonder muis via gestandaardiseerde toetsen (`Tab`, `Enter`,
                `Spatie`, `Escape`). Bovenin elke pagina bevindt zich een directe <em>Skip-to-content</em> link.
              </p>
              <div className="text-xs font-semibold text-emerald-800 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                WCAG 2.1 SC 2.1.1 &amp; 2.4.1 Conform
              </div>
            </div>

            <div className="bg-white rounded-2xl p-6 border border-stone-200 shadow-xs">
              <h3 className="font-serif font-bold text-stone-900 text-base mb-2">
                Kleurcontrast &amp; Typografie
              </h3>
              <p className="text-xs text-stone-700 leading-relaxed mb-3">
                Teksten en interactieve elementen voldoen aan een contrastratio van minimaal <strong>4.5:1</strong> ten
                opzichte van de achtergrond (en 3:1 voor grote tekst). Focus-indicators zijn altijd duidelijk zichtbaar.
              </p>
              <div className="text-xs font-semibold text-emerald-800 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                WCAG 2.1 SC 1.4.3 Conform
              </div>
            </div>

            <div className="bg-white rounded-2xl p-6 border border-stone-200 shadow-xs">
              <h3 className="font-serif font-bold text-stone-900 text-base mb-2">
                Formulieren &amp; Foutafhandeling
              </h3>
              <p className="text-xs text-stone-700 leading-relaxed mb-3">
                Alle invoervelden zijn voorzien van expliciet gekoppelde labels (`htmlFor`). Dynamische statusmeldingen
                en fouten worden direct gemarkeerd met `aria-describedby`, `aria-live` en `role="alert"`.
              </p>
              <div className="text-xs font-semibold text-emerald-800 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                WCAG 2.1 SC 3.3.1 &amp; 3.3.2 Conform
              </div>
            </div>

            <div className="bg-white rounded-2xl p-6 border border-stone-200 shadow-xs">
              <h3 className="font-serif font-bold text-stone-900 text-base mb-2">
                Schermlezer &amp; Semantiek
              </h3>
              <p className="text-xs text-stone-700 leading-relaxed mb-3">
                Pagina&apos;s zijn gestructureerd met HTML5 landmarks (`header`, `nav`, `main`, `footer`), consistente kopniveaus
                (`h1` t/m `h3`) en beschrijvende alt-teksten voor alle informatieve afbeeldingen.
              </p>
              <div className="text-xs font-semibold text-emerald-800 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                WCAG 2.1 SC 1.1.1 &amp; 1.3.1 Conform
              </div>
            </div>
          </div>
        </section>

        {/* Toegankelijke Alternatieven & Uitzonderingen */}
        <section aria-labelledby="alternatieven-heading" className="bg-amber-50/60 rounded-3xl p-6 sm:p-8 border border-amber-200 mb-10">
          <h2 id="alternatieven-heading" className="font-serif text-2xl font-bold text-stone-900 mb-4 flex items-center gap-2">
            <AlertTriangle className="w-6 h-6 text-amber-800" aria-hidden="true" />
            Complexe Onderdelen &amp; Toegankelijke Alternatieven
          </h2>

          <div className="space-y-4 text-sm text-stone-800 leading-relaxed">
            <div className="bg-white rounded-2xl p-5 border border-amber-200">
              <h3 className="font-serif font-bold text-stone-900 text-base mb-1.5 flex items-center gap-2">
                <Compass className="w-4 h-4 text-amber-800" aria-hidden="true" />
                Geografische WebGL Kaart (MapLibre)
              </h3>
              <p className="text-xs text-stone-700 mb-2">
                Omdat interactieve WebGL vectorkaarten visueel complex zijn en geen semantische DOM-structuur bieden voor
                schermlezers, is er een <strong>gelijkwaardig alternatief</strong> ingebouwd: de <em>Toegankelijke Lijstweergave</em>.
                Via de weergaveschakelaar op de kaartpagina kunnen bezoekers direct schakelen naar een gestructureerde lijst van
                alle erfgoedlocaties en verhalen.
              </p>
              <Link to="/kaart" className="text-xs font-semibold text-amber-800 hover:underline inline-flex items-center gap-1">
                Bekijk de erfgoedkaart en het lijstalternatief &rarr;
              </Link>
            </div>

            <div className="bg-white rounded-2xl p-5 border border-amber-200">
              <h3 className="font-serif font-bold text-stone-900 text-base mb-1.5 flex items-center gap-2">
                <FileText className="w-4 h-4 text-amber-800" aria-hidden="true" />
                Mondelinge Geschiedenis &amp; Audio Opnamen
              </h3>
              <p className="text-xs text-stone-700">
                Voor gesproken getuigenissen en oral history interviews wordt direct onder de audiospeler het volledige
                schriftelijke transcript ter beschikking gesteld, zodat auditieve inhoud ook toegankelijk is voor doven en
                slechthorenden (WCAG 1.2.1).
              </p>
            </div>
          </div>
        </section>

        {/* Contact & Klachtenloket */}
        <section aria-labelledby="contact-heading" className="bg-white rounded-3xl p-6 sm:p-8 border border-stone-200 shadow-xs mb-10">
          <h2 id="contact-heading" className="font-serif text-2xl font-bold text-stone-900 mb-3 flex items-center gap-2">
            <Mail className="w-6 h-6 text-amber-800" aria-hidden="true" />
            Feedback en Contactgegevens
          </h2>
          <p className="text-sm text-stone-700 leading-relaxed mb-4">
            Ervaart u ondanks onze maatregelen een toegankelijkheidsprobleem op deze website? Of heeft u een vraag over de
            toegankelijkheid van een specifiek historisch document of verhaal? Neem dan contact op met onze a11y-coordinator:
          </p>

          <div className="bg-stone-50 rounded-2xl p-5 border border-stone-200 space-y-2 text-xs text-stone-800">
            <div>
              <strong>Organisatie:</strong> Stichting Ketikotivlaardingen.NL (KvK 95265104)
            </div>
            <div>
              <strong>E-mailadres:</strong>{' '}
              <a href="mailto:info@hetlevendmonument.nl" className="text-amber-800 underline font-semibold">
                info@hetlevendmonument.nl
              </a>
            </div>
            <div>
              <strong>Reactietermijn:</strong> U ontvangt binnen 5 werkdagen een inhoudelijke reactie en een plan van aanpak.
            </div>
          </div>
        </section>

        {/* Handhavingsprocedure */}
        <footer className="text-xs text-stone-600 border-t border-stone-200 pt-6">
          <p className="leading-relaxed">
            Bent u niet tevreden over de wijze waarop uw melding is afgehandeld, of hebben wij niet tijdig gereageerd? Dan
            kunt u zich wenden tot de <strong>Nationale Ombudsman</strong> via{' '}
            <a
              href="https://www.nationaleombudsman.nl"
              target="_blank"
              rel="noreferrer"
              className="text-amber-800 underline inline-flex items-center gap-0.5"
            >
              www.nationaleombudsman.nl
              <ExternalLink className="w-3 h-3" aria-hidden="true" />
            </a>.
          </p>
        </footer>
      </div>
    </article>
  );
};
