import type { CSSProperties } from 'react';
import { Link, useParams } from 'react-router-dom';

import { embedPathFor, getSectionBySlug, sectionRoute } from '../config/dashboards';
import { useThemeMode } from '../ThemeContext';
import './DashboardPage.css';

export default function DashboardPage() {
  const { slug, dashboardId } = useParams<{ slug: string; dashboardId: string }>();
  const { mode } = useThemeMode();
  const section = getSectionBySlug(slug);
  const dashboard = section?.dashboards.find((entry) => entry.id === dashboardId);

  if (!section || !dashboard) {
    return (
      <div className="dash dash--missing">
        <h1>Dashboard not found</h1>
        <p>There is nothing at this address.</p>
        <Link to={section ? sectionRoute(section) : '/'} className="dash__back">
          &larr; Back
        </Link>
      </div>
    );
  }

  const embedPath = embedPathFor(dashboard);

  return (
    <div className="dash" style={{ '--accent': `var(--${section.metal})` } as CSSProperties}>
      <Link to={sectionRoute(section)} className="dash__back">
        &larr; {section.name}
      </Link>

      <header className="dash__header">
        <div>
          <p className="eyebrow">{section.name}</p>
          <h1 className="dash__title">{dashboard.title}</h1>
          <p className="dash__desc">{dashboard.blurb}</p>
        </div>
        {embedPath && (
          <a
            className="dash__open"
            href={`${embedPath}?theme=${mode}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open full view &#8599;
          </a>
        )}
      </header>

      {embedPath ? (
        // `embed=true` strips Streamlit's own chrome; `theme` makes the dashboard
        // render on the same stock as the hub. The key remounts the frame on a
        // theme change so the embedded page re-renders rather than going stale.
        <iframe
          key={mode}
          className="dash__frame"
          src={`${embedPath}?embed=true&theme=${mode}`}
          title={dashboard.title}
        />
      ) : (
        <div className="dash__pending">
          <p className="dash__pending-lead">Not commissioned</p>
          <p>
            No service is running behind this page yet. To commission it: create{' '}
            <code>dashboard_hub/dashboards/{dashboard.module}/app.py</code>, then in{' '}
            <code>dashboard_hub/dashboards.json</code> set this dashboard&rsquo;s{' '}
            <code>status</code> to <code>"stub"</code> and give it a free <code>port</code>.
          </p>
          {dashboard.planned.length > 0 && (
            <>
              <p className="eyebrow dash__pending-label">Scope</p>
              <ul className="dash__pending-list">
                {dashboard.planned.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
