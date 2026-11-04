import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';

interface AuthGuardProps {
  children: React.ReactNode;
}

export const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const location = useLocation();
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;

  if (!token) {
    const redirectParam = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/inloggen?redirect=${redirectParam}`} replace />;
  }

  return <>{children}</>;
};
