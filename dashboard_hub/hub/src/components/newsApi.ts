/** The hub's news endpoint, which serves a sector or a single listing. */

export interface Story {
  id: string;
  title: string;
  summary: string;
  url: string;
  publisher: string;
  published: string | null;
  thumbnail: string | null;
  /** Which listing the story was filed against. */
  ticker: string;
}

/** A sector takes the union across its largest names; a company just its own. */
export type NewsSource = { slug: string; symbol?: never } | { symbol: string; slug?: never };

export function fetchNews(source: NewsSource, signal?: AbortSignal): Promise<Story[]> {
  const query = source.symbol
    ? `symbol=${encodeURIComponent(source.symbol)}`
    : `slug=${encodeURIComponent(source.slug ?? '')}`;
  return fetch(`/api/market/news?${query}`, { signal })
    .then(async (response) => {
      const body = await response.json();
      if (!response.ok || body.error) {
        throw new Error(body.error ?? `API returned ${response.status}`);
      }
      return body.stories as Story[];
    });
}

/** "3h ago" reads faster than a timestamp on a feed. */
export function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return '';
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${Math.max(1, mins)}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days < 30 ? `${days}d ago` : `${Math.round(days / 30)}mo ago`;
}
