import { useState } from 'react';

import EmbeddedDashboard from '../../components/EmbeddedDashboard';
import { isNative } from '../../config/dashboards';
import type { Dashboard, Section } from '../../config/dashboards';
import StockExplorer from '../stock/StockExplorer';
import WorkspaceShell from '../WorkspaceShell';
import Sectors from './Sectors';

/**
 * The Markets desk: search, sweep, anchor, compare.
 *
 * The basket lives here rather than inside the Explorer so Sectors can load one
 * and hand the reader straight to the chart — that hand-off is the reason these
 * three views share a surface instead of being three destinations.
 */
export default function MarketsWorkspace({ section }: { section: Section }) {
  const [basket, setBasket] = useState<string[]>(['AAPL', 'MSFT']);

  function body(dashboard: Dashboard | undefined, goTo: (id: string) => void) {
    if (!dashboard) return <p className="ws__empty">Nothing is running on this desk yet.</p>;

    function chart(symbols: string[]) {
      if (symbols.length === 0) return;
      setBasket(symbols);
      goTo('stock-explorer');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    if (dashboard.id === 'sectors') return <Sectors onCompare={chart} />;
    if (isNative(dashboard)) {
      return <StockExplorer symbols={basket} onSymbolsChange={setBasket} />;
    }
    return <EmbeddedDashboard dashboard={dashboard} />;
  }

  return <WorkspaceShell section={section}>{body}</WorkspaceShell>;
}
