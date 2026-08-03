import type { CSSProperties } from 'react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { embedPathFor, isNative } from '../../config/dashboards';
import type { Dashboard, Section } from '../../config/dashboards';
import { useThemeMode } from '../../ThemeContext';
import StockExplorer from '../stock/StockExplorer';
import Ticker from './Ticker';
import './MarketsWorkspace.css';

/**
 * The Markets desk is a workspace, not an index.
 *
 * The other desks hold point-in-time reports you open, read and leave, so a list
 * of sheets is right for them. This one is live and stateful — search, sweep,
 * anchor, compare — and the three views are one workflow rather than three
 * reports, so they share a surface and switch by tab instead of by navigation.
 *
 * The shell above (top bar, theme, routing) is untouched; only the desk's own
 * body differs. Each view also keeps its own route, so it stays deep-linkable.
 */
export default function MarketsWorkspace({ section }: { section: Section }) {
  const { mode } = useThemeMode();
  const live = section.dashboards.filter((entry) => entry.status === 'stub');
  const [activeId, setActiveId] = useState(live[0]?.id ?? '');
  const active = live.find((entry) => entry.id === activeId) ?? live[0];

  function body(dashboard: Dashboard | undefined) {
    if (!dashboard) return <p className="ws__empty">Nothing is running on this desk yet.</p>;
    if (isNative(dashboard)) return <StockExplorer />;
    const embed = embedPathFor(dashboard);
    if (!embed) {
      return <p className="ws__empty">This view has not been commissioned yet.</p>;
    }
    return (
      <iframe
        key={`${dashboard.id}-${mode}`}
        className="ws__frame"
        src={`${embed}?embed=true&theme=${mode}`}
        title={dashboard.title}
      />
    );
  }

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

        <nav className="ws__tabs" aria-label="Markets views">
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

        <div className="ws__stage">{body(active)}</div>
      </div>
    </div>
  );
}
