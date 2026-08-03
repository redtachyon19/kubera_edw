import { org } from '../config/dashboards';

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <span className="footer__mark">
          {org.short} — {org.product}
        </span>
        <span className="footer__disclaimer">{org.tagline}</span>
      </div>
    </footer>
  );
}
