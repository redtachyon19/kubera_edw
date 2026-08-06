import type { CSSProperties, ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { Dashboard, Section } from '../config/dashboards';
import { useUrlState } from '../hooks/useUrlState';
import Ticker from './markets/Ticker';
import './Workspace.css';

export interface WorkspaceShellProps {
  section: Section;
  /** Draws the active view. `goTo` switches tab, for a hand-off between views. */
  children: (dashboard: Dashboard | undefined, goTo: (id: string) => void) => ReactNode;
}

/**
 * The chrome every live desk shares: tape, masthead, tabs, stage.
 *
 * A report desk is an index of sheets you open, read and leave, so a list is
 * right for it. A live desk is one workflow across several views — search here,
 * open there, compare back — so its views switch in place and keep their state
 * instead of being separate destinations. That difference is declared per desk
 * in `dashboards.json` (`layout: "workspace"`); this component is what it means.
 *
 * Only the chrome lives here. What each view *is*, and any state shared between
 * them, belongs to the desk — Markets hands a basket from Sectors to the
 * Explorer, Companies hands a symbol from the grid to the detail page, and
 * neither is the shell's business.
 */
export default function WorkspaceShell({ section, children }: WorkspaceShellProps) {
  const live = section.dashboards.filter((entry) => entry.status === 'stub');
  // Which view is up is part of what you are looking at, so it goes in the
  // address — a desk's four lenses are otherwise one URL between them.
  const [activeId, setActiveId] = useUrlState('view', live[0]?.id ?? '', {
    valid: live.map((entry) => entry.id),
    push: true,
  });
  const active = live.find((entry) => entry.id === activeId) ?? live[0];

  return (
    <div className="ws" style={{ '--accent': `var(--${section.metal})` } as CSSProperties}>
      {section.tape && section.tape.length > 0 && <Ticker entries={section.tape} />}

      <div className="ws__inner">
        <header className="ws__header">
          <div>
            <p className="eyebrow">Desk</p>
            <h1 className="ws__title">{section.name}</h1>
          </div>
          <p className="ws__tagline">{section.tagline}</p>
        </header>

        <nav className="ws__tabs" aria-label={`${section.name} views`}>
          {live.map((dashboard) => (
            <button
              key={dashboard.id}
              type="button"
              className={dashboard.id === active?.id ? 'ws__tab is-on' : 'ws__tab'}
              onClick={() => setActiveId(dashboard.id)}
              title={dashboard.blurb}
            >
              {dashboard.title}
            </button>
          ))}
          {active && (
            <Link className="ws__full" to={`/s/${section.slug}/${active.id}`}>
              Open on its own &#8599;
            </Link>
          )}
        </nav>

        <p className="ws__blurb">{active?.blurb}</p>

        <div className="ws__stage">{children(active, setActiveId)}</div>
      </div>
    </div>
  );
}
