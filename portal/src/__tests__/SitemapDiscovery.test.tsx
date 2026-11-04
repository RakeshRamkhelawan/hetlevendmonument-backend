import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DataExport } from '../pages/DataExport';
import { Layout } from '../components/Layout';
import { TenantProvider } from '../context/TenantContext';

describe('FE-SEO-001: Sitemap XML Discovery in Portal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('toont XML sitemap endpoint in DataExport pagina met correcte beschrijving', () => {
    render(
      <MemoryRouter>
        <DataExport />
      </MemoryRouter>
    );

    expect(screen.getByText(/5\. XML Sitemap/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Gestandaardiseerde sitemaps\.org XML-index van alle goedgekeurde erfgoedstukken/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/\/api\/v1\/foundation\/sitemap\.xml/i)).toBeInTheDocument();
  });

  it('kopieert sitemap URL naar het klembord bij klikken op de kopieerknop', async () => {
    render(
      <MemoryRouter>
        <DataExport />
      </MemoryRouter>
    );

    const copyButtons = screen.getAllByTitle('Kopieer URL');
    // Button 5 corresponds to sitemap
    const sitemapCopyBtn = copyButtons[copyButtons.length - 1];
    fireEvent.click(sitemapCopyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/foundation/sitemap.xml')
    );

    await waitFor(() => {
      expect(screen.getByTitle('Gekopieerd')).toBeInTheDocument();
    });
  });

  it('toont directe link naar Sitemap (XML) in footer van Layout', () => {
    render(
      <MemoryRouter>
        <TenantProvider>
          <Layout>
            <div>Test Inhoud</div>
          </Layout>
        </TenantProvider>
      </MemoryRouter>
    );

    const sitemapLink = screen.getByRole('link', { name: /Sitemap \(XML\)/i });
    expect(sitemapLink).toBeInTheDocument();
    expect(sitemapLink).toHaveAttribute('href', '/api/v1/foundation/sitemap.xml');
    expect(sitemapLink).toHaveAttribute('target', '_blank');
  });
});
