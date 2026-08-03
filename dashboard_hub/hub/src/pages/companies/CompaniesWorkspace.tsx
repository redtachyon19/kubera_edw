import EmbeddedDashboard from '../../components/EmbeddedDashboard';
import { isNative } from '../../config/dashboards';
import type { Dashboard, Section } from '../../config/dashboards';
import WorkspaceShell from '../WorkspaceShell';
import Companies from './Companies';

/**
 * The Companies desk: one issuer at a time, from the market's view and the
 * warehouse's.
 *
 * The Explorer is live and browsable; the two Streamlit sheets beside it are
 * cross-sectional reports over the whole book. Keeping them on one desk is the
 * point — you arrive at a name from the grid, then read the same name in the
 * book-wide context the sheets give it.
 */
export default function CompaniesWorkspace({ section }: { section: Section }) {
  function body(dashboard: Dashboard | undefined) {
    if (!dashboard) return <p className="ws__empty">Nothing is running on this desk yet.</p>;
    if (isNative(dashboard)) return <Companies />;
    return <EmbeddedDashboard dashboard={dashboard} />;
  }

  return <WorkspaceShell section={section}>{body}</WorkspaceShell>;
}
