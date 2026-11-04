import React, { ReactNode } from 'react';
import { Landmark, AlertCircle, RefreshCw } from 'lucide-react';
import { useTenant } from '../context/TenantContext';

interface TenantGuardProps {
  children: ReactNode;
}

export const TenantGuard: React.FC<TenantGuardProps> = ({ children }) => {
  const { tenant, loading, error, reloadTenant } = useTenant();

  if (loading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="min-h-screen flex flex-col items-center justify-center bg-[#FDFBF7] text-stone-800 px-4"
      >
        <div className="w-16 h-16 rounded-2xl bg-amber-800 text-white flex items-center justify-center shadow-md animate-pulse mb-6" aria-hidden="true">
          <Landmark className="w-8 h-8" />
        </div>
        <h1 className="font-serif font-bold text-2xl text-stone-900 mb-2 text-center">
          Erfgoedarchief laden...
        </h1>
        <p className="text-sm text-stone-600 max-w-sm text-center">
          Even geduld a.u.b., de stichting en het erfgoedarchief worden geladen.
        </p>
      </div>
    );
  }

  if (error || !tenant) {
    return (
      <div
        role="alert"
        aria-live="assertive"
        className="min-h-screen flex flex-col items-center justify-center bg-[#FDFBF7] text-stone-800 px-4"
      >
        <div className="max-w-md w-full bg-white border border-stone-200 rounded-2xl p-8 shadow-sm text-center">
          <div className="w-14 h-14 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center mx-auto mb-5" aria-hidden="true">
            <AlertCircle className="w-7 h-7" />
          </div>
          <h1 className="font-serif font-bold text-2xl text-stone-900 mb-3">
            Erfgoedplatform niet gevonden
          </h1>
          <p className="text-sm text-stone-600 leading-relaxed mb-6">
            Het domein of de stichting die u probeert te bezoeken is niet geregistreerd of momenteel niet actief op Het Levend Monument.
          </p>
          {error && (
            <div className="bg-stone-50 border border-stone-200 rounded-lg p-3 text-xs text-stone-500 font-mono mb-6 text-left break-all">
              {error}
            </div>
          )}
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button
              onClick={() => void reloadTenant()}
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-amber-800 text-white text-sm font-semibold hover:bg-amber-700 transition-colors shadow-xs"
            >
              <RefreshCw className="w-4 h-4" aria-hidden="true" />
              Opnieuw proberen
            </button>
            <a
              href="https://levend-monument.nl"
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl border border-stone-300 text-stone-700 text-sm font-semibold hover:bg-stone-50 hover:text-stone-900 transition-colors"
            >
              Naar hoofdplatform
            </a>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};
