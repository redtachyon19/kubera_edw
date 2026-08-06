import Emblem from '../../components/Emblem';
import TimeChart from '../../components/TimeChart';
import { useFetch } from '../../hooks/useFetch';
import { fetchCountry, index, move, rate, tone, usd } from './worldApi';
import type { CountryDetail } from './worldApi';
import './CountryPanel.css';

/**
 * Everything about one country, on one surface.
 *
 * Four readings, in the order they answer each other. **Purchasing power** first,
 * because it reframes every other number on the page: a market up 20% in a
 * currency that lost 30% against gold did not make anyone richer. Then **what the
 * country sells and buys**, then **who it sells to and buys from** — composition
 * before counterparties, because the mix explains the partners (Australia is
 * Japan's third-largest supplier because Japan buys fuel and ore). Then the
 * **news**, which is usually the reason someone opened the country at all.
 */
export default function CountryPanel({
  iso3,
  period,
  onClose,
}: {
  iso3: string;
  period: string;
  onClose: () => void;
}) {
  const {
    data: detail,
    loading,
    error,
  } = useFetch<CountryDetail>((signal) => fetchCountry(iso3, period, signal), [iso3, period]);

  const profile = detail?.profile ?? null;
  const pp = detail?.purchasingPower;
  const trade = detail?.trade;
  const composition = detail?.composition;

  const partners = (trade?.partners ?? []).slice(0, 8);
  const widest = Math.max(...partners.map((p) => p.total), 1);

  return (
    <section className="cpanel">
      <header className="cpanel__head">
        <div className="cpanel__ident">
          <Emblem id={iso3} kind="flag" name={profile?.name ?? iso3} size={26} />
          <div>
          <h3 className="cpanel__name">{profile?.name ?? iso3}</h3>
          <p className="cpanel__meta">
            {[profile?.capital, profile?.region, profile?.incomeLevel].filter(Boolean).join(' · ')}
          </p>
          </div>
        </div>
        <button type="button" className="cpanel__close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>

      {error && <p className="cpanel__error">Could not load {iso3} — {error}</p>}
      {loading && <p className="cpanel__loading">Reading {iso3}…</p>}

      {profile && (
        <dl className="cpanel__strip">
          <div>
            <dt>Inflation{profile.inflationYear ? ` ${profile.inflationYear}` : ''}</dt>
            <dd className={tone(profile.inflation, false)}>{rate(profile.inflation)}</dd>
          </div>
          <div>
            <dt>GDP growth{profile.gdpGrowthYear ? ` ${profile.gdpGrowthYear}` : ''}</dt>
            <dd className={tone(profile.gdpGrowth)}>{rate(profile.gdpGrowth)}</dd>
          </div>
          <div>
            <dt>Unemployment</dt>
            <dd className={tone(profile.unemployment, false)}>{rate(profile.unemployment)}</dd>
          </div>
          <div>
            <dt>{profile.index ?? 'Equity market'} · {period}</dt>
            <dd className={tone(profile.marketChange)}>{move(profile.marketChange)}</dd>
          </div>
        </dl>
      )}

      {pp && pp.points.length > 0 && (
        <section className="cpanel__block">
          <h4 className="cpanel__title">Purchasing power · {period}</h4>
          <p className="cpanel__note">
            Rebased to 100. <strong>{pp.currency} in gold</strong> is what the currency actually
            buys of something no government issues — the reading that survives inflation in the
            unit you are measuring with.
          </p>
          <TimeChart
            points={pp.points}
            lines={pp.lines}
            format={index}
            baseline={100}
            height={230}
            caption={`${pp.currency} measured against gold and the dollar`}
          />
          <p className="cpanel__verdict">
            Over {period}, {pp.currency} bought{' '}
            <strong className={tone(pp.goldChange)}>{move(pp.goldChange)}</strong> in gold
            {pp.currency !== 'USD' && (
              <>
                {' '}and <strong className={tone(pp.usdChange)}>{move(pp.usdChange)}</strong> against
                the dollar — while the dollar itself bought{' '}
                <strong className={tone(pp.dollarGoldChange)}>{move(pp.dollarGoldChange)}</strong> in
                gold
              </>
            )}
            .
          </p>
        </section>
      )}

      {composition && (composition.exports.length > 0 || composition.imports.length > 0) && (
        <section className="cpanel__block">
          <h4 className="cpanel__title">
            What it trades
            {composition.years?.exports ? ` · ${composition.years.exports}` : ''}
          </h4>
          <p className="cpanel__note">
            Share of merchandise trade. The mix is what explains the partners below.
          </p>
          <div className="cpanel__mix">
            {(['exports', 'imports'] as const).map((flow) => (
              <div key={flow} className="cpanel__mixside">
                <h5>{flow === 'exports' ? 'Sells' : 'Buys'}</h5>
                <ul>
                  {composition[flow].map((entry) => (
                    <li key={entry.key}>
                      <span className="cpanel__mixlabel">{entry.label}</span>
                      <span className="cpanel__mixbar">
                        <span
                          className={`cpanel__mixfill is-${flow}`}
                          style={{ width: `${Math.min(100, entry.share)}%` }}
                        />
                      </span>
                      <span className="cpanel__mixvalue">{entry.share.toFixed(1)}%</span>
                    </li>
                  ))}
                  {composition[flow].length === 0 && <li className="cpanel__none">Not reported</li>}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {trade && partners.length > 0 && (
        <section className="cpanel__block">
          <h4 className="cpanel__title">
            Who it trades with{trade.year ? ` · ${trade.year}` : ''}
          </h4>
          <p className="cpanel__note">
            Total {usd(trade.totalExports)} sold, {usd(trade.totalImports)} bought. Bars are
            two-way trade; the balance says which direction the money runs.
          </p>
          <ul className="cpanel__partners">
            {partners.map((partner) => {
              const sold = partner.exports ?? 0;
              const bought = partner.imports ?? 0;
              return (
                <li key={partner.iso3}>
                  <span className="cpanel__pname">
                    <Emblem id={partner.iso3} kind="flag" name={partner.name} size={14} />
                    {partner.name}
                  </span>
                  <span className="cpanel__pbar">
                    <span
                      className="cpanel__pfill is-exports"
                      style={{ width: `${(sold / widest) * 100}%` }}
                      title={`Sells ${usd(sold)}`}
                    />
                    <span
                      className="cpanel__pfill is-imports"
                      style={{ width: `${(bought / widest) * 100}%` }}
                      title={`Buys ${usd(bought)}`}
                    />
                  </span>
                  <span className={`cpanel__pbal ${tone(partner.balance)}`}>
                    {partner.balance === null
                      ? '—'
                      : `${partner.balance >= 0 ? '+' : '−'}${usd(Math.abs(partner.balance)).replace('$', '$')}`}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="cpanel__key">
            <span className="cpanel__swatch is-exports" /> sells to
            <span className="cpanel__swatch is-imports" /> buys from
          </p>
        </section>
      )}

      {detail && detail.news.length > 0 && (
        <section className="cpanel__block">
          <h4 className="cpanel__title">In the news</h4>
          <ul className="cpanel__news">
            {detail.news.map((story) => (
              <li key={story.url}>
                <a href={story.url} target="_blank" rel="noopener noreferrer">
                  {story.title}
                </a>
                <span className="cpanel__source">{story.source}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
