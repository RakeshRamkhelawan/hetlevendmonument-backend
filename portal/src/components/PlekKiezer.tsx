import React, { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

if (typeof window !== 'undefined' && typeof maplibregl.setWorkerUrl === 'function') {
  maplibregl.setWorkerUrl(maplibreWorkerUrl);
}

export interface Plek {
  lat: number;
  lng: number;
}

interface PlekKiezerProps {
  plek: Plek | null;
  onKies: (plek: Plek | null) => void;
}

/** Nederland, Suriname en Curacao in een beeld (BE-EP-056). */
const BEGINBEELD: [[number, number], [number, number]] = [
  [-60, 3],
  [8, 54],
];

/** Afronden op 5 decimalen (ongeveer 1 meter): genoeg voor de kaart, niet meer dan nodig. */
const rond = (x: number) => Math.round(x * 1e5) / 1e5;

/**
 * Kaartje waarop een verteller de plek van het verhaal aanwijst (BE-EP-056).
 * Tikken of klikken zet een speld; de speld is te verslepen. Wie de plek niet
 * weet, laat de kaart leeg: het veld is optioneel.
 */
export const PlekKiezer: React.FC<PlekKiezerProps> = ({ plek, onKies }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const kaartRef = useRef<maplibregl.Map | null>(null);
  const speldRef = useRef<maplibregl.Marker | null>(null);
  const onKiesRef = useRef(onKies);
  onKiesRef.current = onKies;

  useEffect(() => {
    if (!containerRef.current) return;
    const kaart = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          },
        },
        layers: [{ id: 'osm-layer', type: 'raster', source: 'osm', minzoom: 0, maxzoom: 19 }],
      },
      bounds: BEGINBEELD,
      fitBoundsOptions: { padding: 20 },
    });
    kaart.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    kaart.on('click', (e) => onKiesRef.current({ lat: rond(e.lngLat.lat), lng: rond(e.lngLat.lng) }));
    kaartRef.current = kaart;
    return () => {
      kaart.remove();
      kaartRef.current = null;
      speldRef.current = null;
    };
  }, []);

  useEffect(() => {
    const kaart = kaartRef.current;
    if (!kaart) return;
    if (!plek) {
      speldRef.current?.remove();
      speldRef.current = null;
      return;
    }
    if (!speldRef.current) {
      const speld = new maplibregl.Marker({ color: '#92400e', draggable: true }).setLngLat([plek.lng, plek.lat]).addTo(kaart);
      speld.on('dragend', () => {
        const p = speld.getLngLat();
        onKiesRef.current({ lat: rond(p.lat), lng: rond(p.lng) });
      });
      speldRef.current = speld;
    } else {
      speldRef.current.setLngLat([plek.lng, plek.lat]);
    }
  }, [plek]);

  return (
    <div className="space-y-2">
      <div
        ref={containerRef}
        role="application"
        aria-label="Kaart om de plek van uw verhaal aan te wijzen. Tik of klik op de plek."
        className="w-full h-64 rounded-xl overflow-hidden border border-stone-200"
      />
      <div className="flex items-center justify-between text-xs text-stone-600">
        <span aria-live="polite">{plek ? 'Plek gekozen. U kunt de speld verslepen.' : 'Nog geen plek gekozen.'}</span>
        {plek && (
          <button type="button" onClick={() => onKies(null)} className="font-semibold text-amber-800 hover:underline">
            Plek wissen
          </button>
        )}
      </div>
    </div>
  );
};
