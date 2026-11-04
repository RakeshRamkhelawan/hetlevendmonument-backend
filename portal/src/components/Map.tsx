import React, { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { GeoFeature } from '../types';
import { buildPopupContent } from './map-popup';

if (typeof window !== 'undefined' && typeof maplibregl.setWorkerUrl === 'function') {
  maplibregl.setWorkerUrl(maplibreWorkerUrl);
}

interface MapProps {
  features: GeoFeature[];
  onBoundsChange?: (bounds: { minLng: number; minLat: number; maxLng: number; maxLat: number }) => void;
  className?: string;
  initialCenter?: [number, number];
  initialZoom?: number;
  /** Zet het beeld eenmalig zo dat alle punten zichtbaar zijn (bijv. Nederland, Suriname en Curacao). */
  fitToFeatures?: boolean;
}

export const Map: React.FC<MapProps> = ({
  features,
  onBoundsChange,
  className = 'w-full h-full min-h-[500px]',
  initialCenter = [5.2913, 52.1326], // Centrum van Nederland
  initialZoom = 7.5,
  fitToFeatures = false,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const hasFittedRef = useRef(false);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
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
        layers: [
          {
            id: 'osm-layer',
            type: 'raster',
            source: 'osm',
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: initialCenter,
      zoom: initialZoom,
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');

    const notifyBounds = () => {
      if (!onBoundsChange) return;
      const bounds = map.getBounds();
      onBoundsChange({
        minLng: bounds.getWest(),
        minLat: bounds.getSouth(),
        maxLng: bounds.getEast(),
        maxLat: bounds.getNorth(),
      });
    };

    map.on('load', () => {
      notifyBounds();
    });

    map.on('moveend', () => {
      notifyBounds();
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update markers when features change
  useEffect(() => {
    if (!mapRef.current) return;

    // Clear existing markers
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

    const map = mapRef.current;

    features.forEach((feature) => {
      const [lng, lat] = feature.geometry.coordinates;
      const { id, title, location_name, file_url } = feature.properties;

      // Custom accessible HTML marker element
      const el = document.createElement('div');
      el.className =
        'w-7 h-7 bg-amber-800 text-white rounded-full flex items-center justify-center border-2 border-white shadow-md cursor-pointer hover:scale-110 hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500 transition-all';
      el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'button');
      el.setAttribute('aria-label', `Erfgoedlocatie: ${title}${location_name ? ' in ' + location_name : ''}`);
      el.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>`;

      const popup = new maplibregl.Popup({ offset: 25, closeButton: false }).setDOMContent(
        buildPopupContent({ id, title, location_name, file_url }),
      );

      // Keyboard open popup on Enter or Space
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          popup.setLngLat([lng, lat]).addTo(map);
        }
      });

      const marker = new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).setPopup(popup).addTo(map);

      markersRef.current.push(marker);
    });

    if (fitToFeatures && !hasFittedRef.current && features.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      features.forEach((f) => bounds.extend(f.geometry.coordinates as [number, number]));
      map.fitBounds(bounds, { padding: 60, maxZoom: 7, duration: 0 });
      hasFittedRef.current = true;
    }
  }, [features, fitToFeatures]);

  return (
    <div
      role="region"
      aria-label="Interactieve geografische kaart met erfgoedlocaties"
      className={`relative rounded-2xl overflow-hidden border border-stone-200 shadow-inner ${className}`}
    >
      <div
        ref={mapContainerRef}
        tabIndex={0}
        role="application"
        aria-label="Kaartweergave. Gebruik pijltjestoetsen om te navigeren, plus en min om in te zoomen, of gebruik de toegankelijke lijstweergave hierboven."
        className="w-full h-full focus:outline-none focus:ring-2 focus:ring-amber-700"
      />
    </div>
  );
};
