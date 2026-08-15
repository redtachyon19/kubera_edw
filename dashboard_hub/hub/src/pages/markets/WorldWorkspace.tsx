import EmbeddedDashboard from '../../components/EmbeddedDashboard';
import { isNative } from '../../config/dashboards';
import type { Dashboard, Section } from '../../config/dashboards';
import WorkspaceShell from '../WorkspaceShell';
import World from './World';
import type { Lens } from './World';

/** Desk view id -> the lens World draws. */
const LENS: Record<string, Lens> = {
  governments: 'governments',
  trade: 'trade',
  'world-sectors': 'sectors',
  energy: 'energy',
  weather: 'weather',
};

/**
 * The World desk: economies rather than securities.
 *
 * Its four lenses are the desk's own views, not a control nested inside a single
 * dashboard. That was the shape while World lived under Markets, and it meant
 * three of the four were invisible until you found the toggle — a segmented
 * control doing the job of navigation. Promoted to a desk, the tab bar carries
 * them, and the globe keeps its rotation across a switch because the component
 * never unmounts.
 */
export default function WorldWorkspace({ section }: { section: Section }) {
  function body(dashboard: Dashboard | undefined) {
    if (!dashboard) return <p className="ws__empty">Nothing is running on this desk yet.</p>;
    if (isNative(dashboard)) return <World lens={LENS[dashboard.id] ?? 'governments'} />;
    return <EmbeddedDashboard dashboard={dashboard} />;
  }

  return <WorkspaceShell section={section}>{body}</WorkspaceShell>;
}
