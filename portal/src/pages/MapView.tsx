import React, { useState, useCallback, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Search, MapPin, Filter, Layers, ChevronRight, Compass, List, Map as MapIcon } from 'lucide-react';
import { Map } from '../components/Map';
import { api } from '../api/client';
import type { FoundationContentListItem, GeoFeature } from '../types';

/**
 * De kaart toont alle openbare items met een locatie. Die komen uit de openbare lijst
 * (die al lat/lng bevat), niet uit het bbox-eindpunt: dat staat maximaal 2 graden toe
 * (anti-scrape) en kan Suriname, Curacao en Nederland dus nooit samen laten zien.
 */
const MAX_PAGINAS = 10;

export function naarFeatures(items: FoundationContentListItem[]): GeoFeature[] {
  return items
    .filter((i) => typeof i.lat === 'number' && typeof i.lng === 'number')
    .map((i) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [i.lng as number, i.lat as number] as [number, number] },
      properties: {
        id: i.id,
        title: i.title,
        summary: i.summary,
        content_type: String(i.content_type),
        file_url: i.file_url ?? null,
        location_name: i.location_name,
        category: i.category,
        created_at: i.created_at,
      },
    }));
}

export const MapView: React.FC = () => {
  const [features, setFeatures] = useState<GeoFeature[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('alles');
  const [loading, setLoading] = useState(false);
  const [activeFeature, setActiveFeature] = useState<GeoFeature | null>(null);
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map');

  const categories = [
    { id: 'alles', label: 'Alle Categorieen' },
    { id: 'verhalen', label: 'Verhalen' },
    { id: 'herdenking', label: 'Herdenking' },
    { id: 'educatie', label: 'Educatie' },
    { id: 'kunst', label: 'Kunst' },
    { id: 'archief', label: 'Archief' },
  ];

  const laadAlleLocaties = useCallback(async () => {
    setLoading(true);
    try {
      const alle: FoundationContentListItem[] = [];
      for (let pagina = 1; pagina <= MAX_PAGINAS; pagina++) {
        const res = await api.getContentList({ page: pagina, page_size: 100 });
        alle.push(...(res.items || []));
        if (!res.items || res.items.length < 100) break;
      }
      setFeatures(naarFeatures(alle));
    } catch (err) {
      console.error('Fout bij ophalen kaart data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    laadAlleLocaties();
  }, [laadAlleLocaties]);

  const filteredFeatures = features.filter((feat) => {
    const matchesSearch =
      searchQuery === '' ||
      feat.properties.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (feat.properties.location_name && feat.properties.location_name.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesCategory = selectedCategory === 'alles' || feat.properties.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="h-[calc(100vh-5rem)] flex flex-col bg-stone-100 overflow-hidden">
      {/* Top Filter Bar */}
      <div className="bg-white border-b border-stone-200 px-4 py-3 z-10 flex flex-wrap items-center justify-between gap-3 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-800 text-white flex items-center justify-center" aria-hidden="true">
            <Compass className="w-4 h-4" />
          </div>
          <div>
            <h1 className="font-serif font-bold text-stone-900 text-lg leading-tight">Interactieve Erfgoedkaart</h1>
            <p className="text-xs text-stone-600">Ontdek herinneringen en verhalen op geografische locatie</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 flex-grow max-w-2xl justify-end">
          {/* View Mode Toggle (WCAG 2.1 AA / WCAG 2.2 2.5.7 Equivalent Alternative) */}
          <div className="flex items-center rounded-xl bg-stone-100 p-1 border border-stone-200" role="group" aria-label="Kies weergaveoptie">
            <button
              type="button"
              onClick={() => setViewMode('map')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                viewMode === 'map'
                  ? 'bg-white text-stone-900 shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
              aria-pressed={viewMode === 'map'}
              aria-label="Schakel naar interactieve kaartweergave"
            >
              <MapIcon className="w-3.5 h-3.5 text-amber-800" aria-hidden="true" />
              <span>Kaart</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                viewMode === 'list'
                  ? 'bg-white text-stone-900 shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
              aria-pressed={viewMode === 'list'}
              aria-label="Schakel naar toegankelijke lijstweergave voor schermlezers en toetsenbord"
            >
              <List className="w-3.5 h-3.5 text-amber-800" aria-hidden="true" />
              <span>Toegankelijke Lijst</span>
            </button>
          </div>

          {/* Search box with accessible label */}
          <div className="relative flex-grow max-w-xs">
            <label htmlFor="map-search" className="sr-only">
              Zoek op titel of plaats
            </label>
            <Search className="w-4 h-4 text-stone-500 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
            <input
              id="map-search"
              type="text"
              placeholder="Zoek op titel of plaats..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-stone-50 border border-stone-200 rounded-xl focus:outline-none focus:border-amber-700 transition-colors"
            />
          </div>

          {/* Category Dropdown */}
          <div className="flex items-center gap-1.5 bg-stone-50 border border-stone-200 rounded-xl px-2.5 py-1.5">
            <Filter className="w-3.5 h-3.5 text-stone-600" aria-hidden="true" />
            <label htmlFor="map-category" className="sr-only">
              Filter op categorie
            </label>
            <select
              id="map-category"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="text-xs bg-transparent border-none focus:outline-none text-stone-800 font-medium"
            >
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.label}
                </option>
              ))}
            </select>
          </div>

          <div className="text-xs font-semibold text-stone-700 px-2" role="status" aria-live="polite">
            {loading ? 'Laden...' : `${filteredFeatures.length} locaties`}
          </div>
        </div>
      </div>

      {/* Main Workspace */}
      {viewMode === 'list' ? (
        /* Accessible List View (Full width, semantic, keyboard-navigable) */
        <section
          aria-label="Toegankelijke lijst van erfgoedlocaties"
          className="flex-grow overflow-y-auto p-4 sm:p-6 lg:p-8 bg-[#FDFBF7]"
        >
          <div className="max-w-4xl mx-auto">
            <div className="mb-6 pb-3 border-b border-stone-200 flex items-center justify-between">
              <h2 className="font-serif font-bold text-xl text-stone-900">
                Lijst van erfgoedlocaties ({filteredFeatures.length})
              </h2>
              <span className="text-xs text-stone-600">
                Toegankelijk alternatief conform WCAG 2.1 AA
              </span>
            </div>

            {filteredFeatures.length === 0 ? (
              <div className="p-12 text-center text-stone-600 bg-white rounded-2xl border border-stone-200">
                <MapPin className="w-10 h-10 text-stone-400 mx-auto mb-3" aria-hidden="true" />
                <p className="font-medium">Geen erfgoedlocaties gevonden die voldoen aan de zoekcriteria.</p>
              </div>
            ) : (
              <ul className="space-y-4" aria-label="Erfgoedlocaties overzicht">
                {filteredFeatures.map((feature) => (
                  <li
                    key={feature.properties.id}
                    className="bg-white rounded-2xl p-5 border border-stone-200 shadow-xs hover:border-amber-300 transition-all flex flex-col sm:flex-row gap-5 items-start sm:items-center justify-between"
                  >
                    <div className="flex gap-4 items-start">
                      {feature.properties.file_url ? (
                        <img
                          src={feature.properties.file_url}
                          alt={`Afbeelding bij ${feature.properties.title}`}
                          className="w-20 h-20 rounded-xl object-cover border border-stone-200 flex-shrink-0"
                        />
                      ) : (
                        <div className="w-20 h-20 rounded-xl bg-stone-100 border border-stone-200 flex items-center justify-center flex-shrink-0 text-stone-500">
                          <Layers className="w-8 h-8" aria-hidden="true" />
                        </div>
                      )}
                      <div>
                        {feature.properties.location_name && (
                          <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-800 mb-1">
                            <MapPin className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                            <span>{feature.properties.location_name}</span>
                          </div>
                        )}
                        <h3 className="font-serif font-bold text-stone-900 text-base mb-1">
                          {feature.properties.title}
                        </h3>
                        <p className="text-xs text-stone-600">
                          Geografische coördinaten:{' '}
                          <span className="font-mono">
                            {feature.geometry.coordinates[1].toFixed(4)}° N, {feature.geometry.coordinates[0].toFixed(4)}° O
                          </span>
                        </p>
                      </div>
                    </div>

                    <Link
                      to={`/item/${feature.properties.id}`}
                      className="inline-flex items-center gap-1.5 bg-amber-800 hover:bg-amber-700 text-white font-semibold text-xs px-4 py-2.5 rounded-xl transition-colors self-end sm:self-center shadow-xs"
                      aria-label={`Bekijk verhaal: ${feature.properties.title}`}
                    >
                      <span>Bekijk Verhaal</span>
                      <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      ) : (
        /* Interactive Map + Sidebar (Semantic section, no double main) */
        <div className="flex-grow flex flex-col md:flex-row overflow-hidden relative">
          {/* Left Sidebar List */}
          <aside
            aria-label="Zijbalk met locaties in dit kaartgebied"
            className="w-full md:w-80 lg:w-96 bg-white border-r border-stone-200 flex flex-col h-64 md:h-full z-10 shadow-sm"
          >
            <div className="p-3 border-b border-stone-100 bg-stone-50 flex items-center justify-between text-xs text-stone-700 font-semibold uppercase tracking-wider">
              <span>In dit gebied ({filteredFeatures.length})</span>
              {loading && <span className="animate-pulse text-amber-800">Bijwerken...</span>}
            </div>

            <ul className="flex-grow overflow-y-auto divide-y divide-stone-100 p-2 space-y-2" aria-label="Locaties in dit kaartgebied">
              {filteredFeatures.length === 0 ? (
                <li className="p-8 text-center text-stone-600 text-sm list-none">
                  <MapPin className="w-8 h-8 text-stone-400 mx-auto mb-2" aria-hidden="true" />
                  Geen herinneringen gevonden in dit gebied. Beweeg de kaart of pas je filters aan.
                </li>
              ) : (
                filteredFeatures.map((feature) => {
                  const isSelected = activeFeature?.properties.id === feature.properties.id;
                  return (
                    <li key={feature.properties.id} className="list-none">
                      <div
                        onClick={() => setActiveFeature(feature)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setActiveFeature(feature);
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-label={`Selecteer locatie: ${feature.properties.title}`}
                        className={`p-3 rounded-xl cursor-pointer transition-all border ${
                          isSelected
                            ? 'bg-amber-50 border-amber-300 shadow-xs'
                            : 'bg-white hover:bg-stone-50 border-transparent hover:border-stone-200'
                        }`}
                      >
                        <div className="flex gap-3">
                          {feature.properties.file_url ? (
                            <img
                              src={feature.properties.file_url}
                              alt={`Afbeelding bij ${feature.properties.title}`}
                              className="w-16 h-16 rounded-lg object-cover flex-shrink-0 border border-stone-200"
                            />
                          ) : (
                            <div className="w-16 h-16 rounded-lg bg-stone-100 border border-stone-200 flex items-center justify-center flex-shrink-0 text-stone-400">
                              <Layers className="w-6 h-6" aria-hidden="true" />
                            </div>
                          )}
                          <div className="flex-grow min-w-0">
                            {feature.properties.location_name && (
                              <div className="flex items-center gap-1 text-[11px] font-semibold text-amber-800 mb-0.5">
                                <MapPin className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
                                <span className="truncate">{feature.properties.location_name}</span>
                              </div>
                            )}
                            <h3 className="font-serif font-bold text-stone-900 text-sm leading-snug line-clamp-2 mb-1">
                              {feature.properties.title}
                            </h3>
                            <div className="flex items-center justify-between mt-2 pt-1">
                              <span className="text-[10px] text-stone-600">
                                {feature.geometry.coordinates[1].toFixed(3)}, {feature.geometry.coordinates[0].toFixed(3)}
                              </span>
                              <Link
                                to={`/item/${feature.properties.id}`}
                                className="inline-flex items-center gap-0.5 text-xs font-semibold text-amber-800 hover:text-amber-950"
                                aria-label={`Bekijk verhaal van ${feature.properties.title}`}
                              >
                                Bekijk
                                <ChevronRight className="w-3 h-3" aria-hidden="true" />
                              </Link>
                            </div>
                          </div>
                        </div>
                      </div>
                    </li>
                  );
                })
              )}
            </ul>
          </aside>

          {/* Map Container Section (Geen geneste main tag!) */}
          <section aria-label="Interactieve kaartweergave" className="flex-grow h-full relative">
            <Map features={filteredFeatures} fitToFeatures className="w-full h-full" />
          </section>
        </div>
      )}
    </div>
  );
};
