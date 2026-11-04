import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from '../components/ErrorBoundary';

const Bomb: React.FC<{ shouldThrow?: boolean }> = ({ shouldThrow = true }) => {
  if (shouldThrow) {
    throw new Error('Test explosie in component');
  }
  return <div>Normale Veilige Content</div>;
};

describe('ErrorBoundary', () => {
  it('rendert children wanneer er geen fout optreedt', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Normale Veilige Content')).toBeInTheDocument();
  });

  it('vangt een fout op en toont de vriendelijke Nederlandse fallback UI', () => {
    // Onderdruk console.error voor de verwachte gegooide fout
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Er is iets misgegaan')).toBeInTheDocument();
    expect(screen.getByText('Test explosie in component')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /opnieuw proberen/i })).toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it('ondersteunt een aangepaste fallback prop', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary fallback={<div data-testid="custom-fallback">Aangepast foutscherm</div>}>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('custom-fallback')).toBeInTheDocument();
    expect(screen.getByText('Aangepast foutscherm')).toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it('herstelt naar normale weergave na klikken op opnieuw proberen', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    let shouldThrow = true;
    const StatefulBomb = () => {
      if (shouldThrow) {
        throw new Error('Eerste poging faalt');
      }
      return <div>Hersteld na fout!</div>;
    };

    render(
      <ErrorBoundary>
        <StatefulBomb />
      </ErrorBoundary>
    );

    expect(screen.getByText('Er is iets misgegaan')).toBeInTheDocument();

    // Fix condition and click reset
    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: /opnieuw proberen/i }));

    expect(screen.getByText('Hersteld na fout!')).toBeInTheDocument();

    consoleSpy.mockRestore();
  });
});
