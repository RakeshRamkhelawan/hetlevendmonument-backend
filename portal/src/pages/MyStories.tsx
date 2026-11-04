import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Clock, CheckCircle2, AlertCircle, PlusCircle, Calendar, MapPin, ArrowRight } from 'lucide-react';
import { api, FoundationContentListItem } from '../api/client';

export const MyStories: React.FC = () => {
  const [items, setItems] = useState<FoundationContentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSubmissions = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.getMySubmissions();
        setItems(res.items);
        setTotal(res.total);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Er is een fout opgetreden bij het ophalen van uw inzendingen.');
      } finally {
        setLoading(false);
      }
    };
    fetchSubmissions();
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Goedgekeurd &amp; Gepubliceerd</span>
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-200">
            <AlertCircle className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Niet opgenomen</span>
          </span>
        );
      case 'pending':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
            <Clock className="w-3.5 h-3.5" aria-hidden="true" />
            <span>In behandeling bij de redactie</span>
          </span>
        );
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 sm:py-14">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-8 border-b border-stone-200">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-800 mb-1.5">
            <BookOpen className="w-4 h-4" aria-hidden="true" />
            <span>Persoonlijk Archief</span>
          </div>
          <h1 className="font-serif text-3xl font-bold text-stone-900">Mijn Inzendingen</h1>
          <p className="text-stone-600 text-sm mt-1">
            Overzicht van uw ingezonden verhalen, documenten en herinneringen voor Het Levend Monument.
          </p>
        </div>

        <Link
          to="/uploaden"
          className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm transition-colors shadow-sm self-start sm:self-auto"
        >
          <PlusCircle className="w-4 h-4" aria-hidden="true" />
          <span>Nieuw Verhaal Inzenden</span>
        </Link>
      </div>

      <div className="mt-8">
        {loading ? (
          <div className="py-16 text-center text-stone-500 space-y-3">
            <div className="w-8 h-8 border-2 border-amber-700 border-t-transparent rounded-full animate-spin mx-auto" aria-hidden="true" />
            <p className="text-sm">Uw inzendingen worden geladen...</p>
          </div>
        ) : error ? (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-sm flex items-start gap-3">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-rose-700" aria-hidden="true" />
            <div>
              <p className="font-semibold">Fout bij laden van inzendingen</p>
              <p className="text-xs text-rose-700 mt-0.5">{error}</p>
            </div>
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-16 px-4 bg-white rounded-3xl border border-dashed border-stone-300 space-y-4">
            <div className="w-14 h-14 bg-stone-100 rounded-full flex items-center justify-center mx-auto text-stone-400">
              <BookOpen className="w-7 h-7" aria-hidden="true" />
            </div>
            <div className="space-y-1">
              <h2 className="font-serif text-xl font-bold text-stone-800">Nog geen inzendingen</h2>
              <p className="text-stone-500 text-sm max-w-md mx-auto">
                U heeft nog geen erfgoedverhalen of foto's gedeeld. Help mee ons levende monument te verrijken met uw herinneringen.
              </p>
            </div>
            <Link
              to="/uploaden"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm transition-colors"
            >
              <PlusCircle className="w-4 h-4" aria-hidden="true" />
              <span>Deel uw eerste verhaal</span>
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-xs text-stone-500">Totaal {total} inzending{total === 1 ? '' : 'en'}</p>
            <div className="grid gap-4">
              {items.map((item) => (
                <article
                  key={item.id}
                  className="p-5 bg-white rounded-2xl border border-stone-200 hover:border-amber-300 transition-colors shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                >
                  <div className="space-y-2">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <h2 className="font-serif font-bold text-lg text-stone-900">
                        {item.title}
                      </h2>
                      {getStatusBadge(item.status)}
                    </div>

                    <div className="flex items-center gap-4 text-xs text-stone-500 flex-wrap">
                      {item.category && (
                        <span className="capitalize px-2 py-0.5 rounded bg-stone-100 text-stone-700">
                          {item.category}
                        </span>
                      )}
                      {item.location_name && (
                        <span className="flex items-center gap-1">
                          <MapPin className="w-3.5 h-3.5 text-stone-400" aria-hidden="true" />
                          <span>{item.location_name}</span>
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5 text-stone-400" aria-hidden="true" />
                        <span>{new Date(item.created_at).toLocaleDateString('nl-NL', { year: 'numeric', month: 'long', day: 'numeric' })}</span>
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-end sm:self-center">
                    {item.status === 'approved' ? (
                      <Link
                        to={`/verhaal/${item.id}`}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-stone-100 hover:bg-stone-200 text-stone-800 text-xs font-semibold transition-colors"
                      >
                        <span>Bekijk op platform</span>
                        <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
                      </Link>
                    ) : (
                      <span className="text-xs text-stone-400 italic">
                        {item.status === 'pending' ? 'Wordt beoordeeld' : 'Niet zichtbaar'}
                      </span>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
