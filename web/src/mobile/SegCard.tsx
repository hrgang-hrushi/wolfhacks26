import { X } from 'lucide-react';
import {
  CLASS_LABEL,
  HO_CRACK,
  HO_FLOOD,
  HO_RATE,
  TIERS,
  countyName,
  fmtInt,
  fmtMiles,
  fmtPct,
  fmtRate,
  fmtYtp,
  noEstimateReason,
  parseId,
  rgbCss,
  routeName,
  type Detail,
  type Featured,
  type Seg,
  type Stats,
} from '../lib/data';
import { HeldoutBadge } from '../lib/ui';

/** One road in plain English. */
export function SegCard({
  seg,
  detail,
  stats,
  compact,
  distance,
  outcome,
}: {
  seg: Seg;
  detail: Detail | null;
  stats: Stats | null;
  compact?: boolean;
  distance?: number;
  outcome?: 'damaged' | 'not damaged' | 'hidden';
}) {
  const { cls, mp } = parseId(seg.id);
  const county = countyName(seg.id, stats);
  const tier = TIERS[seg.tier];
  const title = `${routeName(seg.id)}${county ? ` · ${county} County` : ''}`;

  if (compact)
    return (
      <span className="m-card-compact">
        <span className="m-dot" style={{ background: rgbCss(tier.rgb) }} />
        <span className="m-card-compact-main">
          <strong>{routeName(seg.id)}</strong>, mp {mp.toFixed(2)}
          {distance != null && <em> · {distance < 1000 ? `${Math.round(distance)} m` : `${(distance / 1000).toFixed(1)} km`} away</em>}
        </span>
        <span className="m-card-compact-val">{fmtYtp(seg.ytp)}</span>
      </span>
    );

  return (
    <article className="m-card">
      <header>
        <h3>{title}</h3>
        <p>
          {CLASS_LABEL[cls]}, milepost {mp.toFixed(2)}
          {detail?.emp != null && ` to ${detail.emp.toFixed(2)}`}
          {detail?.len != null && ` (${fmtMiles(detail.len)})`}
        </p>
        {detail?.fr && detail.to && (
          <p className="m-fromto">
            From {detail.fr} to {detail.to}
          </p>
        )}
      </header>

      {outcome && outcome !== 'hidden' && (
        <div className={`m-outcome ${outcome === 'damaged' ? 'bad' : ''}`}>
          What happened in Helene: <strong>{outcome}</strong>
        </div>
      )}

      <dl className="m-facts">
        <div>
          <dt>Reaches Poor</dt>
          <dd>
            {seg.ytp == null ? 'No estimate' : seg.ytp >= 50 ? 'Not within 50 years' : seg.ytp < 0.05 ? 'Already there' : `In about ${fmtYtp(seg.ytp)}`}
            <HeldoutBadge heldout={(seg.ho & HO_RATE) !== 0} />
          </dd>
          {seg.ytp == null && <dd className="m-note">{noEstimateReason(detail)}</dd>}
        </div>
        <div>
          <dt>Wear</dt>
          <dd>{fmtRate(seg.rate)}</dd>
          <dd className="m-note">Rating points lost each year. Poor is a rating below 60.</dd>
        </div>
        <div>
          <dt>Cracking risk</dt>
          <dd>
            {fmtPct(seg.crack)}
            <HeldoutBadge heldout={(seg.ho & HO_CRACK) !== 0} />
          </dd>
          <dd className="m-note">Chance that more than 10% of the surface is cracked.</dd>
        </div>
        <div>
          <dt>Flood risk</dt>
          {seg.hz && seg.flood != null ? (
            <>
              <dd>
                Score {seg.flood.toFixed(seg.flood < 0.1 ? 3 : 2)}
                <HeldoutBadge heldout={(seg.ho & HO_FLOOD) !== 0} />
              </dd>
              <dd className="m-note">0 to 1, learned from what Hurricane Helene damaged. A ranking, not a probability.</dd>
            </>
          ) : (
            <>
              <dd>Not assessed</dd>
              <dd className="m-note">This road is outside the Helene zone, so the flood model does not apply.</dd>
            </>
          )}
        </div>
      </dl>

      <p className="m-tier">
        <span className="m-dot" style={{ background: rgbCss(tier.rgb) }} />
        Repair tier: <strong>{tier.label}</strong>
      </p>

      {detail && (
        <p className="m-record">
          NCDOT record:
          {detail.rtg != null && ` rated ${detail.rtg} of 100 in ${detail.sy ?? 'the last survey'}.`}
          {detail.ry != null && ` Last resurfaced ${detail.ry}.`}
          {detail.aadt != null && ` About ${fmtInt(detail.aadt)} vehicles a day (${detail.as === 'count' ? 'counted' : 'estimated'}).`}
        </p>
      )}
    </article>
  );
}

/** The README's worked example, with the README's own numbers. */
export function FeaturedCard({ featured, onClose }: { featured: Featured; onClose: () => void }) {
  const r = featured.readme;
  return (
    <article className="m-card m-featured">
      <header>
        <h3>State Road 2748 · Wake County</h3>
        <button type="button" className="m-icon-btn" aria-label="Close example" onClick={onClose}>
          <X size={18} />
        </button>
      </header>
      <p>
        A two-lane road, {r.length_mi} miles long. Inspectors rated it <strong>{r.rating} of 100</strong> in {r.survey_year}. It was last
        resurfaced in {r.resurfaced}.
      </p>
      <table className="m-compare">
        <thead>
          <tr>
            <th />
            <th>Predicted, unseen</th>
            <th>What happened</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Wear</th>
            <td>{r.wear_predicted} pts/yr</td>
            <td>{r.wear_actual} pts/yr</td>
          </tr>
          <tr>
            <th>Reaches Poor</th>
            <td>in about {r.years_to_poor} years</td>
            <td>not known yet</td>
          </tr>
          <tr>
            <th>Cracking</th>
            <td>top {r.crack_top_pct}% of all roads</td>
            <td>inspection found cracking over 10%</td>
          </tr>
        </tbody>
      </table>
      <p className="m-note">
        The model that scored this road was trained without it, and without any road in its 5 km square. {r.source}.
      </p>
    </article>
  );
}
