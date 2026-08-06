import EmbeddedDashboard from '../../components/EmbeddedDashboard';
import { isNative } from '../../config/dashboards';
import type { Dashboard, Section } from '../../config/dashboards';
import { useUrlList } from '../../hooks/useUrlState';
import WorkspaceShell from '../WorkspaceShell';
import Explorer from './Explorer';

const DEFAULT_BASKET = ['AAPL', 'MSFT'];

/**
 * The Markets desk: securities. Search one, chart it, sweep its sector.
 *
 * The basket lives here rather than inside the Explorer so it survives being
 * navigated away from and back — and in the query string rather than in state,
 * so the desk you are looking at is an address you can send to somebody.
 */
export default function MarketsWorkspace({ section }: { section: Section }) {
  const [basket, setBasket] = useUrlList('symbols', DEFAULT_BASKET);

  function body(dashboard: Dashboard | undefined) {
    if (!dashboard) return <p className="ws__empty">Nothing is running on this desk yet.</p>;

    if (isNative(dashboard)) {
      return <Explorer symbols={basket} onSymbolsChange={setBasket} />;
    }
    return <EmbeddedDashboard dashboard={dashboard} />;
  }

  return <WorkspaceShell section={section}>{body}</WorkspaceShell>;
}
