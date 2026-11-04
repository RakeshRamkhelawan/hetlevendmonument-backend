import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FormattedText, deelOp } from '../components/FormattedText';

describe('FormattedText: eenvoudige opmaak voor verhalen en lesmateriaal', () => {
  it('maakt koppen, opsommingen, genummerde lijsten en alinea\'s', () => {
    const blokken = deelOp('## Kop\nEerste zin.\n\n- een\n- twee\n\n1. alfa\n2. beta');
    expect(blokken.map((b) => b.soort)).toEqual(['kop', 'alinea', 'lijst', 'nummers']);
  });

  it('laat een gewoon verhaal zonder opmaaktekens als alinea\'s staan', () => {
    const blokken = deelOp('Lieve Nani,\n\nIk ben goed aangekomen.\n\nJe kleinzoon,\nRavi');
    expect(blokken.every((b) => b.soort === 'alinea')).toBe(true);
    expect(blokken).toHaveLength(3);
  });

  it('maakt alleen https-adressen klikbaar, zonder de punt erachter', () => {
    render(<FormattedText text={'Zie https://www.cbs.nl/nl-nl/artikel. Of javascript:alert(1)'} />);
    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe('https://www.cbs.nl/nl-nl/artikel');
    expect(link.getAttribute('rel')).toContain('noopener');
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });
});
