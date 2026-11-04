import React from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Calendar, User, EyeOff } from 'lucide-react';
import type { FoundationContentListItem } from '../types';

interface ContentCardProps {
  content: FoundationContentListItem;
}

export const ContentCard: React.FC<ContentCardProps> = ({ content }) => {
  const formattedDate = new Date(content.created_at).toLocaleDateString('nl-NL', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  return (
    <article className="group bg-white rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition-all duration-300 border border-stone-200 flex flex-col h-full">
      <Link to={`/item/${content.id}`} className="block relative overflow-hidden aspect-[16/10] bg-stone-100">
        <img
          src={content.file_url || '/hero-bg.jpg'}
          alt={content.title}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          loading="lazy"
        />
        {content.category && (
          <span className="absolute top-3 left-3 bg-white/90 backdrop-blur-sm px-2.5 py-1 rounded-full text-xs font-semibold text-stone-800 shadow-sm uppercase tracking-wider">
            {content.category}
          </span>
        )}
      </Link>

      <div className="p-5 flex flex-col flex-grow">
        <div className="flex items-center gap-3 text-xs text-stone-500 mb-2.5">
          <span className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5" />
            {formattedDate}
          </span>
          {content.location_name && (
            <span className="flex items-center gap-1 truncate max-w-[150px]" title={content.location_name}>
              <MapPin className="w-3.5 h-3.5 flex-shrink-0" />
              {content.location_name}
            </span>
          )}
        </div>

        <h3 className="text-lg font-serif font-bold text-stone-900 group-hover:text-amber-800 transition-colors line-clamp-2 mb-2">
          <Link to={`/item/${content.id}`}>{content.title}</Link>
        </h3>

        <p className="text-sm text-stone-600 line-clamp-3 mb-4 flex-grow">
          {content.summary || 'Geen samenvatting beschikbaar.'}
        </p>

        <div className="pt-4 border-t border-stone-100 flex items-center justify-between text-xs text-stone-500">
          <span className="flex items-center gap-1.5 font-medium">
            {content.is_anonymous ? (
              <>
                <EyeOff className="w-3.5 h-3.5 text-stone-400" />
                <span className="italic text-stone-400">Anonieme inzending</span>
              </>
            ) : (
              <>
                <User className="w-3.5 h-3.5 text-stone-500" />
                <span>{content.creator_name || 'Onbekende verteller'}</span>
              </>
            )}
          </span>
          <span className="text-amber-800 font-semibold group-hover:underline">Lees verhaal &rarr;</span>
        </div>
      </div>
    </article>
  );
};
