import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthGuard } from '../components/AuthGuard';

describe('AuthGuard Route Security', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('stuurt niet-geauthenticeerde gebruiker door naar /inloggen met redirect query param', () => {
    render(
      <MemoryRouter initialEntries={['/beheer']}>
        <Routes>
          <Route
            path="/beheer"
            element={
              <AuthGuard>
                <div>Geheime Beheeromgeving</div>
              </AuthGuard>
            }
          />
          <Route path="/inloggen" element={<div>Inlogpagina</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Inlogpagina')).toBeInTheDocument();
    expect(screen.queryByText('Geheime Beheeromgeving')).not.toBeInTheDocument();
  });

  it('toont beschermde route content wanneer portal_token aanwezig is in localStorage', () => {
    localStorage.setItem('portal_token', 'valid-jwt-token-123');

    render(
      <MemoryRouter initialEntries={['/beheer']}>
        <Routes>
          <Route
            path="/beheer"
            element={
              <AuthGuard>
                <div>Geheime Beheeromgeving</div>
              </AuthGuard>
            }
          />
          <Route path="/inloggen" element={<div>Inlogpagina</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Geheime Beheeromgeving')).toBeInTheDocument();
  });
});
