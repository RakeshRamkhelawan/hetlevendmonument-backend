import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, Compass, Home } from 'lucide-react';

export const NotFound: React.FC = () => {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/ontdekken?q=${encodeURIComponent(query.trim())}`);
    }
  };

  return (
    <div className="min-h-[70vh] flex items-center justify-center py-16 px-4 bg-[#FDFBF7]">
      <main className="max-w-xl w-full text-center space-y-8 bg-white p-8 sm:p-12 rounded-3xl border border-stone-200 shadow-sm" role="main">
        <div className="w-20 h-20 bg-amber-100 text-amber-900 rounded-full flex items-center justify-center mx-auto mb-2">
          <span className="font-serif text-3xl font-bold text-amber-900" aria-hidden="true">404</span>
        </div>

        <div className="space-y-3">
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-stone-900">
            Pagina niet gevonden
          </h1>
          <p className="text-stone-600 text-sm sm:text-base leading-relaxed">
            Het erfgoedstuk of de pagina die u zoekt bestaat niet (meer), is verplaatst of het adres is onjuist ingevoerd.
          </p>
        </div>

        <form onSubmit={handleSearch} className="relative max-w-md mx-auto" role="search" aria-label="Erfgoedcollectie doorzoeken">
          <label htmlFor="search-404" className="sr-only">
            Zoek in de erfgoedcollectie
          </label>
          <Search className="w-5 h-5 text-stone-400 absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
          <input
            id="search-404"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Zoek een verhaal, locatie of monument..."
            className="w-full pl-10 pr-28 py-3 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
          />
          <button
            type="submit"
            className="absolute right-1.5 top-1.5 bottom-1.5 px-4 bg-amber-800 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold transition-colors"
          >
            Zoeken
          </button>
        </form>

        <div className="pt-4 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            to="/"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-stone-100 hover:bg-stone-200 text-stone-800 font-semibold text-sm transition-colors"
          >
            <Home className="w-4 h-4" aria-hidden="true" />
            <span>Naar de Homepage</span>
          </Link>
          <Link
            to="/kaart"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm transition-colors"
          >
            <Compass className="w-4 h-4" aria-hidden="true" />
            <span>Open Erfgoedkaart</span>
          </Link>
        </div>
      </main>
    </div>
  );
};
