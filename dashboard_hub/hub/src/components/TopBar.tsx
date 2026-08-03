import type { CSSProperties } from 'react';
import { Link, NavLink } from 'react-router-dom';

import { org, sectionRoute, sections } from '../config/dashboards';
import ThemeToggle from './ThemeToggle';
import './TopBar.css';

export default function TopBar() {
  return (
    <header className="topbar">
      <div className="topbar__inner">
        <Link to="/" className="topbar__brand" aria-label={`${org.short} home`}>
          <span className="topbar__mark">{org.short}</span>
          <span className="topbar__product">{org.product}</span>
        </Link>

        <nav className="topbar__nav" aria-label="Sections">
          {sections.map((section) => (
            <NavLink
              key={section.slug}
              to={sectionRoute(section)}
              style={{ '--accent': `var(--${section.metal})` } as CSSProperties}
              className={({ isActive }) =>
                isActive ? 'topbar__link topbar__link--active' : 'topbar__link'
              }
              title={section.tagline}
            >
              {section.name}
            </NavLink>
          ))}
        </nav>

        <ThemeToggle />
      </div>
      <div className="topbar__descriptor">{org.descriptor}</div>
    </header>
  );
}
