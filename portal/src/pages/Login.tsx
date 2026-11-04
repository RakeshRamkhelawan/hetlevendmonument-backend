import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { Mail, CheckCircle2, AlertCircle, Shield, ArrowRight, LogOut, KeyRound, Lock, User } from 'lucide-react';
import { api } from '../api/client';
import { HCaptchaWidget } from '../components/HCaptchaWidget';
import { neemNaInloggen } from '../naInloggen';

/**
 * Na het inloggen: een docent naar het docentenportaal (BE-EP-055), curator en
 * beheerder naar beheer, een verteller naar Mijn Inzendingen (BE-EP-056).
 */
const standaardDoel = (rol: string | undefined) => {
  if (rol === 'teacher') return '/docenten';
  if (rol === 'admin' || rol === 'curator') return '/beheer';
  return '/mijn-inzendingen';
};

export const Login: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const isProduction = import.meta.env.VITE_ENVIRONMENT === 'production';
  const isDevHost =
    !isProduction &&
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

  const [authMode, setAuthMode] = useState<'password' | 'magic_link'>('password');
  const [username, setUsername] = useState(isDevHost ? 'admin' : '');
  const [password, setPassword] = useState(isDevHost ? 'Tester01' : '');

  const [email, setEmail] = useState('');
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [devMagicLink, setDevMagicLink] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<{ email: string; role: string } | null>(null);

  useEffect(() => {
    // Check if user is already logged in
    const storedToken = localStorage.getItem('portal_token');
    const storedUser = localStorage.getItem('portal_user');
    if (storedToken && storedUser) {
      try {
        setCurrentUser(JSON.parse(storedUser));
      } catch {
        // ignore
      }
    }

    // If token present in URL, verify it
    if (token) {
      const verify = async () => {
        setLoading(true);
        setError(null);
        try {
          const res = await api.verifyMagicLink(token);
          localStorage.setItem('portal_user', JSON.stringify(res.user));
          setCurrentUser(res.user);
          setMessage('Inloggen geslaagd! U wordt doorgestuurd...');
          // BE-EP-056: wie de link aanvroeg vanaf "Deel je verhaal", komt daar terug.
          const target = searchParams.get('redirect') || neemNaInloggen() || standaardDoel(res.user.role);
          setTimeout(() => navigate(target), 1500);
        } catch (err: unknown) {
          setError(err instanceof Error ? err.message : 'Ongeldige of verlopen inloglink.');
        } finally {
          setLoading(false);
        }
      };
      verify();
    }
  }, [token, navigate]);

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;

    setLoading(true);
    setError(null);
    setMessage('Inloggen...');

    try {
      const res = await api.loginWithPassword(username, password);
      localStorage.setItem('portal_user', JSON.stringify(res.user));
      setCurrentUser(res.user);
      setMessage('Inloggen geslaagd! U wordt doorgestuurd...');
      const target = searchParams.get('redirect') || standaardDoel(res.user.role);
      setTimeout(() => navigate(target), 1000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ongeldige gebruikersnaam of wachtwoord.');
    } finally {
      setLoading(false);
    }
  };

  const handleRequestMagicLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    setLoading(true);
    setError(null);
    setMessage(null);
    setDevMagicLink(null);

    try {
      const res = await api.requestMagicLink(email, captchaToken);
      if (res.dev_magic_link_url) {
        setDevMagicLink(res.dev_magic_link_url);
        setMessage('Inloglink gegenereerd voor lokale ontwikkelmodus.');
      } else {
        setMessage(res.message || 'Er is een inloglink verstuurd naar uw e-mailadres.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Fout bij aanvragen van inloglink.');
    } finally {
      setLoading(false);
    }
  };

  const handleDevQuickLogin = async (role: 'admin' | 'curator' | 'bezoeker') => {
    setLoading(true);
    setError(null);
    setMessage(`Direct inloggen als ${role}...`);
    try {
      const res = await api.quickLogin(role);
      localStorage.setItem('portal_user', JSON.stringify(res.user));
      setCurrentUser(res.user);
      setMessage(`Inloggen als ${res.user.role} geslaagd! U wordt doorgestuurd...`);
      const target =
        searchParams.get('redirect') ||
        (role === 'bezoeker' ? '/mijn-inzendingen' : '/beheer');
      setTimeout(() => navigate(target), 800);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Fout bij direct inloggen.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    api.clearAuthToken();
    localStorage.removeItem('portal_user');
    setCurrentUser(null);
    setMessage('U bent succesvol uitgelogd.');
  };

  return (
    <div className="min-h-[75vh] flex items-center justify-center py-16 px-4 bg-[#FDFBF7]">
      <div className="max-w-md w-full bg-white rounded-3xl p-8 border border-stone-200 shadow-sm">
        {currentUser ? (
          <div className="text-center space-y-6">
            <div className="w-14 h-14 bg-amber-100 text-amber-900 rounded-full flex items-center justify-center mx-auto">
              <Shield className="w-7 h-7 text-amber-800" />
            </div>
            <div>
              <h2 className="font-serif text-2xl font-bold text-stone-900 mb-1">Ingelogd</h2>
              <p className="text-stone-500 text-xs">
                Ingelogd als <strong className="text-stone-800">{currentUser.email}</strong> ({currentUser.role})
              </p>
            </div>
            <div className="flex flex-col gap-3">
              {currentUser.role === 'visitor' || currentUser.role === 'bezoeker' ? (
                <Link
                  to="/mijn-inzendingen"
                  className="w-full bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm py-3 px-4 rounded-xl transition-colors inline-flex items-center justify-center gap-2"
                >
                  <span>Ga naar Mijn Inzendingen</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
              ) : (
                <Link
                  to="/beheer"
                  className="w-full bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm py-3 px-4 rounded-xl transition-colors inline-flex items-center justify-center gap-2"
                >
                  <span>Ga naar Beheerpaneel</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
              )}
              <button
                onClick={handleLogout}
                className="w-full bg-stone-100 hover:bg-stone-200 text-stone-700 font-semibold text-sm py-3 px-4 rounded-xl transition-colors inline-flex items-center justify-center gap-2"
              >
                <LogOut className="w-4 h-4" />
                <span>Uitloggen</span>
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className="text-center mb-6">
              <div className="w-12 h-12 bg-amber-100 text-amber-900 rounded-full flex items-center justify-center mx-auto mb-3">
                <KeyRound className="w-6 h-6 text-amber-800" />
              </div>
              <h1 className="font-serif text-2xl font-bold text-stone-900 mb-1">Inloggen voor Beheerders</h1>
              <p className="text-stone-500 text-xs">
                {authMode === 'password'
                  ? 'Log in met uw gebruikersnaam en wachtwoord.'
                  : 'Voer uw e-mailadres in om een veilige eenmalige inloglink te ontvangen.'}
              </p>
            </div>

            {/* Inlogmethode Tab Switcher */}
            <div className="flex border border-stone-200 rounded-xl p-1 bg-stone-100/70 mb-6">
              <button
                type="button"
                onClick={() => { setAuthMode('password'); setError(null); setMessage(null); }}
                className={`flex-1 py-2 text-xs font-semibold rounded-lg flex items-center justify-center gap-1.5 transition ${
                  authMode === 'password'
                    ? 'bg-white text-stone-900 shadow-xs border border-stone-200/50'
                    : 'text-stone-500 hover:text-stone-700'
                }`}
              >
                <KeyRound className="w-3.5 h-3.5" />
                <span>Wachtwoord</span>
              </button>
              <button
                type="button"
                onClick={() => { setAuthMode('magic_link'); setError(null); setMessage(null); }}
                className={`flex-1 py-2 text-xs font-semibold rounded-lg flex items-center justify-center gap-1.5 transition ${
                  authMode === 'magic_link'
                    ? 'bg-white text-stone-900 shadow-xs border border-stone-200/50'
                    : 'text-stone-500 hover:text-stone-700'
                }`}
              >
                <Mail className="w-3.5 h-3.5" />
                <span>Magic Link</span>
              </button>
            </div>

            {message && (
              <div id="login-message" role="status" aria-live="polite" className="mb-6 p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-start gap-3">
                <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <span>{message}</span>
              </div>
            )}

            {error && (
              <div id="login-error" role="alert" aria-live="assertive" className="mb-6 p-4 rounded-2xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-start gap-3">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            {devMagicLink && !isProduction && (
              <div className="mb-6 p-4 rounded-2xl bg-amber-50 border border-amber-300 text-amber-950 text-xs space-y-2">
                <div className="font-bold flex items-center gap-1.5 text-amber-900">
                  <KeyRound className="w-4 h-4" />
                  <span>Lokale Ontwikkelmodus - Direct Inloggen</span>
                </div>
                <p className="text-amber-800/90">
                  Er is lokaal een eenmalige inloglink gegenereerd:
                </p>
                <a
                  href={typeof window !== 'undefined' ? devMagicLink.replace(/^https?:\/\/[^/]+/, window.location.origin) : devMagicLink}
                  className="inline-flex items-center justify-center gap-2 bg-amber-800 hover:bg-amber-700 text-white font-semibold py-2 px-3 rounded-xl text-xs transition"
                >
                  <span>Klik hier om direct in te loggen</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </a>
              </div>
            )}

            {authMode === 'password' ? (
              <form onSubmit={handlePasswordLogin} className="space-y-4" aria-label="Wachtwoord inlogformulier">
                <div>
                  <label htmlFor="username" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                    Gebruikersnaam of E-mailadres <span className="text-red-600" aria-hidden="true">*</span>
                  </label>
                  <div className="relative">
                    <User className="w-4 h-4 text-stone-500 absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
                    <input
                      id="username"
                      type="text"
                      required
                      aria-required="true"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder={isDevHost ? 'admin of admin@levendmonument.nl' : 'naam@hetlevendmonument.nl'}
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="password" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                    Wachtwoord <span className="text-red-600" aria-hidden="true">*</span>
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-stone-500 absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
                    <input
                      id="password"
                      type="password"
                      required
                      aria-required="true"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={isDevHost ? 'Tester01' : '••••••••'}
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                    />
                  </div>
                  <div className="flex justify-end mt-1.5">
                    <button
                      type="button"
                      onClick={() => {
                        setAuthMode('magic_link');
                        setMessage('Voer uw e-mailadres in om een eenmalige inloglink te ontvangen.');
                      }}
                      className="text-xs text-amber-800 hover:text-amber-900 underline transition-colors"
                    >
                      Wachtwoord vergeten?
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  aria-busy={loading}
                  className="w-full bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm py-3 px-4 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {loading ? 'Inloggen...' : 'Inloggen met Wachtwoord'}
                </button>
              </form>
            ) : (
              <form onSubmit={handleRequestMagicLink} className="space-y-4" aria-label="Magic link inlogformulier">
                <div>
                  <label htmlFor="email" className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1.5">
                    E-mailadres <span className="text-red-600" aria-hidden="true">*</span>
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-stone-500 absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
                    <input
                      id="email"
                      type="email"
                      required
                      aria-required="true"
                      aria-invalid={!!error}
                      aria-describedby={error ? 'login-error' : message ? 'login-message' : undefined}
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder={isDevHost ? 'curator@levendmonument.nl' : 'uw.naam@organisatie.nl'}
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-stone-200 focus:outline-none focus:border-amber-700 text-sm bg-stone-50/50"
                    />
                  </div>
                </div>

                <HCaptchaWidget onVerify={setCaptchaToken} className="pt-1" />

                <button
                  type="submit"
                  disabled={loading}
                  aria-busy={loading}
                  className="w-full bg-amber-800 hover:bg-amber-700 text-white font-semibold text-sm py-3 px-4 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {loading ? 'Verzenden...' : 'Verstuur Magic Link'}
                </button>
              </form>
            )}

            {isDevHost && (
              <div className="mt-8 pt-6 border-t border-stone-200">
                <div className="flex items-center gap-2 mb-2 text-amber-900 font-bold text-xs uppercase tracking-wider">
                  <Shield className="w-4 h-4 text-amber-800" />
                  <span>Direct Inloggen (Lokale Testaccounts)</span>
                </div>
                <p className="text-stone-500 text-xs mb-3">
                  Klik op een rol om direct zonder e-mailinbox in te loggen:
                </p>
                <div className="space-y-2">
                  <button
                    type="button"
                    onClick={() => handleDevQuickLogin('curator')}
                    disabled={loading}
                    className="w-full text-left p-3 rounded-xl border border-amber-200 bg-amber-50/70 hover:bg-amber-100 text-amber-950 text-xs font-medium transition flex items-center justify-between group"
                  >
                    <div>
                      <div className="font-bold text-amber-900">Curator (Beheer &amp; Curatiepaneel)</div>
                      <div className="text-[11px] text-amber-700/80">curator@levendmonument.nl</div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-amber-700 group-hover:translate-x-0.5 transition-transform" />
                  </button>

                  <button
                    type="button"
                    onClick={() => handleDevQuickLogin('admin')}
                    disabled={loading}
                    className="w-full text-left p-3 rounded-xl border border-stone-200 bg-stone-50 hover:bg-stone-100 text-stone-900 text-xs font-medium transition flex items-center justify-between group"
                  >
                    <div>
                      <div className="font-bold text-stone-800">Administrator (Volledig Beheer)</div>
                      <div className="text-[11px] text-stone-500">admin@levendmonument.nl</div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-stone-600 group-hover:translate-x-0.5 transition-transform" />
                  </button>

                  <button
                    type="button"
                    onClick={() => handleDevQuickLogin('bezoeker')}
                    disabled={loading}
                    className="w-full text-left p-3 rounded-xl border border-stone-200 bg-stone-50 hover:bg-stone-100 text-stone-900 text-xs font-medium transition flex items-center justify-between group"
                  >
                    <div>
                      <div className="font-bold text-stone-800">Bezoeker (Inzender)</div>
                      <div className="text-[11px] text-stone-500">bezoeker@levendmonument.nl</div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-stone-600 group-hover:translate-x-0.5 transition-transform" />
                  </button>
                </div>
              </div>
            )}

            <div className="mt-8 pt-6 border-t border-stone-100 text-center text-xs text-stone-400">
              Beveiligd conform AVG &amp; SanskritiSetu Auth Framework.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
