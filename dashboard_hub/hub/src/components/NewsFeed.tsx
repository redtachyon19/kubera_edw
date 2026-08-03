import { useEffect, useState } from 'react';

import { fetchNews, timeAgo } from './newsApi';
import type { NewsSource, Story } from './newsApi';
import './NewsFeed.css';

/**
 * Recent coverage for a sector or a single company.
 *
 * Everything here is third-party content: headlines are rendered as text (React
 * escapes them), links open in a new tab with `noopener`, and thumbnails are
 * fetched with `no-referrer` so browsing the hub does not leak back to the image
 * host. Nothing in an article is read or acted on — it is a reading list.
 */
export default function NewsFeed({ source, empty }: { source: NewsSource; empty: string }) {
  const [stories, setStories] = useState<Story[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading');
  const [broken, setBroken] = useState<Record<string, boolean>>({});

  const key = source.symbol ?? source.slug;

  useEffect(() => {
    const controller = new AbortController();
    setState('loading');
    fetchNews(source, controller.signal)
      .then((items) => {
        setStories(items);
        setState('ready');
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setState('failed');
      });
    return () => controller.abort();
    // The source is an object literal at every call site; its identity is the key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (state === 'loading') return <p className="news__note">Loading coverage…</p>;
  if (state === 'failed') return <p className="news__note">Coverage unavailable right now.</p>;
  if (stories.length === 0) return <p className="news__note">{empty}</p>;

  return (
    <div className="news">
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
    </div>
  );
}
