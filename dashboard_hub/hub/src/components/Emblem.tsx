import { useState } from 'react';

import './Emblem.css';

interface Props {
  /** A company ticker, or an ISO3 country code. */
  id: string;
  kind: 'logo' | 'flag';
  /** Used for the lettermark fallback and the alt text. */
  name: string;
  size?: number;
}

/**
 * A company mark or a country flag, drawn in grey until you look at it.
 *
 * Colour is the loudest signal on this page and it is already spoken for —
 * green for a gain, red for a loss. Three hundred full-colour brand marks in a
 * grid would shout over every number on it. So they sit desaturated by default
 * and come up to full colour under the cursor, which makes the mark a thing you
 * reach for rather than a thing you fight past.
 *
 * The bytes come from `/api/market/logo` and `/api/market/flag`, which cache to
 * disk server-side; a mark the services have nothing for falls back to a
 * lettermark rather than a broken image.
 */
export default function Emblem({ id, kind, name, size = 22 }: Props) {
  const [failed, setFailed] = useState(false);

  const initials = name
    .replace(/[^A-Za-z0-9 ]/g, ' ')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase();

  if (failed || !id) {
    return (
      <span
        className="emblem emblem--letters"
        style={{ width: size, height: size, fontSize: size * 0.42 }}
        aria-hidden="true"
      >
        {initials || '—'}
      </span>
    );
  }

  const query = kind === 'logo' ? `symbol=${encodeURIComponent(id)}` : `iso3=${encodeURIComponent(id)}`;

  return (
    <img
      className={`emblem emblem--${kind}`}
      src={`/api/market/${kind}?${query}`}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      style={{ width: size, height: size }}
      onError={() => setFailed(true)}
    />
  );
}
