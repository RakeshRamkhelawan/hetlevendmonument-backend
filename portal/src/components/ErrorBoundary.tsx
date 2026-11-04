import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

export interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public state: ErrorBoundaryState = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('ErrorBoundary verving een onafgevangen fout:', error, errorInfo);
  }

  public handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  public handleReload = (): void => {
    window.location.reload();
  };

  public render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          role="alert"
          aria-live="assertive"
          className="min-h-screen flex flex-col items-center justify-center bg-[#FDFBF7] text-stone-800 px-4"
        >
          <div className="max-w-md w-full bg-white border border-stone-200 rounded-2xl p-8 shadow-sm text-center">
            <div
              className="w-14 h-14 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center mx-auto mb-5"
              aria-hidden="true"
            >
              <AlertTriangle className="w-7 h-7" />
            </div>
            <h1 className="font-serif font-bold text-2xl text-stone-900 mb-3">
              Er is iets misgegaan
            </h1>
            <p className="text-sm text-stone-600 leading-relaxed mb-6">
              Er is een onverwachte fout opgetreden bij het laden van dit onderdeel. Onze excuses voor het ongemak.
            </p>
            {this.state.error?.message && (
              <div className="bg-stone-50 border border-stone-200 rounded-lg p-3 text-xs text-stone-500 font-mono mb-6 text-left break-all">
                {this.state.error.message}
              </div>
            )}
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button
                type="button"
                onClick={this.handleReset}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-amber-800 text-white text-sm font-semibold hover:bg-amber-700 transition-colors shadow-xs"
              >
                <RefreshCw className="w-4 h-4" aria-hidden="true" />
                Opnieuw proberen
              </button>
              <a
                href="/"
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-stone-100 text-stone-700 text-sm font-semibold hover:bg-stone-200 transition-colors"
              >
                <Home className="w-4 h-4" aria-hidden="true" />
                Naar startpagina
              </a>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
