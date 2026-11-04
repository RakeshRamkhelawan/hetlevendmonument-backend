import React, { useState } from 'react';
import { Database, Copy, Check, ExternalLink, ShieldCheck } from 'lucide-react';
import { api } from '../api/client';

export const DataExport: React.FC = () => {
  const [copiedQuery, setCopiedQuery] = useState<string | null>(null);

  const tenantSlug = api.getTenantSlug();
  const baseUrl = window.location.origin;

  const oaiBase = `${baseUrl}/api/v1/${tenantSlug}/foundation/oai-pmh`;
  const sitemapUrl = `${baseUrl}/api/v1/foundation/sitemap.xml`;
  const mapBase = `${baseUrl}/api/v1/${tenantSlug}/foundation/map/bbox?sw_lat=51.4&sw_lng=3.9&ne_lat=52.4&ne_lng=4.9`;

  const queries = [
    {
      title: '1. OAI-PMH Identify',
      desc: 'Geeft metadata over de repository, protocoldetails en beheercontacten.',
      url: `${oaiBase}?verb=Identify`,
    },
    {
      title: '2. ListMetadataFormats',
      desc: 'Geeft de ondersteunde standaarden weer (zoals oai_dc en edm).',
      url: `${oaiBase}?verb=ListMetadataFormats`,
    },
    {
      title: '3. ListRecords (Dublin Core)',
      desc: 'Oogst openbare erfgoeditems met standaard Dublin Core tags.',
      url: `${oaiBase}?verb=ListRecords&metadataPrefix=oai_dc`,
    },
    {
      title: '4. GeoJSON Kaart Bbox API',
      desc: 'Haalt geolocaties en verhalen op binnen een geografische rechthoek.',
      url: mapBase,
    },
    {
      title: '5. XML Sitemap (Zoekmachine & NDE Harvester Index)',
      desc: 'Gestandaardiseerde sitemaps.org XML-index van alle goedgekeurde erfgoedstukken en portal-routes.',
      url: sitemapUrl,
    },
  ];

  const handleCopy = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopiedQuery(url);
    setTimeout(() => setCopiedQuery(null), 3000);
  };

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-10">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-semibold uppercase tracking-wider mb-3">
            <Database className="w-3.5 h-3.5 text-amber-800" />
            Netwerk Digitaal Erfgoed &amp; FAIR Data
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-stone-900 mb-3">
            Open Data &amp; OAI-PMH Harvester
          </h1>
          <p className="text-stone-600 text-sm leading-relaxed">
            Het Levend Monument stelt haar openbare collectie beschikbaar als interoperabele open data voor musea,
            universiteiten, archieven en ontwikkelaars via gestandaardiseerde protocollen.
          </p>
        </div>

        {/* Standards overview */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10 text-xs">
          <div className="bg-white p-5 rounded-2xl border border-stone-200 shadow-xs">
            <h3 className="font-serif font-bold text-stone-900 text-sm mb-1">OAI-PMH v2.0</h3>
            <p className="text-stone-500">
              Open Archives Initiative Protocol for Metadata Harvesting voor geautomatiseerde indexering.
            </p>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-stone-200 shadow-xs">
            <h3 className="font-serif font-bold text-stone-900 text-sm mb-1">Dublin Core &amp; EDM</h3>
            <p className="text-stone-500">
              Europeana Data Model en Dublin Core met NDE-termen voor historische taxonomie.
            </p>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-stone-200 shadow-xs">
            <h3 className="font-serif font-bold text-stone-900 text-sm mb-1">CC-BY 4.0 Licentie</h3>
            <p className="text-stone-500">
              Open licentie voor hergebruik met naamsvermelding van de oorspronkelijke verteller of instelling.
            </p>
          </div>
        </div>

        {/* Query Endpoints */}
        <div className="space-y-6 mb-12">
          <h2 className="font-serif text-2xl font-bold text-stone-900">Endpoints &amp; Voorbeeldopdrachten</h2>

          {queries.map((q, i) => (
            <div key={i} className="bg-white rounded-2xl p-5 sm:p-6 border border-stone-200 shadow-xs">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                <h3 className="font-serif font-bold text-stone-900 text-base">{q.title}</h3>
                <span className="text-[11px] font-semibold text-stone-400 font-mono uppercase">HTTP GET</span>
              </div>
              <p className="text-xs text-stone-500 mb-3">{q.desc}</p>
              <div className="flex items-center gap-2 bg-stone-900 text-stone-100 p-3 rounded-xl font-mono text-xs overflow-x-auto">
                <span className="flex-grow select-all break-all">{q.url}</span>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <button
                    onClick={() => handleCopy(q.url)}
                    className="p-1.5 hover:bg-stone-800 rounded-lg text-stone-400 hover:text-white transition-colors"
                    title={copiedQuery === q.url ? 'Gekopieerd' : 'Kopieer URL'}
                    aria-label={copiedQuery === q.url ? 'Gekopieerd' : 'Kopieer URL'}
                  >
                    {copiedQuery === q.url ? (
                      <Check className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                  <a
                    href={q.url}
                    target="_blank"
                    rel="noreferrer"
                    className="p-1.5 hover:bg-stone-800 rounded-lg text-stone-400 hover:text-white transition-colors"
                    title="Open in browser"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Ethical Guidelines */}
        <div className="bg-stone-100 rounded-3xl p-6 sm:p-8 border border-stone-200 text-xs space-y-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-amber-800" />
            <h3 className="font-serif font-bold text-stone-900 text-sm">Ethisch Gebruik van Erfgoeddata</h3>
          </div>
          <p className="text-stone-600 leading-relaxed">
            De data in Het Levend Monument bevat persoonlijke herinneringen en verhalen over gevoelig cultureel erfgoed.
            Onderzoekers en ontwikkelaars die data oogsten worden verzocht respectvol om te gaan met de context, de
            geanonimiseerde status van getuigenissen te respecteren en de bronvermelding accuraat weer te geven.
          </p>
        </div>
      </div>
    </div>
  );
};
