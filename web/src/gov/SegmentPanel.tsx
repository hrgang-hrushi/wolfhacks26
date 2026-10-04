import { useState } from 'react';
import { Check, Link2, MapPin, Plus } from 'lucide-react';
import {
  CLASS_LABEL,
  HO_CRACK,
  HO_FLOOD,
  HO_RATE,
  PRIORITY,
  TIERS,
  countyName,
  fmtInt,
  fmtMiles,
  fmtMoney,
  fmtPct,
  fmtRate,
  fmtYtp,
  noEstimateReason,
  parseId,
  rgbCss,
  routeName,
  type Detail,
  type Seg,
  type Stats,
} from '../lib/data';
import { MODEL_INPUTS, NEGATIVE_RATE_NOTE } from '../lib/readme';
import { HeldoutBadge } from '../lib/ui';
import { segMiles, type WorkOrder } from '../lib/workOrders';

export function OrderTarget({
  orders,
  value,
  onChange,
}: {
  orders: WorkOrder[];
  value: string;
  onChange: (v: string) => void;
}) {
  const open = orders.filter((o) => o.status !== 'Done');
  return (
    <select className="g-select" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Work order to add to">
      <option value="">New work order</option>
      {open.map((o) => (
        <option key={o.id} value={o.id}>
          {o.id} ({o.status}, {o.segs.length} road{o.segs.length === 1 ? '' : 's'})
        </option>
      ))}
    </select>
  );
}

/** Straight-line projection from the road's own surveyed rating at its own predicted wear rate. */
function Projection({ seg, detail }: { seg: Seg; detail: Detail }) {
  if (detail.rtg == null || detail.sy == null) return null;
  const rate = Math.max(0, seg.rate);
  const poor = PRIORITY.poor_rating;
  const span = 20;
  const W = 300;
  const H = 110;
  const padL = 30;
  const padB = 20;
  const padT = 8;
  const x = (yr: number) => padL + (yr / span) * (W - padL - 6);
  const y = (r: number) => padT + ((100 - r) / 100) * (H - padT - padB);
  const end = Math.max(0, detail.rtg - rate * span);
  const cross = rate > 0 && detail.rtg > poor ? (detail.rtg - poor) / rate : null;
  return (
    <figure className="g-proj">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Linear projection of the rating at the predicted wear rate">
        <line x1={padL} x2={W - 6} y1={y(poor)} y2={y(poor)} className="g-proj-poor" />
        <text x={W - 8} y={y(poor) - 4} textAnchor="end" className="g-proj-label">
          Poor (below {poor})
        </text>
        {[0, 50, 100].map((r) => (
          <text key={r} x={padL - 6} y={y(r) + 3} textAnchor="end" className="g-proj-tick">
            {r}
          </text>
        ))}
        {[0, 5, 10, 15, 20].map((t) => (
          <text key={t} x={x(t)} y={H - 5} textAnchor="middle" className="g-proj-tick">
            {detail.sy! + t}
          </text>
        ))}
        <line x1={padL} x2={padL} y1={padT} y2={H - padB} className="g-proj-axis" />
        <line x1={padL} x2={W - 6} y1={H - padB} y2={H - padB} className="g-proj-axis" />
        <line x1={x(0)} y1={y(detail.rtg)} x2={x(span)} y2={y(end)} className="g-proj-line" />
        <circle cx={x(0)} cy={y(detail.rtg)} r={3.5} className="g-proj-dot" />
        {cross != null && cross <= span && <circle cx={x(cross)} cy={y(poor)} r={3.5} className="g-proj-cross" />}
      </svg>
      <figcaption>
        Linear projection at predicted wear rate, from the {detail.sy} rating of {detail.rtg}. One inspection, so this is a
        straight line, not a measured trend.
      </figcaption>
    </figure>
  );
}

export function SegmentPanel({
  selection,
  detail,
  stats,
  orders,
  target,
  onTarget,
  onAdd,
  onZoom,
  busy,
}: {
  selection: Seg[];
  detail: Detail | null;
  stats: Stats | null;
  orders: WorkOrder[];
  target: string;
  onTarget: (v: string) => void;
  onAdd: () => void;
  onZoom: (seg: Seg) => void;
  busy: boolean;
}) {
  if (selection.length === 0)
    return (
      <div className="g-empty">
        <MapPin size={22} />
        <p>Click a road on the map, or a row in the work queue, to see its forecast.</p>
        <p className="fine">Hold Shift and drag on the map to select several roads at once.</p>
      </div>
    );

  if (selection.length > 1) {
    const miles = selection.reduce((a, s) => a + segMiles(s), 0);
    const counts = [0, 0, 0, 0, 0];
    for (const s of selection) counts[s.tier]++;
    return (
      <div className="g-panel-body">
        <h2>{selection.length} roads selected</h2>
        <p className="g-sub">{fmtMiles(miles)} in total (measured along the lines)</p>
        <ul className="g-tierlist">
          {TIERS.map((t, i) =>
            counts[i] ? (
              <li key={t.key}>
                <span className="g-dot" style={{ background: rgbCss(t.rgb) }} />
                {t.label}
                <strong>{counts[i]}</strong>
              </li>
            ) : null,
          )}
        </ul>
        <div className="g-actions">
          <OrderTarget orders={orders} value={target} onChange={onTarget} />
          <button type="button" className="g-btn g-btn-primary" onClick={onAdd} disabled={busy}>
            <Plus size={15} /> {busy ? 'Adding…' : `Add ${selection.length} to work order`}
          </button>
        </div>
        <ul className="g-seglist">
          {selection.slice(0, 200).map((s) => (
            <li key={s.id}>
              <button type="button" onClick={() => onZoom(s)}>
                <span className="g-dot" style={{ background: rgbCss(TIERS[s.tier].rgb) }} />
                <span>
                  {routeName(s.id)}, mp {parseId(s.id).mp.toFixed(2)}
                </span>
                <em>{fmtYtp(s.ytp)}</em>
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const seg = selection[0];
  const { cls, mp, route } = parseId(seg.id);
  const county = countyName(seg.id, stats);
  const tier = TIERS[seg.tier];
  const age = detail?.ry != null && detail.sy != null && detail.ry <= detail.sy ? detail.sy - detail.ry : null;

  return (
    <div className="g-panel-body">
      <div className="g-seg-head">
        <div>
          <h2>
            {routeName(seg.id)}
            {county && <span> · {county} County</span>}
          </h2>
          <p className="g-sub">
            {CLASS_LABEL[cls]}, mp {mp.toFixed(2)}
            {detail?.emp != null && ` to ${detail.emp.toFixed(2)}`}
            {detail?.len != null && ` · ${fmtMiles(detail.len)}`}
            {detail?.ln != null && ` · ${detail.ln} lanes`}
          </p>
          {detail?.fr && detail.to && (
            <p className="g-sub">
              {detail.fr} → {detail.to}
            </p>
          )}
        </div>
        <span className="g-tier-chip" style={{ background: rgbCss(tier.rgb, 0.14), color: rgbCss(tier.rgb) }} title={tier.rule}>
          {tier.label}
        </span>
      </div>

      <div className="g-facts">
        <div>
          <span className="g-k">Years to Poor</span>
          <span className="g-v">{fmtYtp(seg.ytp)}</span>
          <HeldoutBadge heldout={(seg.ho & HO_RATE) !== 0} />
          {seg.ytp == null && <span className="g-n">{noEstimateReason(detail)}</span>}
        </div>
        <div>
          <span className="g-k">Predicted wear</span>
          <span className="g-v">{fmtRate(seg.rate)}</span>
          <HeldoutBadge heldout={(seg.ho & HO_RATE) !== 0} />
          {seg.rate < 0 && <span className="g-n">{NEGATIVE_RATE_NOTE}</span>}
        </div>
        <div>
          <span className="g-k">Cracking probability</span>
          <span className="g-v">{fmtPct(seg.crack)}</span>
          <HeldoutBadge heldout={(seg.ho & HO_CRACK) !== 0} />
        </div>
        <div>
          <span className="g-k">Flood-failure score</span>
          {seg.hz && seg.flood != null ? (
            <>
              <span className="g-v">{seg.flood.toFixed(seg.flood < 0.1 ? 3 : 2)}</span>
              <HeldoutBadge heldout={(seg.ho & HO_FLOOD) !== 0} />
              <span className="g-n">Helene zone. A ranking score, not a probability.</span>
            </>
          ) : (
            <>
              <span className="g-v g-v-muted">Not assessed</span>
              <span className="g-n">Outside the Helene zone.</span>
            </>
          )}
        </div>
      </div>

      {detail && (
        <>
          <h3>NCDOT record</h3>
          <dl className="g-record">
            {detail.rtg != null && (
              <>
                <dt>Rating</dt>
                <dd>
                  {detail.rtg} of 100 ({detail.sy} survey)
                </dd>
              </>
            )}
            {detail.ry != null && (
              <>
                <dt>Last resurfaced</dt>
                <dd>
                  {detail.ry}
                  {age != null && ` (${age} years before the survey)`}
                </dd>
              </>
            )}
            <dt>Traffic</dt>
            <dd>
              {detail.aadt != null
                ? `${fmtInt(detail.aadt)} vehicles a day (${detail.as === 'count' ? 'counted' : 'estimated'})`
                : 'No count or estimate'}
            </dd>
            {detail.trt && (
              <>
                <dt>NCDOT treatment</dt>
                <dd>
                  {detail.trt}
                  {detail.cost != null && detail.cost > 0 && ` · ${fmtMoney(detail.cost)}`}
                </dd>
              </>
            )}
            <dt>Route code</dt>
            <dd className="g-mono">{route}</dd>
          </dl>
          {detail.trt && (
            <p className="fine">Treatment and cost are NCDOT’s own recommendation from its pavement record, not an output of this model.</p>
          )}
          {seg.ytp != null && <Projection seg={seg} detail={detail} />}
        </>
      )}

      <p className="g-why">
        <strong>Why this forecast?</strong>{' '}
        {detail
          ? `This road’s inputs: ${age != null ? `a surface ${age} years old at inspection` : 'no resurfacing year on record (so the wear forecast is an extrapolation)'}, ${
              detail.aadt != null ? `about ${fmtInt(detail.aadt)} vehicles a day` : 'no traffic count'
            }, and the terrain around it. `
          : ''}
        {MODEL_INPUTS}
      </p>

      <div className="g-actions">
        <OrderTarget orders={orders} value={target} onChange={onTarget} />
        <button type="button" className="g-btn g-btn-primary" onClick={onAdd} disabled={busy}>
          <Plus size={15} /> {busy ? 'Adding…' : 'Add to work order'}
        </button>
        <button type="button" className="g-btn" onClick={() => onZoom(seg)}>
          Zoom to road
        </button>
        <CopyLink />
      </div>
    </div>
  );
}

/** The address bar already holds a link to the selected road (GovApp keeps it there); this copies it. */
function CopyLink() {
  const [copied, setCopied] = useState(false);
  if (!navigator.clipboard) return null;
  return (
    <button
      type="button"
      className="g-btn"
      title="Copy a link that reopens this road"
      onClick={() => {
        void navigator.clipboard
          .writeText(window.location.href)
          .then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          })
          .catch(() => undefined);
      }}
    >
      {copied ? <Check size={14} /> : <Link2 size={14} />} {copied ? 'Copied' : 'Copy link'}
    </button>
  );
}
