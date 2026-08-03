import type { CSSProperties, MouseEvent } from 'react';
import { useEffect, useRef } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';

import { getSectionBySlug, isWorkspace, org, sectionRoute, sections } from '../config/dashboards';
import ThemeToggle from './ThemeToggle';
import './TopBar.css';

/** How long navigation waits, so a double-click can cancel it. */
const DOUBLE_MS = 320;

export default function TopBar({ onBrandDouble }: { onBrandDouble?: () => void }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const pending = useRef<number | null>(null);

  // A workspace desk puts its own live strip in this slot, so the engraved
  // strapline stands down there rather than stacking two bands of chrome.
  const desk = getSectionBySlug(pathname.match(/^\/s\/([^/]+)/)?.[1]);
  const showDescriptor = !(desk && isWorkspace(desk));

  useEffect(
    () => () => {
      if (pending.current) window.clearTimeout(pending.current);
    },
    [],
  );

  /**
   * One click goes home, two brings out the card.
   *
   * The card is opened from the browser's own `dblclick`, which uses the
   * platform's double-click threshold rather than a number picked here — a
   * hand-rolled timer is stricter than the OS and drops slower double-clicks.
   * The timer that remains does one job: hold navigation back long enough that
   * a double-click does not go home on its first half. A modified click — new
   * tab, new window — is left entirely to the browser.
   */
  function onBrandClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();

    if (pending.current) window.clearTimeout(pending.current);
    pending.current = window.setTimeout(() => {
      pending.current = null;
      navigate('/');
    }, DOUBLE_MS);
  }

  function onBrandDoubleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    if (pending.current) {
      window.clearTimeout(pending.current);
      pending.current = null;
    }
    onBrandDouble?.();
  }

  return (
    <header className="topbar">
      <div className="topbar__inner">
        <Link
          to="/"
          className="topbar__brand"
          aria-label={`${org.short} home — double-click for contact`}
          onClick={onBrandClick}
          onDoubleClick={onBrandDoubleClick}
        >
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
      {showDescriptor && <div className="topbar__descriptor">{org.descriptor}</div>}
    </header>
  );
}
