import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Lock } from 'lucide-react';

interface Sectie {
  titel: string;
  inhoud: React.ReactNode;
}

const CONTACT = 'privacy@hetlevendmonument.nl';

const secties: Sectie[] = [
  {
    titel: '1. Wie zijn wij',
    inhoud: (
      <p>
        Het Levend Monument is een digitaal erfgoedplatform van Stichting Ketikotivlaardingen.NL (KvK 95265104, gevestigd in Vlaardingen). De stichting is verantwoordelijk voor de verwerking van persoonsgegevens op
        deze website. Vragen over privacy stelt u via <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.
      </p>
    ),
  },
  {
    titel: '2. Welke gegevens wij verwerken en waarom',
    inhoud: (
      <ul>
        <li>
          <strong>Account</strong> (e-mailadres, weergavenaam): om in te loggen met een inloglink en uw inzendingen te
          beheren. Grondslag: uitvoering van de dienst die u gebruikt.
        </li>
        <li>
          <strong>Inzendingen</strong> (verhaal, foto, audio of video, plaats, en desgewenst uw naam): om ze na
          beoordeling door een curator te publiceren. U kunt anoniem inzenden; dan tonen wij geen naam. U bevestigt bij
          het inzenden dat u de rechten heeft en dat herkenbare personen toestemming gaven. Grondslag: toestemming.
        </li>
        <li>
          <strong>Nieuwsbrief</strong> (e-mailadres, en als bewijs van uw toestemming het moment, IP-adres en
          browsergegevens van uw aanmelding): pas na bevestiging via een e-mail (dubbele aanmelding). Afmelden kan met
          de link in elke nieuwsbrief. Grondslag: toestemming.
        </li>
        <li>
          <strong>Contactformulier</strong> (naam, e-mailadres, bericht): om uw vraag te beantwoorden. Grondslag:
          gerechtvaardigd belang.
        </li>
        <li>
          <strong>Donaties</strong> (naam, e-mailadres, bedrag en eventueel een bericht): betaling verloopt via
          Stripe, dat daarvoor ook uw naam en e-mailadres ontvangt; wij ontvangen en bewaren geen bank- of
          kaartgegevens. Kiest u niet voor anoniem doneren, dan tonen wij uw naam, het bedrag en uw bericht op de
          donatiepagina. Grondslag: uitvoering van de donatie en de wettelijke bewaarplicht voor de administratie.
        </li>
        <li>
          <strong>Verwijderverzoeken</strong> (naam, e-mailadres, motivering): om een melding over een inzending te
          behandelen. Grondslag: wettelijke plicht en gerechtvaardigd belang.
        </li>
        <li>
          <strong>Leeromgeving voor scholen</strong>: van docenten verwerken wij naam, e-mailadres, school, functie
          en een eventuele toelichting, om een aanvraag voor een docentaccount te beoordelen en het account te
          beheren. Leerlingen maken geen account aan en geven geen e-mailadres op. Bij een werkblad vullen zij alleen
          een voornaam of bijnaam en hun antwoorden in; die ziet alleen hun eigen docent. Grondslag: uitvoering van
          de dienst voor de school.
        </li>
        <li>
          <strong>Beveiliging</strong>: ons systeem verwerkt uw IP-adres om misbruik tegen te gaan (bijvoorbeeld te
          veel verzoeken achter elkaar) en legt het vast in technische logbestanden van de server. Grondslag:
          gerechtvaardigd belang.
        </li>
      </ul>
    ),
  },
  {
    titel: '3. Wie ontvangt gegevens (verwerkers)',
    inhoud: (
      <ul>
        <li>
          <strong>Microsoft Azure</strong>: hosting van de website, de database en de bestanden, in een datacenter in
          de Europese Unie (Ierland).
        </li>
        <li>
          <strong>Brevo</strong>: het versturen van inloglinks, bevestigingen en de nieuwsbrief.
        </li>
        <li>
          <strong>Stripe</strong>: het afhandelen van donaties.
        </li>
        <li>
          <strong>hCaptcha</strong>: een controle tegen spam bij formulieren.
        </li>
        <li>
          <strong>Mistral AI</strong> (Frankrijk): de tekst van een inzending wordt gebruikt om automatisch labels voor
          te stellen (zoals periode en plaats). Een curator controleert die labels altijd. Er worden geen
          contactgegevens meegestuurd.
        </li>
        <li>
          <strong>OpenStreetMap</strong>: de kaartafbeeldingen worden van de servers van OpenStreetMap geladen; daarbij
          ziet OpenStreetMap uw IP-adres.
        </li>
      </ul>
    ),
  },
  {
    titel: '4. Archivering',
    inhoud: (
      <p>
        Gepubliceerde verhalen worden periodiek in een archiefformaat (BagIt) vastgelegd, zodat het erfgoed ook op lange
        termijn bewaard blijft. Bij anonieme inzendingen staat er geen naam in het archief en zijn de
        kaartcoordinaten afgerond. E-mailadressen van inzenders gaan nooit het archief in; alleen het algemene
        contactadres van de stichting staat erin.
      </p>
    ),
  },
  {
    titel: '5. Hoe lang wij gegevens bewaren',
    inhoud: (
      <p>
        Wij bewaren gegevens niet langer dan nodig voor het doel. Na afmelding voor de nieuwsbrief krijgt u geen
        nieuwsbrief meer; uw e-mailadres en het bewijs van uw eerdere toestemming bewaren wij dan nog om te kunnen
        aantonen dat wij u met toestemming mailden. Wilt u dat ook die gegevens worden gewist, mail ons dan. Gegevens over donaties bewaren wij zo lang de wettelijke bewaarplicht voor de administratie dat vereist.
        Gepubliceerde verhalen blijven zichtbaar tot u of een ander om verwijdering vraagt en dat verzoek wordt
        toegekend. Antwoorden van leerlingen verwijderen wij automatisch 8 weken nadat ze voor het eerst zijn
        opgeslagen. Gegevens van een docentaccount bewaren wij zolang het account bestaat.
      </p>
    ),
  },
  {
    titel: '6. Uw rechten',
    inhoud: (
      <>
        <p>
          U mag uw gegevens inzien, laten verbeteren of laten verwijderen, en bezwaar maken tegen een verwerking.
          Daarvoor mailt u naar <a href={`mailto:${CONTACT}`}>{CONTACT}</a>. Uw eigen inzendingen ziet u na het
          inloggen onder <Link to="/mijn-inzendingen">Mijn inzendingen</Link>. Wilt u een gepubliceerde inzending laten
          verwijderen, gebruik dan het <Link to="/ntd">meldformulier</Link>.
        </p>
        <p>
          Bent u het niet eens met hoe wij met uw gegevens omgaan, dan kunt u een klacht indienen bij de{' '}
          <a href="https://autoriteitpersoonsgegevens.nl" target="_blank" rel="noreferrer">
            Autoriteit Persoonsgegevens (opent in een nieuw venster)
          </a>
          .
        </p>
      </>
    ),
  },
  {
    titel: '7. Cookies en lokale opslag',
    inhoud: (
      <p>
        Wij gebruiken geen tracking- of advertentiecookies. Na het inloggen bewaart uw browser een sleutel en uw
        accountgegevens (zoals uw e-mailadres), zodat u ingelogd blijft; beide verdwijnen bij uitloggen. De
        spamcontrole van hCaptcha kan bij formulieren eigen technische cookies plaatsen. Bij een werkblad bewaart
        de browser van een leerling een willekeurige code, zodat de leerling de eigen antwoorden terugziet; die code
        zegt niets over wie de leerling is. De lettertypes van deze website worden door onszelf geleverd, niet
        door Google.
      </p>
    ),
  },
];

export const Privacy: React.FC = () => (
  <article className="min-h-screen bg-[#FDFBF7] py-12">
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <Link
        to="/ontdekken"
        className="inline-flex items-center gap-2 text-xs font-semibold text-stone-700 hover:text-stone-900 bg-white px-3 py-1.5 rounded-xl border border-stone-200 transition-colors shadow-xs mb-8"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
        Terug naar verhalen
      </Link>
      <header className="mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-semibold uppercase tracking-wider mb-4 border border-amber-200">
          <Lock className="w-4 h-4" aria-hidden="true" />
          Privacy
        </div>
        <h1 className="font-serif text-3xl sm:text-4xl font-bold text-stone-900 leading-tight mb-4">Privacyverklaring</h1>
        <p className="text-stone-700 text-base leading-relaxed">
          Hoe Het Levend Monument met uw persoonsgegevens omgaat. Versie van 1 november 2026.
        </p>
      </header>
      <div className="space-y-8">
        {secties.map((s) => (
          <section key={s.titel} className="bg-white rounded-2xl p-6 border border-stone-200 prose prose-stone max-w-none text-sm leading-relaxed [&_ul]:list-disc [&_ul]:pl-5 [&_li]:mb-2 [&_a]:text-amber-800 [&_a]:underline">
            <h2 className="font-serif text-xl font-bold text-stone-900 mb-3">{s.titel}</h2>
            {s.inhoud}
          </section>
        ))}
      </div>
    </div>
  </article>
);
