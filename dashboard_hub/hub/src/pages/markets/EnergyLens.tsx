import TimeChart from '../../components/TimeChart';
import { index, move, price, tone } from './worldApi';
import type { EnergyPanel } from './worldApi';

const GROUPS = ['Energy', 'Metals', 'Basket'] as const;

const GROUP_NOTE: Record<string, string> = {
  Energy: 'Crude, gas and refined products. Henry Hub and TTF are the two gas benchmarks that matter — they price the same molecule either side of the Atlantic and rarely agree.',
  Metals: 'What energy is dug up with, and what it is stored as when nobody trusts the currency.',
  Basket: 'The broad commodity index and the equities that produce it — how the whole complex moved, and whether the producers kept it.',
};

/**
 * Energy and the commodity complex.
 *
 * The chart carries crude and gas because those are the two prices that pass
 * through to everything else on this desk — inflation, trade balances for the
 * countries that import fuel, and the currencies of the ones that export it.
 */
export default function EnergyLens({
  panel,
  period,
  loading,
}: {
  panel: EnergyPanel | null;
  period: string;
  loading: boolean;
}) {
  if (!panel) {
    return <p className="world__loading">{loading ? 'Reading the pits…' : 'No energy data.'}</p>;
  }

  return (
    <div className="world__energy">
      <section className="cpanel__block">
        <h4 className="cpanel__title">Crude and gas · {period}</h4>
        <p className="cpanel__note">
          Rebased to 100. Crude trades near $80 a barrel and gas near $3 an MMBtu, so on a shared
          price axis the gas line lies flat and hides the fact that it is the one moving
          differently. Levels are in the table below.
        </p>
        <TimeChart
          points={panel.points}
          lines={panel.lines}
          format={index}
          baseline={100}
          height={280}
          caption={`Brent, WTI and Henry Hub over ${period}`}
        />
      </section>

      {GROUPS.map((group) => {
        const rows = panel.prices.filter((p) => p.group === group);
        if (rows.length === 0) return null;
        return (
          <section key={group} className="cpanel__block">
            <h4 className="cpanel__title">{group}</h4>
            <p className="cpanel__note">{GROUP_NOTE[group]}</p>
            <ul className="world__prices">
              {rows.map((row) => (
                <li key={row.slug}>
                  <span className="world__pricename">{row.name}</span>
                  <span className="world__priceunit">{row.unit}</span>
                  <span className="world__pricelast">{price(row.last)}</span>
                  <span className={`world__pricechg ${tone(row.change)}`}>{move(row.change)}</span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
