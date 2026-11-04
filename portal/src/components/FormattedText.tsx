import React from 'react';

/**
 * Toont platte tekst met een paar eenvoudige opmaakregels, zonder HTML te injecteren:
 * - een regel die begint met "## " wordt een kop;
 * - regels die beginnen met "- " worden een opsomming;
 * - regels die beginnen met "1. ", "2. " ... worden een genummerde lijst;
 * - een lege regel scheidt alinea's;
 * - https-adressen worden klikbare links.
 * Tekst zonder deze tekens (zoals de verhalen) ziet er hetzelfde uit als voorheen.
 */

const URL_RE = /(https:\/\/[^\s)]+)/g;

function metLinks(tekst: string, sleutel: string): React.ReactNode[] {
  return tekst.split(URL_RE).map((deel, i) => {
    if (/^https:\/\//.test(deel)) {
      const schoon = deel.replace(/[.,;:]+$/, '');
      const rest = deel.slice(schoon.length);
      return (
        <React.Fragment key={`${sleutel}-${i}`}>
          <a href={schoon} target="_blank" rel="noopener noreferrer" className="text-amber-800 underline break-all">
            {schoon}
          </a>
          {rest}
        </React.Fragment>
      );
    }
    return <React.Fragment key={`${sleutel}-${i}`}>{deel}</React.Fragment>;
  });
}

type Blok =
  | { soort: 'kop'; tekst: string }
  | { soort: 'lijst'; regels: string[] }
  | { soort: 'nummers'; regels: string[] }
  | { soort: 'alinea'; regels: string[] };

export function deelOp(tekst: string): Blok[] {
  const blokken: Blok[] = [];
  for (const regel of tekst.replace(/\r\n/g, '\n').split('\n')) {
    const laatste = blokken[blokken.length - 1];
    if (regel.trim() === '') {
      blokken.push({ soort: 'alinea', regels: [] });
      continue;
    }
    if (regel.startsWith('## ')) {
      blokken.push({ soort: 'kop', tekst: regel.slice(3).trim() });
      continue;
    }
    const punt = /^- (.*)$/.exec(regel);
    if (punt) {
      if (laatste && laatste.soort === 'lijst') laatste.regels.push(punt[1]);
      else blokken.push({ soort: 'lijst', regels: [punt[1]] });
      continue;
    }
    const nummer = /^\d+\. (.*)$/.exec(regel);
    if (nummer) {
      if (laatste && laatste.soort === 'nummers') laatste.regels.push(nummer[1]);
      else blokken.push({ soort: 'nummers', regels: [nummer[1]] });
      continue;
    }
    if (laatste && laatste.soort === 'alinea') laatste.regels.push(regel);
    else blokken.push({ soort: 'alinea', regels: [regel] });
  }
  return blokken.filter((b) => b.soort !== 'alinea' || b.regels.length > 0);
}

export const FormattedText: React.FC<{ text: string }> = ({ text }) => (
  <div className="space-y-4 text-stone-800 leading-relaxed text-base">
    {deelOp(text).map((blok, i) => {
      const k = `b${i}`;
      if (blok.soort === 'kop') {
        return (
          <h3 key={k} className="font-serif text-lg font-bold text-stone-900 pt-2">
            {blok.tekst}
          </h3>
        );
      }
      if (blok.soort === 'lijst') {
        return (
          <ul key={k} className="list-disc pl-6 space-y-1.5">
            {blok.regels.map((r, j) => (
              <li key={j}>{metLinks(r, `${k}-${j}`)}</li>
            ))}
          </ul>
        );
      }
      if (blok.soort === 'nummers') {
        return (
          <ol key={k} className="list-decimal pl-6 space-y-1.5">
            {blok.regels.map((r, j) => (
              <li key={j}>{metLinks(r, `${k}-${j}`)}</li>
            ))}
          </ol>
        );
      }
      return (
        <p key={k} className="whitespace-pre-line">
          {metLinks(blok.regels.join('\n'), k)}
        </p>
      );
    })}
  </div>
);
