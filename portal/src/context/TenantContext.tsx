import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  ReactNode,
} from 'react';
import type { TenantPublicInfo, PortalSettingsResponse } from '../types';
import { api } from '../api/client';

export interface TenantContextType {
  tenant: TenantPublicInfo | null;
  settings: PortalSettingsResponse | null;
  loading: boolean;
  error: string | null;
  reloadTenant: () => Promise<void>;
  loadSettings: () => Promise<PortalSettingsResponse | null>;
  setSettings: (settings: PortalSettingsResponse | null) => void;
}

const TenantContext = createContext<TenantContextType | undefined>(undefined);

export interface TenantProviderProps {
  children: ReactNode;
  initialTenant?: TenantPublicInfo | null;
  initialSettings?: PortalSettingsResponse | null;
}

export const TenantProvider: React.FC<TenantProviderProps> = ({
  children,
  initialTenant = null,
  initialSettings = null,
}) => {
  const [tenant, setTenant] = useState<TenantPublicInfo | null>(initialTenant);
  const [settings, setSettings] = useState<PortalSettingsResponse | null>(initialSettings);
  const [loading, setLoading] = useState<boolean>(!initialTenant);
  const [error, setError] = useState<string | null>(null);

  const resolveTenant = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError(null);
    try {
      // 1. Check URL parameters for dev / debug overrides (?tenant=slug or ?domain=host)
      const searchParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
      const slugOverride = searchParams?.get('tenant') || searchParams?.get('slug');
      const domainOverride = searchParams?.get('domain');

      // 2. Extract current hostname
      const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
      const isLocalhost = host === 'localhost' || host === '127.0.0.1';

      const resolved = await api.resolveCurrentTenant({
        host,
        slug: slugOverride || (isLocalhost ? 'default' : undefined),
        domain: domainOverride || undefined,
        forceRefresh,
      });

      setTenant(resolved);
      if (resolved.name && typeof document !== 'undefined') {
        document.title = `${resolved.name} | Het Levend Monument`;
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Onbekende fout bij laden van stichting';
      setError(msg);
      setTenant(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSettings = useCallback(async (): Promise<PortalSettingsResponse | null> => {
    try {
      const res = await api.getPortalSettings();
      setSettings(res);
      return res;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!initialTenant) {
      void resolveTenant();
    }
  }, [initialTenant, resolveTenant]);

  const value: TenantContextType = {
    tenant,
    settings,
    loading,
    error,
    reloadTenant: () => resolveTenant(true),
    loadSettings,
    setSettings,
  };

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
};

export function useTenant(): TenantContextType {
  const context = useContext(TenantContext);
  if (!context) {
    return {
      tenant: null,
      settings: null,
      loading: false,
      error: null,
      reloadTenant: async () => {},
      loadSettings: async () => null,
      setSettings: () => {},
    };
  }
  return context;
}

