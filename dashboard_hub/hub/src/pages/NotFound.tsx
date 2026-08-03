import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import './NotFound.css';

/**
 * A page that isn't there, and the one screen allowed to be lurid about it.
 *
 * Blood floods the whole view from the top, runs ahead of itself in drips of
 * different lengths, and the copy sits on it in bone. Everything else in this
 * terminal is restraint and hairlines; a 404 is the one place where nothing is
 * at stake, so it gets the joke the rest of the house style keeps a straight
 * face about.
 */
export interface NotFoundProps {
  title?: string;
  children?: ReactNode;
  /** Where "Index" points; a desk sends the reader back to itself. */
  backTo?: string;
  backLabel?: string;
}

export default function NotFound({ title, children, backTo, backLabel }: NotFoundProps = {}) {
  return (
    <div className="notfound">
      <svg
        className="notfound__blood"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {/* The drips run ahead, so the flood arrives to meet them. */}
        <g className="notfound__drips">
          <rect x="7" y="0" width="1.1" height="46" rx="0.55" />
          <rect x="19" y="0" width="1.8" height="63" rx="0.9" />
          <rect x="31" y="0" width="1.2" height="52" rx="0.6" />
          <rect x="44" y="0" width="2.1" height="74" rx="1.05" />
          <rect x="57" y="0" width="1.3" height="57" rx="0.65" />
          <rect x="69" y="0" width="1.9" height="69" rx="0.95" />
          <rect x="81" y="0" width="1.1" height="49" rx="0.55" />
          <rect x="92" y="0" width="2.3" height="78" rx="1.15" />
        </g>

        {/* The flood itself, with a leading edge that is not a straight line. */}
        <path
          className="notfound__flood"
          d="M0,-104 H100 V0 C94,6 88,-1 82,4 C75,10 69,2 62,7
             C55,12 49,3 42,8 C35,13 28,4 21,9 C15,13 8,5 0,9 Z"
        />
      </svg>

      <div className="notfound__inner">
        <p className="eyebrow notfound__eyebrow">Error 404</p>
        <h1 className="notfound__title">{title ?? 'Page not found'}</h1>
        <div className="notfound__hairline" />
        <p className="notfound__body">
          {children ?? (
            <>
              That address is not part of this terminal. Desks are at <code>/s/&lt;desk&gt;</code>{' '}
              and dashboards at <code>/s/&lt;desk&gt;/&lt;dashboard&gt;</code>.
            </>
          )}
        </p>
        <Link to={backTo ?? '/'} className="notfound__back">
          &larr; {backLabel ?? 'Index'}
        </Link>
      </div>
    </div>
  );
}
