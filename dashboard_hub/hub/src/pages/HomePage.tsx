import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';

import { countLive, org, sectionRoute, sections, totals } from '../config/dashboards';
import './HomePage.css';
import Ruled from '../components/Ruled';

export default function HomePage() {
  return (
    <div className="home">
      <section className="home__masthead">
        <div className="home__masthead-inner">
          <p className="eyebrow home__eyebrow">{org.name}</p>
          <h1 className="home__title">{org.product}</h1>
          <div className="home__hairline" />
          <p className="home__standfirst">
            An investment research terminal: markets and macro read live, filings read from a
            governed warehouse. Every view runs as its own service against the same marts, so a
            figure means the same thing whichever page you read it on.
          </p>
          <dl className="home__facts">
            <div>
              <dt>Dashboards</dt>
              <dd className="num">{totals.dashboards}</dd>
            </div>
            <div>
              <dt>In service</dt>
              <dd className="num">{totals.live}</dd>
            </div>
            <div>
              <dt>Desks</dt>
              <dd className="num">{sections.length}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="home__index" id="sections">
        <Ruled below={40}>Index</Ruled>

        <div className="home__grid">
          {sections.map((section) => (
            <Link
              key={section.slug}
              to={sectionRoute(section)}
              className="desk-card"
              style={{ '--accent': `var(--${section.metal})` } as CSSProperties}
            >
              <span className="desk-card__accent" aria-hidden="true" />
              <span className="desk-card__no num">
                {String(sections.indexOf(section) + 1).padStart(2, '0')}
              </span>
              <h2 className="desk-card__name">{section.name}</h2>
              <p className="desk-card__tagline">{section.tagline}</p>
              <span className="desk-card__meta">
                <span className="num">{countLive(section)}</span> of{' '}
                <span className="num">{section.dashboards.length}</span> in service
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
