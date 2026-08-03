import { embedPathFor } from '../config/dashboards';
import type { Dashboard } from '../config/dashboards';
import { useThemeMode } from '../ThemeContext';

/**
 * A Streamlit dashboard inside a workspace tab.
 *
 * `embed=true` strips Streamlit's own chrome and `theme` puts it on the hub's
 * stock; the key remounts the frame on a theme change, because the embedded page
 * reads the theme once at load and would otherwise go stale against the shell.
 */
export default function EmbeddedDashboard({ dashboard }: { dashboard: Dashboard }) {
  const { mode } = useThemeMode();
  const embed = embedPathFor(dashboard);

  if (!embed) return <p className="ws__empty">This view has not been commissioned yet.</p>;

  return (
    <iframe
      key={`${dashboard.id}-${mode}`}
      className="ws__frame"
      src={`${embed}?embed=true&theme=${mode}`}
      title={dashboard.title}
    />
  );
}
