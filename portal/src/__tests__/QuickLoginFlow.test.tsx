import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Login } from '../pages/Login';
import { api } from '../api/client';

describe('QuickLogin & Password Auth Flow (WI-4, WI-10)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('wisselt naar magic link modus bij klikken op Wachtwoord vergeten', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const forgotBtn = screen.getByText('Wachtwoord vergeten?');
    expect(forgotBtn).toBeInTheDocument();

    fireEvent.click(forgotBtn);

    expect(screen.getByText('Verstuur Magic Link')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('curator@levendmonument.nl')).toBeInTheDocument();
  });

  it('logt direct in met testaccount Administrator bij 1-klik knop', async () => {
    const quickLoginSpy = vi.spyOn(api, 'quickLogin').mockResolvedValueOnce({
      access_token: 'mock-jwt-admin-token',
      token_type: 'bearer',
      user: { email: 'admin@levendmonument.nl', role: 'admin' },
    });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const adminBtn = screen.getByText('Administrator (Volledig Beheer)');
    expect(adminBtn).toBeInTheDocument();

    fireEvent.click(adminBtn);

    await waitFor(() => {
      expect(quickLoginSpy).toHaveBeenCalledWith('admin');
    });

    expect(localStorage.getItem('portal_user')).toContain('admin@levendmonument.nl');
  });

  it('logt direct in met testaccount Bezoeker bij 1-klik knop', async () => {
    const quickLoginSpy = vi.spyOn(api, 'quickLogin').mockResolvedValueOnce({
      access_token: 'mock-jwt-visitor-token',
      token_type: 'bearer',
      user: { email: 'bezoeker@levendmonument.nl', role: 'visitor' },
    });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const visitorBtn = screen.getByText('Bezoeker (Inzender)');
    expect(visitorBtn).toBeInTheDocument();

    fireEvent.click(visitorBtn);

    await waitFor(() => {
      expect(quickLoginSpy).toHaveBeenCalledWith('bezoeker');
    });

    expect(localStorage.getItem('portal_user')).toContain('bezoeker@levendmonument.nl');
  });
});
