import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ApiClient, api } from '../api/client';
import { TenantProvider, useTenant } from '../context/TenantContext';
import { TenantGuard } from '../components/TenantGuard';
import { Layout } from '../components/Layout';
import type { TenantPublicInfo } from '../types';

describe('FE-TENANT-001: Frontend Dynamic Tenant Bootstrap & Subdomain Resolution', () => {
  const mockTenant: TenantPublicInfo = {
    id: 42,
    name: 'Stichting Ketikoti Vlaardingen',
    slug: 'ketikoti',
    domain: 'ketikoti.levend-monument.nl',
    is_active: true,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    document.title = 'Het Levend Monument';
    api.resetTenantCache();
  });

  describe('ApiClient.resolveCurrentTenant', () => {
    it('succesvol tenant resolven en interne slug en metadata bijwerken', async () => {
      const client = new ApiClient('default', '/api/v1');
      expect(client.getTenantSlug()).toBe('default');
      expect(client.getTenantPublicInfo()).toBeNull();

      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockTenant,
      } as unknown as Response);

      const result = await client.resolveCurrentTenant({ host: 'ketikoti.levend-monument.nl' });

      expect(fetchSpy).toHaveBeenCalledWith(
        '/api/v1/foundation/tenant/resolve',
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'x-tenant-domain': 'ketikoti.levend-monument.nl',
          }),
        })
      );
      expect(result).toEqual(mockTenant);
      expect(client.getTenantSlug()).toBe('ketikoti');
      expect(client.getTenantPublicInfo()).toEqual(mockTenant);
    });

    it('stuurt query parameters door bij dev override opties', async () => {
      const client = new ApiClient('default', '/api/v1');

      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockTenant,
      } as unknown as Response);

      await client.resolveCurrentTenant({ slug: 'ketikoti', domain: 'custom.nl' });

      expect(fetchSpy).toHaveBeenCalledWith(
        '/api/v1/foundation/tenant/resolve?slug=ketikoti&domain=custom.nl',
        expect.anything()
      );
    });

    it('werpt een duidelijke fout wanneer het endpoint 404 retourneert', async () => {
      const client = new ApiClient('default', '/api/v1');

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ detail: 'Tenant domain niet gevonden' }),
      } as unknown as Response);

      await expect(
        client.resolveCurrentTenant({ host: 'onbekend.nl' })
      ).rejects.toThrow('Tenant resolution failed (404): Tenant domain niet gevonden');
    });

    it('dedupliceert gelijktijdige in-flight requests naar exact 1 fetch aanroep', async () => {
      const client = new ApiClient('default', '/api/v1');

      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockTenant,
      } as unknown as Response);

      const [res1, res2] = await Promise.all([
        client.resolveCurrentTenant({ host: 'ketikoti.levend-monument.nl' }),
        client.resolveCurrentTenant({ host: 'ketikoti.levend-monument.nl' }),
      ]);

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(res1).toEqual(mockTenant);
      expect(res2).toEqual(mockTenant);
    });

    it('retourneert direct gecachete tenant info zonder extra fetch tenzij forceRefresh', async () => {
      const client = new ApiClient('default', '/api/v1');

      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => mockTenant,
      } as unknown as Response);

      await client.resolveCurrentTenant({ slug: 'ketikoti' });
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      const cached = await client.resolveCurrentTenant({ slug: 'ketikoti' });
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(cached).toEqual(mockTenant);

      await client.resolveCurrentTenant({ slug: 'ketikoti', forceRefresh: true });
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });
  });

  describe('TenantProvider & TenantGuard Integration', () => {
    it('rendert laadindicator met role="status" tijdens resolutie', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(
        () => new Promise(() => {}) // Hangs indefinitely to test loading state
      );

      render(
        <TenantProvider>
          <TenantGuard>
            <div data-testid="protected-content">Content</div>
          </TenantGuard>
        </TenantProvider>
      );

      const loader = screen.getByRole('status');
      expect(loader).toBeInTheDocument();
      expect(screen.getByText('Erfgoedarchief laden...')).toBeInTheDocument();
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
      api.resetTenantCache();
    });

    it('rendert toegankelijke foutkaart met role="alert" bij onbekende tenant', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ detail: 'Onbekend domein' }),
      } as unknown as Response);

      render(
        <TenantProvider>
          <TenantGuard>
            <div data-testid="protected-content">Content</div>
          </TenantGuard>
        </TenantProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });

      expect(screen.getByText('Erfgoedplatform niet gevonden')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Opnieuw proberen/i })).toBeInTheDocument();
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
    });

    it('rendert content en werkt document.title bij wanneer resolutie slaagt', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockTenant,
      } as unknown as Response);

      function TestConsumer() {
        const { tenant } = useTenant();
        return <div data-testid="resolved-name">{tenant?.name}</div>;
      }

      render(
        <TenantProvider>
          <TenantGuard>
            <TestConsumer />
          </TenantGuard>
        </TenantProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('resolved-name')).toHaveTextContent('Stichting Ketikoti Vlaardingen');
      });

      expect(document.title).toBe('Stichting Ketikoti Vlaardingen | Het Levend Monument');
    });

    it('herprobeert resolutie bij klik op "Opnieuw proberen"', async () => {
      const user = userEvent.setup();

      // Eerst faalt het verzoek
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce({
          ok: false,
          status: 503,
          statusText: 'Service Unavailable',
          json: async () => ({ detail: 'Database connecting...' }),
        } as unknown as Response)
        // Tweede keer slaagt het
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockTenant,
        } as unknown as Response);

      render(
        <TenantProvider>
          <TenantGuard>
            <div data-testid="protected-content">Succesvol hersteld</div>
          </TenantGuard>
        </TenantProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });

      const retryBtn = screen.getByRole('button', { name: /Opnieuw proberen/i });
      await user.click(retryBtn);

      await waitFor(() => {
        expect(screen.getByTestId('protected-content')).toBeInTheDocument();
      });

      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });
  });

  describe('Layout Branding met TenantContext', () => {
    it('toont dynamische stichtingsnaam in navbar en footer', async () => {
      render(
        <TenantProvider initialTenant={mockTenant}>
          <MemoryRouter>
            <Layout>
              <div>Pagina inhoud</div>
            </Layout>
          </MemoryRouter>
        </TenantProvider>
      );

      // Zowel header als footer moeten de dynamische naam bevatten
      const matches = screen.getAllByText('Stichting Ketikoti Vlaardingen');
      expect(matches.length).toBeGreaterThanOrEqual(2);
    });

    it('valt elegant terug op "Het Levend Monument" als er geen tenant context is', async () => {
      render(
        <MemoryRouter>
          <Layout>
            <div>Fallback inhoud</div>
          </Layout>
        </MemoryRouter>
      );

      const matches = screen.getAllByText('Het Levend Monument');
      expect(matches.length).toBeGreaterThanOrEqual(2);
    });
  });
});
