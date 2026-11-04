import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Landmark, Map, Compass, BookOpen, PlusCircle, Shield, Menu, X, Mail, Heart, LogOut, User } from 'lucide-react';
import { api } from '../api/client';
import { useTenant } from '../context/TenantContext';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { tenant } = useTenant();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [newsletterEmail, setNewsletterEmail] = useState('');
  const [newsletterStatus, setNewsletterStatus] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<{ email: string; role: string } | null>(null);
  const location = useLocation();

  useEffect(() => {
    const checkAuth = () => {
      const token = (typeof api?.getAuthToken === 'function' ? api.getAuthToken() : null) || localStorage.getItem('portal_token') || null;
      const stored = localStorage.getItem('portal_user');
      if (token && stored) {
        try {
          setCurrentUser(JSON.parse(stored));
        } catch {
          setCurrentUser(null);
        }
      } else {
        setCurrentUser(null);
      }
    };
    checkAuth();
    window.addEventListener('storage', checkAuth);
    window.addEventListener('auth:unauthorized', checkAuth);
    return () => {
      window.removeEventListener('storage', checkAuth);
      window.removeEventListener('auth:unauthorized', checkAuth);
    };
  }, [location.pathname]);

  const handleLogout = () => {
    if (typeof api?.clearAuthToken === 'function') {
      api.clearAuthToken();
    } else {
      localStorage.removeItem('portal_token');
    }
    localStorage.removeItem('portal_user');
    setCurrentUser(null);
  };

  // Close mobile menu on Escape key for keyboard accessibility
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileMenuOpen) {
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [mobileMenuOpen]);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  const navItems = [
    { to: '/ontdekken', label: 'Ontdekken', icon: Compass },
    { to: '/kaart', label: 'Kaart', icon: Map },
    { to: '/uploaden', label: 'Deel je Verhaal', icon: PlusCircle, highlight: true },
    { to: '/educatie', label: 'Educatie', icon: BookOpen },
    { to: '/over', label: 'Over Ons', icon: Landmark },
    { to: '/doneren', label: 'Doneren', icon: Heart },
  ];

  const handleNewsletterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newsletterEmail) return;
    try {
      await api.subscribeNewsletter(newsletterEmail);
      setNewsletterStatus('Bedankt voor je aanmelding!');
      setNewsletterEmail('');
    } catch {
      setNewsletterStatus('Er ging iets mis. Probeer het later opnieuw.');
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#FDFBF7] text-stone-800">
      {/* Skip-to-content Link (WCAG 2.4.1) */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2.5 focus:bg-amber-800 focus:text-white focus:rounded-xl focus:shadow-xl focus:ring-2 focus:ring-amber-500 focus:ring-offset-2 font-semibold text-sm"
      >
        Direct naar hoofdinhoud
      </a>

      {/* Header Landmark (WCAG 1.3.1) */}
      <header role="banner" className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-stone-200 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          <Link to="/ontdekken" className="flex items-center gap-3 group" aria-label="Het Levend Monument - Ga naar homepagina">
            <div className="w-11 h-11 rounded-xl bg-amber-800 text-white flex items-center justify-center shadow-xs group-hover:bg-amber-700 transition-colors" aria-hidden="true">
              <Landmark className="w-6 h-6" />
            </div>
            <div>
              <span className="font-serif font-bold text-xl tracking-tight text-stone-900 block leading-tight">
                {tenant?.name || 'Het Levend Monument'}
              </span>
              <span className="text-xs text-stone-600 font-medium tracking-wide uppercase">
                Cultuur &amp; Erfgoed Archief
              </span>
            </div>
          </Link>

          {/* Desktop Navigation Landmark */}
          <nav aria-label="Hoofdnavigatie" className="hidden md:flex items-center gap-1.5">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                    item.highlight
                      ? 'bg-amber-800 text-white hover:bg-amber-700 shadow-xs'
                      : isActive
                      ? 'bg-stone-100 text-amber-900 font-semibold'
                      : 'text-stone-700 hover:text-stone-900 hover:bg-stone-50'
                  }`}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon className="w-4 h-4" aria-hidden="true" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Right Action Menu */}
          <div className="hidden lg:flex items-center gap-3">
            {currentUser ? (
              <div className="flex items-center gap-2">
                {currentUser.role === 'admin' || currentUser.role === 'curator' ? (
                  <Link
                    to="/beheer"
                    className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-amber-800/30 bg-amber-50/70 text-amber-900 hover:bg-amber-100 transition-colors"
                  >
                    <Shield className="w-3.5 h-3.5 text-amber-800" aria-hidden="true" />
                    <span>Beheer ({currentUser.role === 'admin' ? 'Admin' : 'Curator'})</span>
                  </Link>
                ) : (
                  <Link
                    to="/mijn-inzendingen"
                    className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-stone-300 bg-stone-50 text-stone-800 hover:bg-stone-100 transition-colors"
                  >
                    <User className="w-3.5 h-3.5 text-amber-800" aria-hidden="true" />
                    <span>Mijn Inzendingen</span>
                  </Link>
                )}
                <button
                  type="button"
                  onClick={handleLogout}
                  title={`Uitloggen (${currentUser.email})`}
                  aria-label={`Uitloggen (${currentUser.email})`}
                  className="p-1.5 text-stone-500 hover:text-rose-700 hover:bg-rose-50 rounded-lg transition-colors"
                >
                  <LogOut className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  to="/beheer"
                  className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-stone-300 text-stone-700 hover:text-stone-900 hover:border-stone-500 transition-colors"
                >
                  <Shield className="w-3.5 h-3.5 text-amber-800" aria-hidden="true" />
                  Curatie
                </Link>
                <Link
                  to="/inloggen"
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-stone-100 text-stone-800 hover:bg-stone-200 transition-colors"
                >
                  Inloggen
                </Link>
              </div>
            )}
          </div>

          {/* Mobile menu toggle button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2.5 rounded-xl text-stone-700 hover:text-stone-900 hover:bg-stone-100 transition-colors"
            aria-label={mobileMenuOpen ? 'Sluit navigatiemenu' : 'Open hoofdmenu'}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-nav"
            type="button"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" aria-hidden="true" /> : <Menu className="w-6 h-6" aria-hidden="true" />}
          </button>
        </div>

        {/* Mobile Dropdown Navigation */}
        {mobileMenuOpen && (
          <nav
            id="mobile-nav"
            aria-label="Mobiele navigatie"
            className="md:hidden border-b border-stone-200 bg-white px-4 pt-2 pb-6 space-y-2 shadow-lg"
          >
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl text-base font-medium ${
                    item.highlight
                      ? 'bg-amber-800 text-white'
                      : isActive
                      ? 'bg-stone-100 text-amber-900 font-semibold'
                      : 'text-stone-700 hover:bg-stone-50'
                  }`}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon className="w-5 h-5" aria-hidden="true" />
                  {item.label}
                </Link>
              );
            })}
            <div className="pt-4 border-t border-stone-100 flex items-center justify-between">
              {currentUser ? (
                <>
                  {currentUser.role === 'admin' || currentUser.role === 'curator' ? (
                    <Link
                      to="/beheer"
                      onClick={() => setMobileMenuOpen(false)}
                      className="flex items-center gap-2 text-sm text-amber-900 font-semibold"
                    >
                      <Shield className="w-4 h-4 text-amber-800" aria-hidden="true" />
                      Beheer ({currentUser.role === 'admin' ? 'Admin' : 'Curator'})
                    </Link>
                  ) : (
                    <Link
                      to="/mijn-inzendingen"
                      onClick={() => setMobileMenuOpen(false)}
                      className="flex items-center gap-2 text-sm text-stone-800 font-medium"
                    >
                      <User className="w-4 h-4 text-amber-800" aria-hidden="true" />
                      Mijn Inzendingen
                    </Link>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      handleLogout();
                      setMobileMenuOpen(false);
                    }}
                    className="text-xs text-rose-700 font-semibold flex items-center gap-1"
                  >
                    <LogOut className="w-3.5 h-3.5" aria-hidden="true" />
                    Uitloggen
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/beheer"
                    onClick={() => setMobileMenuOpen(false)}
                    className="flex items-center gap-2 text-sm text-stone-700 font-medium"
                  >
                    <Shield className="w-4 h-4 text-amber-800" aria-hidden="true" />
                    Curatie &amp; Beheer
                  </Link>
                  <Link
                    to="/inloggen"
                    onClick={() => setMobileMenuOpen(false)}
                    className="text-sm font-semibold text-amber-800"
                  >
                    Inloggen
                  </Link>
                </>
              )}
            </div>
          </nav>
        )}
      </header>

      {/* Main Content Landmark (WCAG 1.3.1 / 2.4.1) */}
      <main id="main-content" tabIndex={-1} className="flex-grow focus:outline-none">
        {children}
      </main>

      {/* Footer Landmark (WCAG 1.3.1) */}
      <footer role="contentinfo" className="bg-stone-900 text-stone-200 pt-16 pb-12 border-t border-stone-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-4 gap-10">
          <div className="space-y-4 md:col-span-2">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-amber-800 text-white flex items-center justify-center" aria-hidden="true">
                <Landmark className="w-5 h-5" />
              </div>
              <span className="font-serif font-bold text-lg text-white">
                {tenant?.name || 'Het Levend Monument'}
              </span>
            </div>
            <p className="text-sm text-stone-300 max-w-md leading-relaxed">
              Het Levend Monument brengt persoonlijke en collectieve herinneringen samen in een open, digitaal
              erfgoedarchief. Samen bouwen we aan een blijvende getuigenis voor de toekomst.
            </p>
            <div className="pt-2">
              <form onSubmit={handleNewsletterSubmit} className="flex gap-2 max-w-md" aria-label="Aanmelden nieuwsbrief">
                <label htmlFor="footer-newsletter-email" className="sr-only">
                  E-mailadres voor nieuwsbrief
                </label>
                <input
                  id="footer-newsletter-email"
                  type="email"
                  value={newsletterEmail}
                  onChange={(e) => setNewsletterEmail(e.target.value)}
                  placeholder="Blijf op de hoogte (e-mailadres)"
                  className="bg-stone-800 border border-stone-700 rounded-xl px-3.5 py-2 text-sm text-white placeholder-stone-400 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 flex-grow"
                  required
                  aria-required="true"
                  aria-describedby={newsletterStatus ? 'footer-newsletter-status' : undefined}
                />
                <button
                  type="submit"
                  className="bg-amber-800 hover:bg-amber-700 text-white px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-1.5 transition-colors shadow-xs"
                  aria-label="Aanmelden voor nieuwsbrief"
                >
                  <Mail className="w-4 h-4" aria-hidden="true" />
                  Meld aan
                </button>
              </form>
              <div className="mt-2">
                <Link to="/nieuwsbrief" className="text-xs text-stone-400 hover:text-amber-300 underline transition-colors">
                  Voorkeuren beheren of edities bekijken &rarr;
                </Link>
              </div>
              {newsletterStatus && (
                <p id="footer-newsletter-status" role="status" aria-live="polite" className="text-xs text-amber-300 mt-2 font-medium">
                  {newsletterStatus}
                </p>
              )}
            </div>
          </div>

          <div>
            <h2 className="font-serif font-bold text-white text-base mb-4">Navigatie</h2>
            <ul className="space-y-2.5 text-sm">
              <li>
                <Link to="/ontdekken" className="hover:text-white transition-colors">
                  Ontdek Verhalen
                </Link>
              </li>
              <li>
                <Link to="/kaart" className="hover:text-white transition-colors">
                  Kaart van Herinneringen
                </Link>
              </li>
              <li>
                <Link to="/uploaden" className="hover:text-white transition-colors">
                  Deel je Verhaal
                </Link>
              </li>
              <li>
                <Link to="/educatie" className="hover:text-white transition-colors">
                  Educatie &amp; Scholen
                </Link>
              </li>
              <li>
                <Link to="/docenten" className="hover:text-white transition-colors">
                  Docenten Portaal
                </Link>
              </li>
              <li>
                <Link to="/nieuwsbrief" className="hover:text-white transition-colors">
                  Nieuwsbrief Archief
                </Link>
              </li>
              <li>
                <Link to="/doneren" className="hover:text-white transition-colors flex items-center gap-1.5 text-amber-300">
                  <Heart className="w-3.5 h-3.5 fill-amber-300" aria-hidden="true" />
                  Steun het Monument
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h2 className="font-serif font-bold text-white text-base mb-4">Informatie &amp; Open Data</h2>
            <ul className="space-y-2.5 text-sm">
              <li>
                <Link to="/over" className="hover:text-white transition-colors">
                  Over dit initiatief
                </Link>
              </li>
              <li>
                <Link to="/toegankelijkheid" className="text-amber-300 font-medium hover:text-white transition-colors">
                  Toegankelijkheidsverklaring
                </Link>
              </li>
              <li>
                <Link to="/privacy" className="text-amber-300 font-medium hover:text-white transition-colors">
                  Privacyverklaring
                </Link>
              </li>
              <li>
                <Link to="/data-export" className="hover:text-white transition-colors">
                  OAI-PMH &amp; Open Data
                </Link>
              </li>
              <li>
                <a
                  href="/api/v1/foundation/sitemap.xml"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-white transition-colors"
                >
                  Sitemap (XML)
                </a>
              </li>
              <li>
                <Link to="/ntd" className="hover:text-white transition-colors">
                  Notice &amp; Takedown
                </Link>
              </li>
              <li>
                <Link to="/contact" className="hover:text-white transition-colors">
                  Contact &amp; Ondersteuning
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-12 mt-12 border-t border-stone-800 flex flex-col sm:flex-row items-center justify-between text-xs text-stone-300 gap-4">
          <p>&copy; 2026 Het Levend Monument. Alle rechten voorbehouden.</p>
          <div className="flex items-center gap-6">
            <span>Conform Netwerk Digitaal Erfgoed (NDE)</span>
            <span>WCAG 2.1 AA Gecertificeerd</span>
            <span>Open Data v2.0</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
