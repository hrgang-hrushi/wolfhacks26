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

/** One road in plain English matching Executive Dashboard design system. */
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
  const rName = routeName(seg.id);

  if (compact) {
    return (
      <span className="m-card-compact">
        <span className="m-dot" style={{ background: rgbCss(tier.rgb) }} />
        <span className="m-card-compact-main">
          <strong>{rName}</strong>, mp {mp.toFixed(2)}
          {distance != null && <em> · {distance < 1000 ? `${Math.round(distance)} m` : `${(distance / 1000).toFixed(1)} km`} away</em>}
        </span>
        <span className="m-card-compact-val">{fmtYtp(seg.ytp)}</span>
      </span>
    );
  }

  // Derive condition category
  const rating = detail?.rtg;
  let conditionCategory: 'good' | 'fair' | 'poor' = 'good';
  let conditionLabel = 'Satisfactory';

  if (rating != null) {
    if (rating < 60) {
      conditionCategory = 'poor';
      conditionLabel = 'Critical (Below 60)';
    } else if (rating < 80) {
      conditionCategory = 'fair';
      conditionLabel = 'Fair (60–79)';
    } else {
      conditionCategory = 'good';
      conditionLabel = 'Good (≥80)';
    }
  } else if (seg.ytp != null) {
    if (seg.ytp < 3) {
      conditionCategory = 'poor';
      conditionLabel = 'Urgent Action';
    } else if (seg.ytp < 8) {
      conditionCategory = 'fair';
      conditionLabel = 'Fair Projection';
    } else {
      conditionCategory = 'good';
      conditionLabel = 'Long-Term Stable';
    }
  }

  return (
    <article className="m-card">
      <header className="m-card-header">
        <div className="m-card-eyebrow">
          <span className="m-route-pill">{rName}</span>
          <span className="m-county-tag">{county ? `${county} County, NC` : 'North Carolina'}</span>
        </div>
        <h3>{rName}{county ? ` · ${county} County` : ''}</h3>
        <p className="m-card-sub">
          {CLASS_LABEL[cls]}, mp {mp.toFixed(2)}
          {detail?.emp != null && ` to ${detail.emp.toFixed(2)}`}
          {detail?.len != null && ` (${fmtMiles(detail.len)})`}
        </p>
        {detail?.fr && detail.to && (
          <p className="m-card-sub">
            From {detail.fr} to {detail.to}
          </p>
        )}
      </header>

      {/* Pavement Condition Hero Bar */}
      <div className="m-pci-hero">
        <div className="m-pci-left">
          <span className="m-pci-score">{rating != null ? rating : (seg.ytp ? Math.min(100, Math.round(55 + seg.ytp * 3.2)) : '—')}</span>
          <span className="m-pci-max">/ 100 PCI</span>
        </div>
        <span className={`m-condition-badge ${conditionCategory}`}>
          {conditionLabel}
        </span>
      </div>

      {outcome && outcome !== 'hidden' && (
        <div className={`m-outcome ${outcome === 'damaged' ? 'bad' : ''}`}>
          Helene Inspection Ground Truth: <strong>{outcome.toUpperCase()}</strong>
        </div>
      )}

      {/* 4 Telemetry Pods (matching CleanLocationCard design) */}
      <div className="m-pods-grid">
        {/* Pod 1: Years to Poor */}
        <div className="m-pod-item">
          <div className="m-pod-title">
            <span>TIME TO POOR</span>
            <HeldoutBadge heldout={(seg.ho & HO_RATE) !== 0} />
          </div>
          <span className="m-pod-value">
            {seg.ytp == null ? 'No est' : seg.ytp >= 50 ? '>50 yrs' : seg.ytp < 0.05 ? 'Critical' : fmtYtp(seg.ytp)}
          </span>
          <span className="m-pod-desc">
            {seg.ytp == null ? noEstimateReason(detail) : 'Action threshold (<60 PCI)'}
          </span>
        </div>

        {/* Pod 2: Wear Rate */}
        <div className="m-pod-item">
          <div className="m-pod-title">
            <span>WEAR RATE</span>
          </div>
          <span className="m-pod-value">{fmtRate(seg.rate)}</span>
          <span className="m-pod-desc">Rating points lost/yr</span>
        </div>

        {/* Pod 3: Cracking Risk */}
        <div className="m-pod-item">
          <div className="m-pod-title">
            <span>CRACK RISK</span>
            <HeldoutBadge heldout={(seg.ho & HO_CRACK) !== 0} />
          </div>
          <span className="m-pod-value">{fmtPct(seg.crack)}</span>
          <span className="m-pod-desc">&gt;10% surface distress</span>
        </div>

        {/* Pod 4: Flood Risk */}
        <div className="m-pod-item">
          <div className="m-pod-title">
            <span>FLOOD RISK</span>
            <HeldoutBadge heldout={(seg.ho & HO_FLOOD) !== 0} />
          </div>
          <span className="m-pod-value">
            {seg.hz && seg.flood != null ? seg.flood.toFixed(seg.flood < 0.1 ? 3 : 2) : 'Not assessed'}
          </span>
          <span className="m-pod-desc">
            {seg.hz ? 'Helene washout ranking' : 'Outside storm zone'}
          </span>
        </div>
      </div>

      <p className="m-tier">
        <span className="m-dot" style={{ background: rgbCss(tier.rgb) }} />
        Repair Priority: <strong>{tier.label}</strong>
      </p>

      {detail && (
        <p className="m-record">
          NCDOT Survey:
          {detail.rtg != null && ` rated ${detail.rtg}/100 in ${detail.sy ?? 'last survey'}.`}
          {detail.ry != null && ` Last resurfaced ${detail.ry}.`}
          {detail.aadt != null && ` ~${fmtInt(detail.aadt)} AADT (${detail.as === 'count' ? 'counted' : 'estimated'}).`}
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
        <div className="m-card-eyebrow">
          <span className="m-route-pill">SR 2748</span>
          <span className="m-county-tag">Wake County, NC</span>
        </div>
        <button type="button" className="m-icon-btn" aria-label="Close example" onClick={onClose}>
          <X size={16} />
        </button>
      </header>
      <h3>State Road 2748 · Worked Example</h3>
      <p className="m-card-sub">
        A two-lane road, {r.length_mi} miles long. Inspectors rated it <strong>{r.rating} of 100</strong> in {r.survey_year}. It was last
        resurfaced in {r.resurfaced}.
      </p>
      <table className="m-compare">
        <thead>
          <tr>
            <th />
            <th>PREDICTED, UNSEEN</th>
            <th>WHAT HAPPENED</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Wear Rate</th>
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
            <td>inspection confirmed &gt;10%</td>
          </tr>
        </tbody>
      </table>
      <p className="m-note">
        The model that scored this road was trained without it, and without any road in its 5 km square. {r.source}.
      </p>
    </article>
  );
}
