import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  GraduationCap,
  KeyRound,
  CheckCircle,
  AlertCircle,
  Clock,
  ArrowRight,
  FileText,
  Video,
} from 'lucide-react';
import { api } from '../api/client';
import type { FoundationContentListItem, EduSessionContext } from '../types';

/**
 * De API (GET /edu/session) geeft {role, expires_at} terug, zonder is_active. Een
 * antwoord met een rol betekent: er is een geldige sessie. is_active blijft gelden als
 * het veld er wel is.
 */
const sessieActief = (s: Partial<EduSessionContext> | null | undefined): boolean =>
  !!s && (typeof s.is_active === 'boolean' ? s.is_active : Boolean(s.role));

export const EduPortal: React.FC = () => {
  const [eduCode, setEduCode] = useState('');
  const [session, setSession] = useState<EduSessionContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [eduItems, setEduItems] = useState<FoundationContentListItem[]>([]);
  const [handleidingen, setHandleidingen] = useState<FoundationContentListItem[]>([]);

  const fetchEdu = async () => {
    try {
      const res = await api.getEduContent();
      setEduItems(res.items || []);
    } catch {
      // Zonder klassessie geeft de API 401; dan zijn er (nog) geen werkbladen te tonen.
      setEduItems([]);
    }
  };

  useEffect(() => {
    // Check if an edu session already exists
    const checkSession = async () => {
      try {
        const sess = await api.getEduSession();
        if (sessieActief(sess)) {
          setSession(sess);
        }
      } catch {
        // No active session, that's fine
      }
    };
    checkSession();

    fetchEdu();

    // De docentenhandleidingen zijn openbaar (categorie educatie).
    const fetchHandleidingen = async () => {
      try {
        const res = await api.getContentList({ category: 'educatie', page_size: 50 });
        setHandleidingen((res.items || []).filter((i) => i.content_type === 'teacher_guide'));
      } catch {
        setHandleidingen([]);
      }
    };
    fetchHandleidingen();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanCode = eduCode.replace(/[\s-]/g, '').toUpperCase();
    if (!cleanCode) return;

    setLoading(true);
    setError(null);

    try {
      const res = await api.validateEduAccess(cleanCode);
      if (res.status === 'valid') {
        const sess = await api.getEduSession();
        setSession(sess);
        setEduCode(cleanCode);
        await fetchEdu();
      } else {
        setError('Ongeldige toegangscode. Controleer de 8-tekens klascode met uw docent.');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.includes('429')) {
        setError('Te veel pogingen. Wacht een minuut voordat u het opnieuw probeert.');
      } else if (
        msg.includes('401') ||
        msg.includes('404') ||
        msg.includes('not found') ||
        msg.includes('ongeldig') ||
        msg.includes('Invalid') ||
        msg.includes('expired') ||
        msg.includes('verlopen')
      ) {
        setError('De ingevoerde toegangscode is ongeldig of verlopen. Controleer de 8-tekens code met uw docent.');
      } else {
        setError('Verificatie mislukt. Probeer het later opnieuw.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleStartModule = (themeTitle: string) => {
    if (!sessieActief(session)) {
      const codeBox = document.getElementById('edu-code-box');
      if (codeBox) {
        codeBox.scrollIntoView({ behavior: 'smooth' });
        const input = document.getElementById('edu-code-input');
        if (input) (input as HTMLInputElement).focus();
      }
      setError(`Voer eerst uw 8-tekens klascode in om '${themeTitle}' te openen.`);
    } else {
      const materials = document.getElementById('edu-materials');
      if (materials) {
        materials.scrollIntoView({ behavior: 'smooth' });
      }
    }
  };

  const educationalThemes = [
    {
      niveau: 'groep-7-8',
      title: 'Vijf verhalen over vrijheid',
      target: 'Groep 7-8',
      duration: '5 lessen van 45 minuten',
      description:
        'Van Schiedam in 1602 tot Vlaardingen in 1975. Leerlingen lezen vijf korte verhalen en ontdekken met eenvoudige werkbladen wat er echt gebeurde.',
      modules: 5,
    },
    {
      niveau: 'onderbouw-vo',
      title: 'Vijf verhalen over vrijheid',
      target: 'Onderbouw VO',
      duration: '5 lessen van 50 minuten',
      description:
        'Dezelfde vijf verhalen, met bronnenwerk: feit en fictie, perspectief, oorzaak en gevolg, en hoe het slavernijverleden doorwerkt in het heden.',
      modules: 5,
    },
  ];

  const handleidingVoor = (niveau: string) => handleidingen.find((h) => h.target_age_group === niveau);
  const niveauNaam: Record<string, string> = { 'groep-7-8': 'Groep 7-8', 'onderbouw-vo': 'Onderbouw VO' };
  const werkbladenPerNiveau = ['groep-7-8', 'onderbouw-vo']
    .map((n) => ({
      niveau: n,
      items: eduItems.filter((i) => i.target_age_group === n).sort((a, b) => a.title.localeCompare(b.title, 'nl')),
    }))
    .filter((g) => g.items.length > 0);
  const overigeWerkbladen = eduItems.filter((i) => !i.target_age_group || !niveauNaam[i.target_age_group]);

  return (
    <div className="min-h-screen bg-[#FDFBF7] py-12">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Banner */}
        <div className="bg-stone-900 rounded-3xl p-8 sm:p-12 text-white relative overflow-hidden mb-12 shadow-sm">
          <div className="relative z-10 max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-800 text-amber-200 text-xs font-semibold uppercase tracking-wider mb-4">
              <GraduationCap className="w-4 h-4" />
              Educatief Portaal
            </div>
            <h1 className="font-serif text-3xl sm:text-4xl font-bold leading-tight mb-4">
              Levende Geschiedenis in het Onderwijs
            </h1>
            <p className="text-stone-300 text-sm leading-relaxed mb-6">
              Lesmateriaal over het slavernijverleden: vijf korte verhalen, werkbladen en gecontroleerde bronnen. Voor
              groep 7-8 en de onderbouw van het voortgezet onderwijs.
            </p>
            <div className="flex flex-wrap gap-4 text-xs font-medium text-stone-300">
              <span className="flex items-center gap-1.5">
                <CheckCircle className="w-4 h-4 text-amber-400" />
                Sluit aan op de SLO-conceptkerndoelen
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle className="w-4 h-4 text-amber-400" />
                Met vensters uit de Canon van Nederland
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle className="w-4 h-4 text-amber-400" />
                Veilig &amp; AVG-conform
              </span>
            </div>
          </div>
        </div>

        {/* Access Code Box */}
        <div id="edu-code-box" className="bg-white rounded-2xl p-6 sm:p-8 border border-stone-200 shadow-xs mb-12">
          {sessieActief(session) ? (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 bg-emerald-50 border border-emerald-200 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-emerald-700 text-white flex items-center justify-center flex-shrink-0">
                  <CheckCircle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-serif font-bold text-emerald-950 text-base">Klassikale Sessie Geactiveerd</h3>
                  <p className="text-xs text-emerald-800">
                    Toegang verleend voor {session?.role === 'teacher' ? 'Docent' : 'Leerling'}. Sessie blijft 4 uur geldig.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs font-semibold text-emerald-900 bg-white px-3 py-1.5 rounded-lg border border-emerald-200">
                <Clock className="w-4 h-4 text-emerald-700" />
                Actieve sessie
              </div>
            </div>
          ) : (
            <div className="max-w-xl mx-auto text-center">
              <div className="w-12 h-12 bg-amber-100 text-amber-900 rounded-full flex items-center justify-center mx-auto mb-3">
                <KeyRound className="w-6 h-6" />
              </div>
              <h2 className="font-serif text-xl font-bold text-stone-900 mb-1">Leerling Toegangscode</h2>
              <p className="text-stone-500 text-xs mb-6">
                Heb je een 8-tekens klascode gekregen van je docent? Voer hem hieronder in voor toegang tot de lesmodules.
              </p>

              <form onSubmit={handleVerifyCode} className="flex gap-2 max-w-sm mx-auto">
                <input
                  id="edu-code-input"
                  type="text"
                  required
                  placeholder="Bijv. 4MAH8XYD"
                  value={eduCode}
                  onChange={(e) => setEduCode(e.target.value)}
                  className="flex-grow uppercase font-mono tracking-widest text-center px-4 py-2.5 rounded-xl border border-stone-300 focus:outline-none focus:border-amber-700 text-sm font-semibold"
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="bg-amber-800 hover:bg-amber-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
                >
                  {loading ? 'Controleren...' : 'Inloggen'}
                </button>
              </form>

              {error && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="mt-6 pt-6 border-t border-stone-100 text-xs text-stone-500 flex items-center justify-center gap-2">
                <span>Bent u docent en wilt u een lescode aanmaken?</span>
                <Link to="/docenten" className="text-amber-800 font-semibold hover:underline">
                  Ga naar Docenten Portaal &rarr;
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* Curated Educational Themes */}
        <section className="mb-14">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="font-serif text-2xl font-bold text-stone-900">Onderwijsthema&apos;s &amp; Modules</h2>
              <p className="text-stone-500 text-xs">Direct inzetbare lessen en opdrachten voor in het klaslokaal</p>
            </div>
            <Link
              to="/docenten"
              className="inline-flex items-center gap-1 text-xs font-semibold text-amber-800 hover:text-amber-950"
            >
              Docentenhandleidingen
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {educationalThemes.map((theme, i) => (
              <div
                key={i}
                className="bg-white rounded-2xl p-6 border border-stone-200 shadow-xs flex flex-col justify-between hover:border-amber-700 transition-colors"
              >
                <div>
                  <div className="flex items-center justify-between text-[11px] font-semibold text-stone-500 mb-3">
                    <span className="bg-stone-100 px-2 py-0.5 rounded text-stone-700">{theme.target}</span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-amber-800" />
                      {theme.duration}
                    </span>
                  </div>
                  <h3 className="font-serif font-bold text-stone-900 text-lg mb-2 leading-snug">{theme.title}</h3>
                  <p className="text-xs text-stone-600 leading-relaxed mb-6">{theme.description}</p>
                </div>
                <div className="pt-4 border-t border-stone-100 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs text-stone-500">{theme.modules} werkbladen</span>
                  {handleidingVoor(theme.niveau) && (
                    <Link
                      to={`/item/${handleidingVoor(theme.niveau)!.id}`}
                      className="text-xs font-semibold text-stone-700 hover:underline"
                    >
                      Docentenhandleiding
                    </Link>
                  )}
                  <button
                    onClick={() => handleStartModule(theme.title)}
                    className="text-xs font-bold text-amber-800 hover:underline"
                  >
                    Start module &rarr;
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Werkbladen, per niveau (alleen zichtbaar met een klassessie) */}
        {eduItems.length > 0 && (
          <section id="edu-materials" className="space-y-10">
            <h2 className="font-serif text-2xl font-bold text-stone-900">Werkbladen</h2>
            {[...werkbladenPerNiveau, ...(overigeWerkbladen.length ? [{ niveau: 'overig', items: overigeWerkbladen }] : [])].map(
              (groep) => (
                <div key={groep.niveau}>
                  <h3 className="font-serif text-lg font-bold text-stone-800 mb-4">
                    {niveauNaam[groep.niveau] || 'Overig materiaal'}
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                    {groep.items.map((item) => (
                      <div key={item.id} className="bg-white rounded-2xl p-5 border border-stone-200 shadow-xs">
                        <div className="flex items-start gap-3">
                          <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-900 flex items-center justify-center flex-shrink-0">
                            {item.content_type === 'video' ? <Video className="w-5 h-5" /> : <FileText className="w-5 h-5" />}
                          </div>
                          <div>
                            <h4 className="font-serif font-bold text-stone-900 text-sm leading-snug mb-1">{item.title}</h4>
                            <p className="text-xs text-stone-500 line-clamp-2 mb-3">{item.summary || 'Werkblad.'}</p>
                            <Link
                              to={`/item/${item.id}`}
                              className="inline-flex items-center gap-1 text-xs font-semibold text-amber-800 hover:underline"
                            >
                              Open werkblad
                              <ArrowRight className="w-3 h-3" />
                            </Link>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ),
            )}
          </section>
        )}
      </div>
    </div>
  );
};
