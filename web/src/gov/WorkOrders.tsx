import { useState } from 'react';
import { Download, Printer, Trash2, X } from 'lucide-react';
import { TIERS, fmtMiles, fmtMoney, fmtYtpShort, parseId, rgbCss, routeName } from '../lib/data';
import {
  STATUSES,
  download,
  orderCost,
  orderCsv,
  orderGeoJson,
  orderMiles,
  orderTier,
  orders as store,
  segMiles,
  type OrderSeg,
  type OrderStatus,
  type WorkOrder,
} from '../lib/workOrders';

export function DemoTag() {
  return (
    <span className="badge badge-demo" title="Crews and work orders are a demonstration of the workflow. They are stored in this browser only.">
      demo data
    </span>
  );
}

/** Bottom tab: every work order in a table, with the editable crew list. */
export function WorkOrdersTable({
  orders,
  crews,
  activeId,
  onOpen,
}: {
  orders: WorkOrder[];
  crews: string[];
  activeId: string | null;
  onOpen: (id: string) => void;
}) {
  const [newCrew, setNewCrew] = useState('');
  return (
    <div className="g-orders">
      <div className="g-queue-bar">
        <DemoTag />
        <span className="g-queue-note">
          Work orders show how dispatch would work. They stay in this browser and are not sent to any crew.
        </span>
        <div className="g-crews">
          <span className="g-k">Demo crews</span>
          {crews.map((c) => (
            <span key={c} className="g-crew">
              {c}
              <button type="button" aria-label={`Remove ${c}`} onClick={() => store.removeCrew(c)}>
                <X size={12} />
              </button>
            </span>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              store.addCrew(newCrew);
              setNewCrew('');
            }}
          >
            <input className="g-input" value={newCrew} onChange={(e) => setNewCrew(e.target.value)} placeholder="Add a crew" aria-label="New crew name" />
          </form>
        </div>
      </div>
      <div className="g-table-wrap">
        <table className="g-table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Status</th>
              <th>Tier</th>
              <th className="g-num">Roads</th>
              <th className="g-num">Miles</th>
              <th>Crew</th>
              <th>Due</th>
              <th>Notes</th>
              <th className="g-num">NCDOT cost</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => {
              const t = TIERS[orderTier(o)];
              const cost = orderCost(o);
              return (
                <tr
                  key={o.id}
                  className={o.id === activeId ? 'sel' : ''}
                  tabIndex={0}
                  onClick={() => onOpen(o.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && e.target === e.currentTarget) onOpen(o.id);
                  }}
                >
                  <td>
                    <strong>{o.id}</strong>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <select
                      className={`g-select g-status g-status-${o.status.replace(' ', '')}`}
                      value={o.status}
                      aria-label={`Status of ${o.id}`}
                      onChange={(e) => store.update(o.id, { status: e.target.value as OrderStatus })}
                    >
                      {STATUSES.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <span className="g-dot" style={{ background: rgbCss(t.rgb) }} /> {t.label}
                  </td>
                  <td className="g-num">{o.segs.length}</td>
                  <td className="g-num">{orderMiles(o).toFixed(1)}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <select className="g-select" value={o.crew} aria-label={`Crew for ${o.id}`} onChange={(e) => store.update(o.id, { crew: e.target.value })}>
                      <option value="">Unassigned</option>
                      {crews.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input className="g-input" type="date" value={o.due} aria-label={`Due date for ${o.id}`} onChange={(e) => store.update(o.id, { due: e.target.value })} />
                  </td>
                  <td className="g-notes-cell">{o.notes}</td>
                  <td className="g-num">{cost != null ? fmtMoney(cost) : ''}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {orders.length === 0 && (
          <p className="g-empty-row">No work orders yet. Select a road (or Shift-drag a box on the map) and press “Add to work order”.</p>
        )}
      </div>
    </div>
  );
}

/** Side panel: one work order, editable, with exports. */
export function OrderPanel({
  order,
  crews,
  onZoomSeg,
  onZoomOrder,
  onPrint,
  onClose,
}: {
  order: WorkOrder | null;
  crews: string[];
  onZoomSeg: (s: OrderSeg) => void;
  onZoomOrder: (o: WorkOrder) => void;
  onPrint: (o: WorkOrder) => void;
  onClose: () => void;
}) {
  if (!order)
    return (
      <div className="g-empty">
        <p>Open a work order from the Work orders tab, or add a road to a new one.</p>
      </div>
    );
  const t = TIERS[orderTier(order)];
  const cost = orderCost(order);
  return (
    <div className="g-panel-body">
      <div className="g-seg-head">
        <div>
          <h2>
            {order.id} <DemoTag />
          </h2>
          <p className="g-sub">
            {order.segs.length} road{order.segs.length === 1 ? '' : 's'} · {fmtMiles(orderMiles(order))}
            {cost != null && ` · NCDOT estimate ${fmtMoney(cost)}`}
          </p>
        </div>
        <span className="g-tier-chip" style={{ background: rgbCss(t.rgb, 0.14), color: rgbCss(t.rgb) }}>
          {t.label}
        </span>
      </div>

      <div className="g-form">
        <label>
          Status
          <select className="g-select" value={order.status} onChange={(e) => store.update(order.id, { status: e.target.value as OrderStatus })}>
            {STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Crew
          <select className="g-select" value={order.crew} onChange={(e) => store.update(order.id, { crew: e.target.value })}>
            <option value="">Unassigned</option>
            {crews.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label>
          Due date
          <input className="g-input" type="date" value={order.due} onChange={(e) => store.update(order.id, { due: e.target.value })} />
        </label>
        <label className="g-form-wide">
          Notes
          <textarea className="g-input" rows={2} value={order.notes} onChange={(e) => store.update(order.id, { notes: e.target.value })} />
        </label>
      </div>

      <div className="g-actions">
        <button type="button" className="g-btn" onClick={() => onZoomOrder(order)}>
          Show on map
        </button>
        <button type="button" className="g-btn" onClick={() => download(`${order.id}.csv`, orderCsv(order), 'text/csv')}>
          <Download size={14} /> CSV
        </button>
        <button type="button" className="g-btn" onClick={() => download(`${order.id}.geojson`, orderGeoJson(order), 'application/geo+json')}>
          <Download size={14} /> GeoJSON
        </button>
        <button type="button" className="g-btn" onClick={() => onPrint(order)}>
          <Printer size={14} /> Print
        </button>
        <button
          type="button"
          className="g-btn g-btn-danger"
          onClick={() => {
            if (window.confirm(`Delete ${order.id}? This cannot be undone.`)) {
              store.remove(order.id);
              onClose();
            }
          }}
        >
          <Trash2 size={14} /> Delete
        </button>
      </div>

      <h3>Roads on this order</h3>
      <ul className="g-seglist">
        {order.segs.map((s) => (
          <li key={s.id}>
            <button type="button" onClick={() => onZoomSeg(s)}>
              <span className="g-dot" style={{ background: rgbCss(TIERS[s.tier].rgb) }} />
              <span>
                {routeName(s.id)}
                {s.county ? `, ${s.county}` : ''}, mp {(s.bmp ?? parseId(s.id).mp).toFixed(2)}
                {s.emp != null && `–${s.emp.toFixed(2)}`}
              </span>
              <em>{fmtYtpShort(s.ytp)} yr</em>
            </button>
            <button type="button" className="g-x" aria-label={`Remove ${routeName(s.id)} from ${order.id}`} onClick={() => store.removeSeg(order.id, s.id)}>
              <X size={14} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** North-up sketch of the order's roads. No basemap, so it prints cleanly anywhere. */
function RouteSketch({ segs }: { segs: OrderSeg[] }) {
  let w = 180;
  let s = 90;
  let e = -180;
  let n = -90;
  for (const seg of segs)
    for (const p of seg.paths)
      for (let i = 0; i < p.length; i += 2) {
        w = Math.min(w, p[i]);
        e = Math.max(e, p[i]);
        s = Math.min(s, p[i + 1]);
        n = Math.max(n, p[i + 1]);
      }
  if (w > e) return null;
  const k = Math.cos((((s + n) / 2) * Math.PI) / 180);
  const W = 520;
  const H = 300;
  const pad = 18;
  const spanX = Math.max((e - w) * k, 1e-5);
  const spanY = Math.max(n - s, 1e-5);
  const scale = Math.min((W - 2 * pad) / spanX, (H - 2 * pad) / spanY);
  const ox = (W - spanX * scale) / 2;
  const oy = (H - spanY * scale) / 2;
  const pts = (p: number[]) => {
    const out: string[] = [];
    for (let i = 0; i < p.length; i += 2) out.push(`${(ox + (p[i] - w) * k * scale).toFixed(1)},${(H - oy - (p[i + 1] - s) * scale).toFixed(1)}`);
    return out.join(' ');
  };
  const miles = (W / scale) * 69; // the frame's width in degrees of latitude; one is about 69 miles
  return (
    <figure className="p-sketch">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Sketch of the roads on this order">
        <rect x={0.5} y={0.5} width={W - 1} height={H - 1} fill="none" stroke="#94a3b8" />
        {segs.map((seg) =>
          seg.paths.map((p, i) => (
            <polyline key={`${seg.id}-${i}`} points={pts(p)} fill="none" stroke={rgbCss(TIERS[seg.tier].rgb)} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
          )),
        )}
        <text x={W - 10} y={18} textAnchor="end" fontSize={11} fill="#475569">
          N ↑
        </text>
      </svg>
      <figcaption>Route sketch, north up, no basemap. The frame is about {miles < 10 ? miles.toFixed(1) : Math.round(miles)} miles wide.</figcaption>
    </figure>
  );
}

/** The one-page printable order. Shown only while printing. */
export function PrintOrder({ order }: { order: WorkOrder }) {
  const t = TIERS[orderTier(order)];
  const cost = orderCost(order);
  return (
    <div className="print-sheet">
      <header>
        <h1>Work order {order.id}</h1>
        <p className="p-demo">DEMO DATA. Unwatched Roads, WolfHacks 2026. Model predictions, not inspections. Not a real dispatch.</p>
      </header>
      <table className="p-meta">
        <tbody>
          <tr>
            <th>Priority tier</th>
            <td>{t.label}</td>
            <th>Status</th>
            <td>{order.status}</td>
          </tr>
          <tr>
            <th>Crew</th>
            <td>{order.crew || 'Unassigned'}</td>
            <th>Due</th>
            <td>{order.due || 'Not set'}</td>
          </tr>
          <tr>
            <th>Roads</th>
            <td>
              {order.segs.length} ({fmtMiles(orderMiles(order))})
            </td>
            <th>NCDOT cost estimate</th>
            <td>{cost != null ? fmtMoney(cost) : 'n/a'}</td>
          </tr>
          <tr>
            <th>Notes</th>
            <td colSpan={3}>{order.notes || ' '}</td>
          </tr>
        </tbody>
      </table>
      <RouteSketch segs={order.segs} />
      <table className="p-segs">
        <thead>
          <tr>
            <th>#</th>
            <th>Route</th>
            <th>County</th>
            <th>Mileposts</th>
            <th>Miles</th>
            <th>From → to</th>
            <th>Tier</th>
            <th>Yrs to Poor</th>
            <th>NCDOT treatment</th>
            <th>Done</th>
          </tr>
        </thead>
        <tbody>
          {order.segs.slice(0, 28).map((s, i) => (
            <tr key={s.id}>
              <td>{i + 1}</td>
              <td>{routeName(s.id)}</td>
              <td>{s.county ?? ''}</td>
              <td>
                {(s.bmp ?? parseId(s.id).mp).toFixed(2)}
                {s.emp != null && `–${s.emp.toFixed(2)}`}
              </td>
              <td>{segMiles(s).toFixed(2)}</td>
              <td>{s.fr && s.to ? `${s.fr} → ${s.to}` : ''}</td>
              <td>{TIERS[s.tier].label}</td>
              <td>{fmtYtpShort(s.ytp)}</td>
              <td>{s.trt ?? ''}</td>
              <td className="p-box">☐</td>
            </tr>
          ))}
        </tbody>
      </table>
      {order.segs.length > 28 && <p className="p-demo">{order.segs.length - 28} more roads are in the CSV export.</p>}
    </div>
  );
}
