import { Link } from 'react-router-dom';

import './NotFound.css';

export default function NotFound() {
  return (
    <div className="notfound">
      <p className="eyebrow">Error 404</p>
      <h1 className="notfound__title">Page not found</h1>
      <div className="notfound__hairline" />
      <p className="notfound__body">
        That address is not part of this hub. Desks are at <code>/s/&lt;desk&gt;</code> and
        dashboards at <code>/s/&lt;desk&gt;/&lt;dashboard&gt;</code>.
      </p>
      <Link to="/" className="notfound__back">
        &larr; Index
      </Link>
    </div>
  );
}
