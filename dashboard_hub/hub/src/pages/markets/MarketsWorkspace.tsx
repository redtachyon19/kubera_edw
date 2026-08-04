import { useState } from 'react';

import EmbeddedDashboard from '../../components/EmbeddedDashboard';
import { isNative } from '../../config/dashboards';
import type { Dashboard, Section } from '../../config/dashboards';
import WorkspaceShell from '../WorkspaceShell';
import Explorer from './Explorer';
import World from './World';

/**
 * The Markets desk: search, sweep, compare, and the world behind it.
 *
 * The basket lives here rather than inside the Explorer so it survives a move to
 * the World desk and back — that persistence is the reason these views share a
 * surface instead of being separate destinations.
 */
export default function MarketsWorkspace({ section }: { section: Section }) {
  const [basket, setBasket] = useState<string[]>(['AAPL', 'MSFT']);

  function body(dashboard: Dashboard | undefined) {
    if (!dashboard) return <p className="ws__empty">Nothing is running on this desk yet.</p>;

    if (dashboard.id === 'world') return <World />;
    if (isNative(dashboard)) {
      return <Explorer symbols={basket} onSymbolsChange={setBasket} />;
    }
    return <EmbeddedDashboard dashboard={dashboard} />;
  }

  return <WorkspaceShell section={section}>{body}</WorkspaceShell>;
}
