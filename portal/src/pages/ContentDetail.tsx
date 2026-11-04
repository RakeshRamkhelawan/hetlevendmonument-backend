import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  MapPin,
  Calendar,
  User,
  ShieldAlert,
  Share2,
  FileText,
  Clock,
  Sparkles,
  ExternalLink,
  Download,
} from 'lucide-react';
import { api } from '../api/client';
import { TagBadge } from '../components/TagBadge';
import { Map } from '../components/Map';
import { FormattedText } from '../components/FormattedText';
import { AntwoordFormulier } from '../components/AntwoordFormulier';
import { ExtraBestanden, HoofdMedia, isBeveiligd } from '../components/VerhaalMedia';
import type { FoundationContentDetail, GeoFeature, WerkbladVraag } from '../types';

export const ContentDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [content, setContent] = useState<FoundationContentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Waar het item vandaan kwam: openbaar, via de klassessie (leerling) of als docent.
  const [bron, setBron] = useState<'publiek' | 'edu' | 'docent'>('publiek');

  useEffect(() => {
    if (!id) return;
    const fetchDetail = async () => {
      setLoading(true);
      try {
        let data: FoundationContentDetail;
        let herkomst: 'publiek' | 'edu' | 'docent' = 'publiek';
        try {
          data = await api.getContentDetail(id);
        } catch (publiekeFout) {
          // Werkbladen staan niet openbaar maar in de educatieve omgeving (visibility edu).
          // Met een actieve klassessie haalt de pagina ze daar op; een ingelogde docent via
          // de docentenomgeving (BE-EP-055). Anders blijft de oorspronkelijke fout staan.
          try {
            data = await api.getEduContentDetail(id);
            herkomst = 'edu';
          } catch {
            if (!api.getAuthToken()) throw publiekeFout;
            try {
              data = await api.getLesmateriaalDetail(id);
              herkomst = 'docent';
            } catch {
              throw publiekeFout;
            }
          }
        }
        setContent(data);
        setBron(herkomst);
      } catch (err) {
        console.error('Fout bij ophalen verhaal:', err);
        setError('Het opgevraagde erfgoeditem kon niet worden geladen.');
      } finally {
        setLoading(false);
      }
    };
    fetchDetail();
  }, [id]);

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-20 text-center">
        <div className="inline-block animate-spin w-8 h-8 border-4 border-amber-800 border-t-transparent rounded-full mb-4"></div>
        <p className="text-stone-600 font-medium">Verhaal wordt geladen...</p>
      </div>
    );
  }

  if (error || !content) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-20 text-center">
        <div className="w-12 h-12 bg-red-100 text-red-700 rounded-full flex items-center justify-center mx-auto mb-4">
          <ShieldAlert className="w-6 h-6" />
        </div>
        <h2 className="font-serif text-2xl font-bold text-stone-900 mb-2">Item niet gevonden</h2>
        <p className="text-stone-600 text-sm mb-6">{error || 'Dit item bestaat niet of is verwijderd.'}</p>
        <Link
          to="/ontdekken"
          className="inline-flex items-center gap-2 bg-amber-800 hover:bg-amber-700 text-white px-5 py-2.5 rounded-xl font-semibold text-sm transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Terug naar overzicht
        </Link>
      </div>
    );
  }

  const mapFeatures: GeoFeature[] =
    content.lat && content.lng
      ? [
          {
            type: 'Feature',
            geometry: {
              type: 'Point',
              coordinates: [content.lng, content.lat],
            },
            properties: {
              id: content.id,
              title: content.title,
              location_name: content.location_name || '',
              file_url: content.file_url,
            },
          },
        ]
      : [];

  const isAudio = content.file_mime?.startsWith('audio/') || content.content_type === 'audio';
  const isLesmateriaal = ['educational_workbook', 'teacher_guide'].includes(String(content.content_type));
  // BE-EP-057: een curator of de inzender bekijkt een verhaal dat nog niet openbaar is.
  const beveiligd = bron === 'publiek' && isBeveiligd(content.status);

  return (
    <article className="min-h-screen bg-[#FDFBF7] py-10">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Navigation & Actions */}
        <div className="flex items-center justify-between gap-4 mb-8">
          <Link
            to="/ontdekken"
            className="inline-flex items-center gap-2 text-xs font-semibold text-stone-600 hover:text-stone-900 bg-white px-3 py-1.5 rounded-xl border border-stone-200 transition-colors shadow-xs"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Terug naar verhalen
          </Link>

          <div className="flex items-center gap-2">
            {content.file_url && (
              <a
                href={api.getMediaUrl(content.id, { download: true })}
                download
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-700 bg-white hover:bg-stone-50 px-3 py-1.5 rounded-xl border border-stone-200 transition-colors shadow-xs"
                title="Download origineel mediabestand"
              >
                <Download className="w-3.5 h-3.5" />
                Download
              </a>
            )}
            <button
              onClick={handleShare}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-700 bg-white hover:bg-stone-50 px-3 py-1.5 rounded-xl border border-stone-200 transition-colors shadow-xs"
            >
              <Share2 className="w-3.5 h-3.5" />
              {copied ? 'Link Gekopieerd!' : 'Delen'}
            </button>
            <Link
              to={`/ntd?content_id=${content.id}&title=${encodeURIComponent(content.title)}`}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-900 bg-amber-50 hover:bg-amber-100 px-3 py-1.5 rounded-xl border border-amber-200 transition-colors"
            >
              <ShieldAlert className="w-3.5 h-3.5 text-amber-800" />
              Melden (NTD)
            </Link>
          </div>
        </div>

        {/* Header Block */}
        <header className="mb-8">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider bg-amber-100 text-amber-900 border border-amber-200">
              {content.category || 'Erfgoed'}
            </span>
            {content.location_name && (
              <span className="flex items-center gap-1 text-xs text-stone-600 font-medium bg-stone-100 px-2.5 py-1 rounded-md">
                <MapPin className="w-3 h-3 text-amber-800" />
                {content.location_name}
              </span>
            )}
          </div>

          <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-bold text-stone-900 leading-tight mb-4">
            {content.title}
          </h1>

          <div className="flex flex-wrap items-center gap-4 text-xs text-stone-500 pb-6 border-b border-stone-200">
            <span className="flex items-center gap-1.5">
              <User className="w-3.5 h-3.5" />
              {content.is_anonymous ? 'Anonieme inzender' : content.creator_name || 'Levend Monument Archief'}
            </span>
            <span className="flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5" />
              {new Date(content.created_at).toLocaleDateString('nl-NL', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </span>
            {content.duration_seconds && (
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                {Math.round(content.duration_seconds / 60)} min audio
              </span>
            )}
          </div>
        </header>

        {/* Media Block (WCAG 1.2 Tijdgebonden media); extra bestanden BE-EP-057 */}
        {content.file_url && <HoofdMedia content={content} beveiligd={beveiligd} />}
        <ExtraBestanden content={content} beveiligd={beveiligd} />

        {/* Grid Layout: Main story + Sidebar metadata */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
          {/* Main Story Body / Transcript */}
          <div className="lg:col-span-2 space-y-8">
            <section
              id="story-transcript-content"
              aria-label={isAudio ? 'Schriftelijk transcript van het audio getuigenis' : 'Het Verhaal'}
              className="bg-white rounded-2xl p-6 sm:p-8 border border-stone-200 shadow-xs"
            >
              <h2 className="font-serif text-xl font-bold text-stone-900 mb-2 pb-2 border-b border-stone-100 flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-amber-800" aria-hidden="true" />
                  {isAudio ? 'Transcriptie & Verhaal' : isLesmateriaal ? 'Lesmateriaal' : 'Het Verhaal'}
                </span>
                {isAudio && (
                  <span className="text-xs font-sans font-semibold text-amber-900 bg-amber-100 px-2.5 py-1 rounded-md">
                    Toegankelijk Transcript
                  </span>
                )}
              </h2>
              <div className="max-w-none font-normal">
                <FormattedText text={content.body || content.description || 'Geen verhaaltekst beschikbaar.'} />
              </div>
            </section>

            {bron === 'edu' &&
              content.content_type === 'educational_workbook' &&
              Array.isArray(content.metadata?.vragen) &&
              (content.metadata?.vragen as WerkbladVraag[]).length > 0 && (
                <AntwoordFormulier contentId={content.id} vragen={content.metadata?.vragen as WerkbladVraag[]} />
              )}

            {/* AI Generated Context / NDE Tags */}
            {content.tags && content.tags.length > 0 && (
              <div className="bg-amber-50/70 rounded-2xl p-6 border border-amber-200/80">
                <div className="flex items-center gap-2 mb-3">
                  <Sparkles className="w-4 h-4 text-amber-800" />
                  <h3 className="font-serif font-bold text-amber-950 text-sm">
                    Netwerk Digitaal Erfgoed (NDE) Taxonomie
                  </h3>
                </div>
                <p className="text-xs text-stone-600 mb-4">
                  Deze labels zijn verrijkt volgens de NDE-standaarden voor interoperabiliteit met landelijke archieven.
                </p>
                <div className="flex flex-wrap gap-2">
                  {content.tags.map((tag) => (
                    <TagBadge key={tag.id || tag.tag} tag={tag} />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Geo Location Mini-Map */}
            {mapFeatures.length > 0 && (
              <div className="bg-white rounded-2xl p-5 border border-stone-200 shadow-xs">
                <h3 className="font-serif font-bold text-stone-900 text-sm mb-3 flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-amber-800" />
                  Locatie op de kaart
                </h3>
                <div className="h-48 rounded-xl overflow-hidden mb-2">
                  <Map
                    features={mapFeatures}
                    initialCenter={[content.lng!, content.lat!]}
                    initialZoom={12}
                    className="w-full h-full min-h-0"
                  />
                </div>
                <div className="text-xs text-stone-500">
                  <span className="font-medium text-stone-800">{content.location_name || 'Onbekende locatie'}</span>
                  <br />
                  {content.lat?.toFixed(4)}° N, {content.lng?.toFixed(4)}° E
                </div>
              </div>
            )}

            {/* Archive & Provenance Details */}
            <div className="bg-white rounded-2xl p-5 border border-stone-200 shadow-xs text-xs space-y-3">
              <h3 className="font-serif font-bold text-stone-900 text-sm pb-2 border-b border-stone-100">
                Archief &amp; Herkomst
              </h3>
              <div>
                <span className="text-stone-400 block font-medium">Levend Monument ID</span>
                <span className="font-mono text-stone-700 select-all">{content.id}</span>
              </div>
              <div>
                <span className="text-stone-400 block font-medium">Licentie &amp; Hergebruik</span>
                <span className="text-stone-800 font-semibold">{content.license || 'Creative Commons CC-BY 4.0'}</span>
              </div>
              <div>
                <span className="text-stone-400 block font-medium">OAI-PMH Harvester</span>
                <Link
                  to="/data-export"
                  className="text-amber-800 hover:underline inline-flex items-center gap-1 font-medium mt-0.5"
                >
                  Open Data Export &amp; Specificaties
                  <ExternalLink className="w-3 h-3" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
};
