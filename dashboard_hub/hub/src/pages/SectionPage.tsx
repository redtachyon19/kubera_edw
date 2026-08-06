import type { CSSProperties, JSX } from 'react';
import { Link, useParams } from 'react-router-dom';

import { dashboardRoute, getSectionBySlug, isWorkspace } from '../config/dashboards';
import type { Section } from '../config/dashboards';
import CompaniesWorkspace from './companies/CompaniesWorkspace';
import MarketsWorkspace from './markets/MarketsWorkspace';
import WorldWorkspace from './markets/WorldWorkspace';
import NotFound from './NotFound';
import './SectionPage.css';
import Ruled from '../components/Ruled';

/** Which shell a live desk uses. A desk with no entry falls back to the index. */
const WORKSPACES: Record<string, (section: Section) => JSX.Element> = {
  markets: (section) => <MarketsWorkspace section={section} />,
  companies: (section) => <CompaniesWorkspace section={section} />,
  world: (section) => <WorldWorkspace section={section} />,
};

export default function SectionPage() {
  const { slug } = useParams<{ slug: string }>();
  const section = getSectionBySlug(slug);

  if (!section) {
    return (
      <NotFound title="Desk not found">
        There is no desk called &ldquo;{slug}&rdquo;.
      </NotFound>
    );
  }

  // Live desks get a workspace; report desks stay an index. The rule lives in
  // the registry so a desk's shape is declared, not special-cased here.
  if (isWorkspace(section)) {
    const workspace = WORKSPACES[section.slug];
    if (workspace) return workspace(section);
  }

  return (
    <div className="section" style={{ '--accent': `var(--${section.metal})` } as CSSProperties}>
      <Link to="/" className="section__back">
        &larr; Index
      </Link>

      <header className="section__header">
        <p className="eyebrow">Desk</p>
        <h1 className="section__name">{section.name}</h1>
        <div className="section__hairline" />
        <p className="section__tagline">{section.description}</p>
      </header>

      <section className="section__list" aria-label="Dashboards">
        <Ruled below={0}>Dashboards</Ruled>

        {section.dashboards.map((dashboard, index) => (
          <Link
            className={`sheet${dashboard.status === 'planned' ? ' sheet--planned' : ''}`}
            key={dashboard.id}
            to={dashboardRoute(section, dashboard)}
          >
            <div className="sheet__plate" aria-hidden="true">
              {/* The number is always drawn and the thumbnail sits over it, so a
                  dashboard with no rendered chart — or one whose PNG has not
                  been generated yet — degrades to the plate rather than a gap. */}
              <span className="sheet__plate-no num">{String(index + 1).padStart(2, '0')}</span>
              <img
                className="sheet__shot"
                src={`/thumbnails/${dashboard.id}.png`}
                alt=""
                loading="lazy"
                decoding="async"
                onError={(event) => {
                  event.currentTarget.style.display = 'none';
                }}
              />
            </div>

            <div className="sheet__body">
              <span className="sheet__status">
                {dashboard.status === 'stub' ? 'In service' : 'Not commissioned'}
              </span>
              <h2 className="sheet__title">{dashboard.title}</h2>
              <p className="sheet__desc">{dashboard.blurb}</p>
              <span className="sheet__cta">Open &rarr;</span>
            </div>
          </Link>
        ))}
      </section>
    </div>
  );
}
