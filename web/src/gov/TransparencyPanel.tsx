import { PRIORITY, TIERS, fmtInt, fmtPct, rgbCss, type Stats } from '../lib/data';
import { SCOPE_NOTE } from '../lib/readme';
import { CannotClaim, MetricsTable, Sources } from '../lib/ui';

/** Model transparency: what was measured, what cannot be claimed, where the data came from. */
export function TransparencyPanel({ stats }: { stats: Stats | null }) {
  if (!stats) return <div className="g-empty">Loading…</div>;
  const s = PRIORITY.score;
  return (
    <div className="g-panel-body">
      <h2>Model transparency</h2>
      <p className="g-sub">{SCOPE_NOTE}</p>

      <h3>Does it work?</h3>
      <MetricsTable stats={stats} />

      <h3>What we cannot claim</h3>
      <CannotClaim />

      <h3>Held-out and in-sample</h3>
      <p className="g-text">
        A prediction is <strong>held-out</strong> when the model that made it was trained without that road or any road in its 5 km square.
        Wear is held-out for {fmtInt(stats.heldout.rate)} of {fmtInt(stats.total)} roads ({fmtPct(stats.heldout.rate / stats.total)}),
        cracking for {fmtInt(stats.heldout.crack)}, flood for all {fmtInt(stats.heldout.flood)} roads in the Helene zone. The rest had no
        label to hold out and are marked <strong>in-sample</strong>.
      </p>

      <h3>Repair tiers (our thresholds, not NCDOT policy)</h3>
      <ul className="g-tierlist g-tierlist-rules">
        {TIERS.map((t) => (
          <li key={t.key}>
            <span className="g-dot" style={{ background: rgbCss(t.rgb) }} />
            <span>
              <b>{t.label}</b>: {t.rule}.
            </span>
            <strong>{fmtInt(stats.tiers[t.key])}</strong>
          </li>
        ))}
      </ul>
      <p className="fine">
        Inside a tier, roads are ordered by a priority score: {s.w_ytp} × (how close to Poor, 0 at {s.ytp_horizon_years}+ years) + {s.w_crack} ×
        cracking probability + {s.w_flood} × flood score (Helene zone only). Poor means a rating below {PRIORITY.poor_rating}.{' '}
        {fmtInt(stats.no_ytp)} roads have no years-to-Poor estimate because their rating is out of date.
      </p>

      <h3>Data sources</h3>
      <Sources stats={stats} />
    </div>
  );
}
