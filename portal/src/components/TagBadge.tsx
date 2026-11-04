import React from 'react';
import type { TagType, ContentTagDetail } from '../types';

interface TagBadgeProps {
  tag: string | ContentTagDetail;
  type?: TagType | string;
  confidence?: number;
  className?: string;
}

export const TagBadge: React.FC<TagBadgeProps> = ({ tag, type, confidence, className = '' }) => {
  const label = typeof tag === 'string' ? tag : tag.tag;
  const tagType = type || (typeof tag === 'object' ? tag.tag_type : 'THEME');
  const tagConfidence = confidence !== undefined ? confidence : (typeof tag === 'object' ? tag.confidence : undefined);

  const getBadgeStyle = (t: string) => {
    switch (t.toUpperCase()) {
      case 'THEME':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'LOCATION':
        return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      case 'PERIOD':
        return 'bg-indigo-100 text-indigo-800 border-indigo-200';
      case 'SENTIMENT':
        return 'bg-rose-100 text-rose-800 border-rose-200';
      case 'LANGUAGE':
        return 'bg-sky-100 text-sky-800 border-sky-200';
      default:
        return 'bg-stone-100 text-stone-700 border-stone-200';
    }
  };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getBadgeStyle(
        tagType
      )} ${className}`}
      title={tagConfidence !== undefined ? `Betrouwbaarheid: ${Math.round(tagConfidence * 100)}%` : undefined}
    >
      #{label}
    </span>
  );
};
