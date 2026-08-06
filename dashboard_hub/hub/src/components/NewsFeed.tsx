import { useState } from 'react';

import { fetchNews, timeAgo } from './newsApi';
import type { NewsSource, Story } from './newsApi';
import './NewsFeed.css';
import Ruled from './Ruled';
import { useFetch } from '../hooks/useFetch';

/**
 * Recent coverage for a sector or a single company, chrome included.
 *
 * The heading and the hairline under it are part of this component rather than
 * something each page writes for itself. They were duplicated at both call
 * sites, and Companies borrowed `sectors__news-rule` — a class belonging to
 * another page's stylesheet — to draw the line. That rule carries a top margin
 * tuned for a container with no gap, so inside the Companies section (a flex
 * column with an 18px gap) the two stacked: 30px above the line, 18px below,
 * the line drifting away from the label it belongs to. Owning the block here
 * means the spacing is defined once, beside the markup it applies to.
 *
 * Everything here is third-party content: headlines are rendered as text (React
 * escapes them), links open in a new tab with `noopener`, and thumbnails are
 * fetched with `no-referrer` so browsing the hub does not leak back to the image
 * host. Nothing in an article is read or acted on — it is a reading list.
 */
export default function NewsFeed({
  source,
  empty,
  title = 'Coverage',
  label,
}: {
  source: NewsSource;
  empty: string;
  /** The eyebrow above the hairline. */
  title?: string;
  /** Accessible name for the section, e.g. "Company coverage". */
  label?: string;
}) {
  const [broken, setBroken] = useState<Record<string, boolean>>({});

  // The source is an object literal at every call site, so its identity would
  // change every render; the ticker or slug inside it is the real key.
  const key = source.symbol ?? source.slug;
  const feed = useFetch<Story[]>((signal) => fetchNews(source, signal), [key]);
  const stories = feed.data ?? [];

  function body() {
    if (feed.loading) return <p className="news__note">Loading coverage…</p>;
    if (feed.error) return <p className="news__note">Coverage unavailable right now.</p>;
    if (stories.length === 0) return <p className="news__note">{empty}</p>;
    return <div className="news">{items}</div>;
  }

  const items = (
    <>
      {stories.map((story) => (
        <a
          key={story.id}
          className="news__item"
          href={story.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          <div className="news__thumb">
            {story.thumbnail && !broken[story.id] ? (
              <img
                src={story.thumbnail}
                alt=""
                loading="lazy"
                referrerPolicy="no-referrer"
                onError={() => setBroken((b) => ({ ...b, [story.id]: true }))}
              />
            ) : (
              <span className="news__thumb-fallback num">{story.ticker}</span>
            )}
          </div>
          <div className="news__body">
            <span className="news__meta">
              <b className="num">{story.ticker}</b>
              {story.publisher && <span>{story.publisher}</span>}
              <time>{timeAgo(story.published)}</time>
            </span>
            <h4 className="news__title">{story.title}</h4>
            {story.summary && <p className="news__summary">{story.summary}</p>}
          </div>
        </a>
      ))}
    </>
  );

  return (
    <section className="news-block" aria-label={label ?? title}>
      <Ruled>{title}</Ruled>
      {body()}
    </section>
  );
}
