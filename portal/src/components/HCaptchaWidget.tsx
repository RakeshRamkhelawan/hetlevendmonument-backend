import React, { useEffect, useRef, useState } from 'react';
import { ShieldCheck, ShieldAlert } from 'lucide-react';

declare global {
  interface Window {
    hcaptcha?: {
      render: (
        container: HTMLElement,
        params: {
          sitekey: string;
          callback: (token: string) => void;
          'expired-callback'?: () => void;
          'error-callback'?: (err: unknown) => void;
          theme?: 'light' | 'dark';
        }
      ) => string;
      reset: (widgetId?: string) => void;
      remove: (widgetId?: string) => void;
    };
  }
}

export interface HCaptchaWidgetProps {
  onVerify: (token: string) => void;
  onExpire?: () => void;
  onError?: (err: unknown) => void;
  className?: string;
}

export const HCaptchaWidget: React.FC<HCaptchaWidgetProps> = ({
  onVerify,
  onExpire,
  onError,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const siteKey = import.meta.env.VITE_HCAPTCHA_SITE_KEY;

  useEffect(() => {
    // Als er geen site key is geconfigureerd (dev/test/CI omgeving),
    // functioneren we in veilige testmodus en leveren direct een mock token.
    if (!siteKey) {
      onVerify('mock-test-hcaptcha-token');
      return;
    }

    let isMounted = true;

    const renderWidget = () => {
      if (!containerRef.current || !window.hcaptcha || widgetIdRef.current !== null) {
        return;
      }
      try {
        const id = window.hcaptcha.render(containerRef.current, {
          sitekey: siteKey,
          callback: (token: string) => {
            if (isMounted) onVerify(token);
          },
          'expired-callback': () => {
            if (isMounted && onExpire) onExpire();
          },
          'error-callback': (err: unknown) => {
            if (isMounted && onError) onError(err);
          },
        });
        widgetIdRef.current = id;
      } catch (e) {
        if (isMounted) {
          setLoadError('Kon spambeveiliging niet initialiseren');
          if (onError) onError(e);
        }
      }
    };

    if (window.hcaptcha) {
      renderWidget();
    } else {
      const existingScript = document.querySelector('script[src*="hcaptcha.com/1/api.js"]');
      if (!existingScript) {
        const script = document.createElement('script');
        script.src = 'https://js.hcaptcha.com/1/api.js?render=explicit';
        script.async = true;
        script.defer = true;
        script.onload = () => {
          if (isMounted) renderWidget();
        };
        script.onerror = () => {
          if (isMounted) {
            setLoadError('Spambeveiliging kon niet worden geladen');
            if (onError) onError(new Error('Failed to load hCaptcha script'));
          }
        };
        document.head.appendChild(script);
      } else {
        existingScript.addEventListener('load', renderWidget);
      }
    }

    return () => {
      isMounted = false;
      if (widgetIdRef.current && window.hcaptcha) {
        try {
          window.hcaptcha.remove(widgetIdRef.current);
        } catch {
          // Negeer teardown fouten bij unmounten
        }
        widgetIdRef.current = null;
      }
    };
  }, [siteKey, onVerify, onExpire, onError]);

  if (!siteKey) {
    return (
      <div
        role="region"
        aria-label="Spambeveiliging verificatie"
        className={`p-3 bg-stone-50 border border-stone-200 rounded-lg text-xs text-stone-600 flex items-center gap-2 ${className}`}
      >
        <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" aria-hidden="true" />
        <span>Bot-protectie: Testmodus (automatisch geverifieerd)</span>
      </div>
    );
  }

  return (
    <div
      role="region"
      aria-label="Spambeveiliging verificatie"
      className={`min-h-[78px] flex flex-col items-start ${className}`}
    >
      <div ref={containerRef} />
      {loadError && (
        <div role="alert" className="mt-2 text-xs text-red-600 flex items-center gap-1">
          <ShieldAlert className="w-3.5 h-3.5" aria-hidden="true" />
          <span>{loadError}</span>
        </div>
      )}
    </div>
  );
};
