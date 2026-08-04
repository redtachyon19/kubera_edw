import { useRef } from 'react';

import StockExplorer from '../stock/StockExplorer';
import Sectors from './Sectors';
import './Explorer.css';

interface Props {
  symbols: string[];
  onSymbolsChange: (symbols: string[]) => void;
}

/**
 * Search and sweep, stacked on one page.
 *
 * The chart is on top because it is what the desk is for; the sector sweep sits
 * underneath it as the way you find the next thing to put in it. Both are on
 * screen at once deliberately — behind a toggle, picking a sector meant losing
 * sight of the chart you were picking it for. Sending an industry up to the
 * chart now moves the page, not the view.
 */
export default function Explorer({ symbols, onSymbolsChange }: Props) {
  const top = useRef<HTMLDivElement>(null);

  function chart(picked: string[]) {
    if (picked.length === 0) return;
    onSymbolsChange(picked);
    top.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <div className="explorer">
      <div ref={top} className="explorer__chart">
        <StockExplorer symbols={symbols} onSymbolsChange={onSymbolsChange} />
      </div>

      <section className="explorer__sectors">
        <h2 className="explorer__rule">
          <span>Sectors</span>
        </h2>
        <Sectors onCompare={chart} />
      </section>
    </div>
  );
}
