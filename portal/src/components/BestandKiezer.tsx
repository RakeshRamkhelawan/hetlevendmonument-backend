import React, { useEffect, useId, useState } from 'react';
import { Camera, FileText, Film, Music, Paperclip, Trash2 } from 'lucide-react';

/** Gelijk aan de bovengrens van de backend (settings.max_upload_size_bytes). */
export const MAX_BESTAND_BYTES = 50 * 1024 * 1024;

/** Gelijk aan MAX_BESTANDEN_PER_VERHAAL in de backend (BE-EP-057). */
export const MAX_BESTANDEN = 10;

/** Wat de backend accepteert (foundation_storage.ALLOWED_MIME_TYPES), plus de namen die browsers voor .m4a gebruiken. */
const TOEGESTAAN = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
  'audio/mpeg',
  'audio/mp3',
  'audio/wav',
  'audio/x-wav',
  'audio/ogg',
  'audio/mp4',
  'audio/x-m4a',
  'audio/m4a',
  'video/mp4',
  'video/webm',
  'video/quicktime',
  'application/pdf',
]);

const ACCEPT = 'image/*,audio/*,video/mp4,video/webm,video/quicktime,application/pdf';

/** Controleer een gekozen bestand; geeft een foutmelding in gewone taal, of null als het goed is. */
export const controleerBestand = (bestand: File): string | null => {
  if (bestand.size === 0) return 'Dit bestand is leeg. Kies een ander bestand.';
  if (bestand.size > MAX_BESTAND_BYTES) return 'Dit bestand is groter dan 50 MB. Kies een kleiner bestand.';
  const soort = (bestand.type || '').toLowerCase();
  if (soort === 'image/heic' || soort === 'image/heif' || /\.hei[cf]$/i.test(bestand.name)) {
    return 'Dit fotoformaat (HEIC) kunnen we nog niet verwerken. Kies de foto via uw telefoon, of sla hem op als JPG.';
  }
  if (!TOEGESTAAN.has(soort)) return 'Dit soort bestand kunnen we niet opslaan. Kies een foto, geluidsopname, video of PDF.';
  return null;
};

const grootte = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB` : `${Math.max(1, Math.round(bytes / 1024))} kB`;

/** Een gekozen bestand in de lijst, met voorbeeld voor foto en geluid. */
const GekozenBestand: React.FC<{ bestand: File; onVerwijder: () => void }> = ({ bestand, onVerwijder }) => {
  const [voorbeeld, setVoorbeeld] = useState<string | null>(null);

  useEffect(() => {
    if (typeof URL.createObjectURL !== 'function') return;
    const url = URL.createObjectURL(bestand);
    setVoorbeeld(url);
    return () => URL.revokeObjectURL(url);
  }, [bestand]);

  return (
    <li className="flex items-center gap-4 p-3 rounded-xl border border-stone-200 bg-stone-50">
      {bestand.type.startsWith('image/') && voorbeeld ? (
        <img src={voorbeeld} alt={`Voorbeeld van ${bestand.name}`} className="w-16 h-16 object-cover rounded-lg" />
      ) : bestand.type.startsWith('audio/') ? (
        <Music className="w-8 h-8 text-amber-800 flex-shrink-0" aria-hidden="true" />
      ) : bestand.type.startsWith('video/') ? (
        <Film className="w-8 h-8 text-amber-800 flex-shrink-0" aria-hidden="true" />
      ) : (
        <FileText className="w-8 h-8 text-amber-800 flex-shrink-0" aria-hidden="true" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-stone-900 truncate">{bestand.name}</p>
        <p className="text-xs text-stone-600">{grootte(bestand.size)}</p>
        {bestand.type.startsWith('audio/') && voorbeeld && (
          <audio controls src={voorbeeld} className="mt-2 w-full" aria-label={`${bestand.name} beluisteren`} />
        )}
      </div>
      <button
        type="button"
        onClick={onVerwijder}
        aria-label={`${bestand.name} verwijderen`}
        className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 hover:underline"
      >
        <Trash2 className="w-4 h-4" aria-hidden="true" />
        Verwijderen
      </button>
    </li>
  );
};

interface BestandKiezerProps {
  bestanden: File[];
  onWijzig: (bestanden: File[]) => void;
}

/**
 * Foto's, geluidsopnames, video's of PDF's kiezen vanaf het eigen apparaat (BE-EP-056),
 * tot MAX_BESTANDEN per verhaal (BE-EP-057). Op een telefoon biedt "Bestanden kiezen"
 * ook de camera en de recorder aan; "Foto maken" opent direct de camera.
 */
export const BestandKiezer: React.FC<BestandKiezerProps> = ({ bestanden, onWijzig }) => {
  const id = useId();
  const [fouten, setFouten] = useState<string[]>([]);
  const ruimte = MAX_BESTANDEN - bestanden.length;

  const kies = (e: React.ChangeEvent<HTMLInputElement>) => {
    const gekozen = Array.from(e.target.files ?? []);
    e.target.value = '';
    if (gekozen.length === 0) return;
    const goed: File[] = [];
    const meldingen: string[] = [];
    for (const bestand of gekozen) {
      const melding = controleerBestand(bestand);
      if (melding) meldingen.push(`${bestand.name}: ${melding}`);
      else goed.push(bestand);
    }
    if (goed.length > ruimte) {
      meldingen.push(`U kunt maximaal ${MAX_BESTANDEN} bestanden bij een verhaal zetten. De laatste ${goed.length - ruimte} zijn niet toegevoegd.`);
    }
    setFouten(meldingen);
    onWijzig([...bestanden, ...goed.slice(0, Math.max(0, ruimte))]);
  };

  const knop =
    'inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-stone-300 bg-white text-stone-800 text-sm font-semibold hover:bg-stone-50 cursor-pointer focus-within:ring-2 focus-within:ring-amber-700';

  return (
    <div className="space-y-3">
      {bestanden.length > 0 && (
        <ul className="space-y-2" aria-label="Gekozen bestanden">
          {bestanden.map((b, i) => (
            <GekozenBestand key={`${b.name}-${b.size}-${i}`} bestand={b} onVerwijder={() => onWijzig(bestanden.filter((_, j) => j !== i))} />
          ))}
        </ul>
      )}

      {ruimte > 0 && (
        <div className="flex flex-wrap gap-3">
          <label htmlFor={`${id}-bestand`} className={knop}>
            <Paperclip className="w-4 h-4" aria-hidden="true" />
            {bestanden.length === 0 ? 'Foto, geluid of document kiezen' : 'Nog een bestand toevoegen'}
            <input id={`${id}-bestand`} type="file" accept={ACCEPT} multiple onChange={kies} className="sr-only" />
          </label>
          <label htmlFor={`${id}-camera`} className={knop}>
            <Camera className="w-4 h-4" aria-hidden="true" />
            Foto maken
            <input id={`${id}-camera`} type="file" accept="image/*" capture="environment" onChange={kies} className="sr-only" />
          </label>
        </div>
      )}

      {fouten.length > 0 && (
        <div role="alert" className="text-sm text-red-700 space-y-1">
          {fouten.map((f) => (
            <p key={f}>{f}</p>
          ))}
        </div>
      )}
      <p className="text-xs text-stone-600">
        Tot {MAX_BESTANDEN} bestanden: foto (JPG, PNG), geluid (MP3, M4A, WAV), video (MP4, MOV) of PDF, elk tot 50 MB.
        Locatiegegevens in foto's, video's en opnames halen wij er automatisch uit.
      </p>
    </div>
  );
};
