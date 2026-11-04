import React, { useEffect, useState } from 'react';
import { Download, FileText, Volume2 } from 'lucide-react';
import { api } from '../api/client';
import type { FoundationBestand, FoundationContentDetail } from '../types';

/** Een verhaal dat (nog) niet openbaar is: alleen curator, beheerder of inzender ziet het (BE-EP-057). */
export const isBeveiligd = (status: string | undefined | null): boolean =>
  status === 'pending' || status === 'rejected' || status === 'removed';

/**
 * De bron-URL van een bestand. Openbaar: de directe URL (zoals altijd). Beveiligd: een
 * img/audio/video-tag stuurt geen inlogtoken mee, dus eerst met het token een tijdelijke,
 * ondertekende URL ophalen (BE-EP-057).
 */
export const useMediaBron = (
  beveiligd: boolean,
  directeUrl: string,
  haalInfo: () => Promise<{ url: string }>,
): string | null => {
  const [bron, setBron] = useState<string | null>(beveiligd ? null : directeUrl);
  useEffect(() => {
    if (!beveiligd) {
      setBron(directeUrl);
      return;
    }
    let weg = false;
    setBron(null);
    haalInfo()
      .then((info) => {
        if (!weg) setBron(info.url);
      })
      .catch(() => {
        if (!weg) setBron(null);
      });
    return () => {
      weg = true;
    };
    // haalInfo is per render een nieuwe functie; de bron hangt alleen af van deze twee.
  }, [beveiligd, directeUrl]);
  return bron;
};

const soort = (mime: string | null | undefined, contentType?: string) => {
  if (mime?.startsWith('video/') || contentType === 'video') return 'video';
  if (mime?.startsWith('audio/') || contentType === 'audio') return 'audio';
  if (mime?.startsWith('image/')) return 'image';
  if (!mime && contentType !== 'document') return 'image';
  return 'document';
};

/** Het hoofdbestand van een verhaal (WCAG 1.2 Tijdgebonden media). */
export const HoofdMedia: React.FC<{ content: FoundationContentDetail; beveiligd: boolean }> = ({ content, beveiligd }) => {
  const wat = soort(content.file_mime, String(content.content_type));
  const stroom = wat === 'video' || wat === 'audio';
  const bron = useMediaBron(beveiligd, api.getMediaUrl(content.id, stroom ? { stream: true } : undefined), () =>
    api.getMediaInfo(content.id),
  );

  return (
    <div className="mb-10 rounded-2xl overflow-hidden border border-stone-200 bg-stone-900 shadow-sm" role="region" aria-label="Erfgoed mediaweergave">
      {!bron ? (
        <p className="p-8 text-center text-sm text-stone-200">Bestand wordt geladen...</p>
      ) : wat === 'video' ? (
        <video
          controls
          src={bron}
          aria-label={`Video-opname: ${content.title}`}
          aria-describedby="story-transcript-content"
          className="w-full max-h-[500px] mx-auto"
        >
          Uw browser ondersteunt de video-tag niet. Een schriftelijke transcriptie is hieronder beschikbaar.
        </video>
      ) : wat === 'audio' ? (
        <div className="p-8 bg-stone-800 flex flex-col items-center justify-center text-white">
          <Volume2 className="w-12 h-12 text-amber-400 mb-4 animate-pulse" aria-hidden="true" />
          <h2 className="font-serif font-semibold text-lg mb-4">Luister naar het gesproken getuigenis</h2>
          <audio
            controls
            src={bron}
            aria-label={`Mondelinge geschiedenis opname: ${content.title}`}
            aria-describedby="story-transcript-content"
            className="w-full max-w-md"
          >
            Uw browser ondersteunt het audio-element niet. Het volledige schriftelijke transcript is hieronder te lezen.
          </audio>
          <p className="text-xs text-stone-300 mt-3 text-center">
            Hieronder vindt u het officiële schriftelijke transcript van deze opname.
          </p>
        </div>
      ) : wat === 'document' ? (
        <a href={bron} className="flex items-center gap-3 p-6 text-white hover:underline" target="_blank" rel="noreferrer">
          <FileText className="w-6 h-6" aria-hidden="true" />
          Document openen
        </a>
      ) : (
        <div className="relative">
          <img src={bron} alt={`Historische afbeelding behorend bij: ${content.title}`} className="w-full max-h-[560px] object-cover mx-auto" />
        </div>
      )}
    </div>
  );
};

const ExtraBestand: React.FC<{ content: FoundationContentDetail; bestand: FoundationBestand; beveiligd: boolean }> = ({
  content,
  bestand,
  beveiligd,
}) => {
  const wat = soort(bestand.file_mime);
  const stroom = wat === 'video' || wat === 'audio';
  const bron = useMediaBron(
    beveiligd,
    api.getBestandMediaUrl(content.id, bestand.id, stroom ? { stream: true } : undefined),
    () => api.getBestandMediaInfo(content.id, bestand.id),
  );
  const nummer = bestand.volgorde;

  if (!bron) {
    return <li className="rounded-xl border border-stone-200 bg-stone-50 p-4 text-sm text-stone-600">Bestand {nummer} wordt geladen...</li>;
  }
  return (
    <li className="rounded-xl overflow-hidden border border-stone-200 bg-white">
      {wat === 'image' ? (
        <img src={bron} alt={`Afbeelding ${nummer} bij: ${content.title}`} className="w-full h-56 object-cover" loading="lazy" />
      ) : wat === 'video' ? (
        <video controls src={bron} aria-label={`Video ${nummer} bij: ${content.title}`} className="w-full max-h-72 bg-stone-900" />
      ) : wat === 'audio' ? (
        <div className="p-4">
          <audio controls src={bron} aria-label={`Geluidsopname ${nummer} bij: ${content.title}`} className="w-full" />
        </div>
      ) : (
        <a href={bron} target="_blank" rel="noreferrer" className="flex items-center gap-2 p-4 text-sm font-semibold text-amber-800 hover:underline">
          <Download className="w-4 h-4" aria-hidden="true" />
          Document {nummer} openen
        </a>
      )}
    </li>
  );
};

/** De bestanden na het eerste, op volgorde (BE-EP-057). */
export const ExtraBestanden: React.FC<{ content: FoundationContentDetail; beveiligd: boolean }> = ({ content, beveiligd }) => {
  const bestanden = content.bestanden ?? [];
  if (bestanden.length === 0) return null;
  return (
    <section aria-label="Meer foto's, opnames en documenten bij dit verhaal" className="mb-10">
      <h2 className="font-serif text-lg font-bold text-stone-900 mb-3">Meer bij dit verhaal</h2>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {bestanden.map((b) => (
          <ExtraBestand key={b.id} content={content} bestand={b} beveiligd={beveiligd} />
        ))}
      </ul>
    </section>
  );
};
