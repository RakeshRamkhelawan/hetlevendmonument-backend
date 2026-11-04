import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Compass, MapPin, Sparkles, ArrowRight, BookOpen, Layers } from 'lucide-react';
import { api } from '../api/client';
import { ContentCard } from '../components/ContentCard';
import type { FoundationContentListItem } from '../types';

export const Home: React.FC = () => {
  const [items, setItems] = useState<FoundationContentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState<string>('alles');

  const categories = [
    { id: 'alles', label: 'Alles' },
    { id: 'verhalen', label: 'Verhalen' },
    { id: 'herdenking', label: 'Herdenking' },
    { id: 'educatie', label: 'Educatie' },
    { id: 'kunst', label: 'Kunst' },
    { id: 'archief', label: 'Archief' },
  ];

  useEffect(() => {
    const fetchContent = async () => {
      setLoading(true);
      try {
        const res = await api.getContentList({
          page: 1,
          page_size: 12,
          category: selectedCategory !== 'alles' ? selectedCategory : undefined,
        });
        setItems(res.items || []);
      } catch (err) {
        console.error('Fout bij laden van content:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchContent();
  }, [selectedCategory]);

  return (
    <div>
      {/* Hero Banner */}
      <section className="relative overflow-hidden bg-stone-900 text-white min-h-[560px] flex items-center">
        <div className="absolute inset-0 z-0">
          <img
            src="/hero-bg.jpg"
            alt="Levend Monument Historie"
            className="w-full h-full object-cover opacity-35 filter saturate-150"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-stone-950 via-stone-900/60 to-transparent" />
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <div className="max-w-3xl">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-800/80 backdrop-blur-sm text-xs font-semibold uppercase tracking-wider text-amber-200 mb-6">
              <Sparkles className="w-3.5 h-3.5" />
              Cultureel Erfgoed Portaal
            </span>
            <h1 className="font-serif text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-white leading-tight mb-6">
              Verhalen die geschiedenis levend houden.
            </h1>
            <p className="text-lg sm:text-xl text-stone-300 leading-relaxed mb-8">
              Ontdek getuigenissen, foto's en herinneringen uit onze gemeenschap. Deel jouw verhaal en draag bij aan het
              blijvende Levend Monument.
            </p>

            <div className="flex flex-wrap gap-4">
              <Link
                to="/uploaden"
                className="bg-amber-800 hover:bg-amber-700 text-white font-semibold px-6 py-3.5 rounded-xl shadow-lg transition-all flex items-center gap-2"
              >
                Deel je Verhaal
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                to="/kaart"
                className="bg-white/10 hover:bg-white/20 text-white backdrop-blur-sm font-semibold px-6 py-3.5 rounded-xl border border-white/20 transition-all flex items-center gap-2"
              >
                <MapPin className="w-4 h-4 text-amber-400" />
                Bekijk op de Kaart
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Highlights */}
      <section className="py-12 bg-white border-b border-stone-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="flex gap-4 items-start p-4 rounded-xl">
            <div className="w-12 h-12 rounded-xl bg-amber-100 text-amber-900 flex items-center justify-center flex-shrink-0">
              <Compass className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-serif font-bold text-lg text-stone-900 mb-1">Open Erfgoed</h3>
              <p className="text-sm text-stone-600 leading-relaxed">
                Vrij toegankelijk en doorzoekbaar digitaal erfgoed conform de richtlijnen van Netwerk Digitaal Erfgoed (NDE).
              </p>
            </div>
          </div>

          <div className="flex gap-4 items-start p-4 rounded-xl">
            <div className="w-12 h-12 rounded-xl bg-emerald-100 text-emerald-900 flex items-center justify-center flex-shrink-0">
              <BookOpen className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-serif font-bold text-lg text-stone-900 mb-1">Educatieve Leeromgeving</h3>
              <p className="text-sm text-stone-600 leading-relaxed">
                Speciale lesmodules en studiezalen voor scholen en docenten met beschermde toegangscodes.
              </p>
            </div>
          </div>

          <div className="flex gap-4 items-start p-4 rounded-xl">
            <div className="w-12 h-12 rounded-xl bg-indigo-100 text-indigo-900 flex items-center justify-center flex-shrink-0">
              <Layers className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-serif font-bold text-lg text-stone-900 mb-1">AI Verrijking &amp; OAI-PMH</h3>
              <p className="text-sm text-stone-600 leading-relaxed">
                Automatische semantische tagging en een OAI-PMH v2.0 endpoint voor erfgoedaggregators zoals Europeana.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Content Feed Section */}
      <section className="py-16 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-10 gap-4">
          <div>
            <span className="text-amber-800 font-semibold text-xs tracking-wider uppercase">Verhalen &amp; Herinneringen</span>
            <h2 className="font-serif text-3xl font-bold text-stone-900 mt-1">Ontdek de Collectie</h2>
          </div>

          {/* Category Filter Chips */}
          <div className="flex flex-wrap gap-2">
            {categories.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                  selectedCategory === cat.id
                    ? 'bg-amber-800 text-white shadow-sm'
                    : 'bg-white text-stone-600 border border-stone-200 hover:border-stone-400'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>

        {/* Content Grid */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-white rounded-2xl p-4 border border-stone-200 animate-pulse h-80">
                <div className="bg-stone-200 h-44 rounded-xl mb-4" />
                <div className="h-4 bg-stone-200 rounded w-3/4 mb-2" />
                <div className="h-4 bg-stone-200 rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : items.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {items.map((item) => (
              <ContentCard key={item.id} content={item} />
            ))}
          </div>
        ) : (
          <div className="text-center py-20 bg-white rounded-3xl border border-stone-200 p-8">
            <Compass className="w-12 h-12 text-stone-300 mx-auto mb-3" />
            <h3 className="font-serif font-bold text-lg text-stone-800 mb-1">Geen verhalen gevonden</h3>
            <p className="text-sm text-stone-500 mb-6">Er zijn nog geen goedgekeurde verhalen in deze categorie.</p>
            <Link
              to="/uploaden"
              className="inline-flex items-center gap-2 bg-amber-800 text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-amber-700"
            >
              Wees de eerste en deel een verhaal
            </Link>
          </div>
        )}
      </section>
    </div>
  );
};
