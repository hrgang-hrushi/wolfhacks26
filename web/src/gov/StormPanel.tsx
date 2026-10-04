import { useMemo } from 'react';
import { Download, Plus, Printer } from 'lucide-react';
import { countyName, parseId, routeName, type Row, type Stats } from '../lib/data';
import { download, stormCsv } from '../lib/workOrders';

const N_CHOICES = [25, 50, 100, 200, 300];

/** Storm readiness: the highest flood scores in the Helene zone, as a staging list. No live storm feed. */
export function StormPanel({
  rows,
  n,
  onN,
  stats,
  onPick,
  onAdd,
  onPrint,
  busy,
}: {
  rows: Row[] | null;
  n: number;
  onN: (n: number) => void;
  stats: Stats | null;
  onPick: (row: Row) => void;
  onAdd: (rows: Row[]) => void;
  onPrint: (rows: Row[]) => void;
  busy: boolean;
}) {
  const top = useMemo(() => (rows ?? []).slice(0, n), [rows, n]);
  const byCounty = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of top) {
      const c = countyName(r.id, stats) ?? parseId(r.id).cty;
      m.set(c, (m.get(c) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [top, stats]);
  const max = byCounty[0]?.[1] ?? 1;
  const metric = stats?.readme_metrics.helene_top50;

  if (!rows) return <div className="g-empty">Loading the staging list…</div>;

  return (
    <div className="g-panel-body">
      <h2>Storm readiness</h2>
      <p className="g-sub">
        The {top.length} state roads with the highest flood-failure score in the Helene zone, as a list for staging equipment and planning
        detours before a storm. This is a ranking from the model, not a live storm feed.
      </p>

      <div className="g-actions">
        <label className="g-inline">
          Show top
          <select className="g-select" value={n} onChange={(e) => onN(Number(e.target.value))}>
            {N_CHOICES.filter((c) => c <= rows.length).map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <button type="button" className="g-btn" onClick={() => download(`storm-staging-top-${top.length}.csv`, stormCsv(top, stats), 'text/csv')}>
          <Download size={14} /> Checklist CSV
        </button>
        <button type="button" className="g-btn" onClick={() => onPrint(top)}>
          <Printer size={14} /> Print
        </button>
        <button type="button" className="g-btn g-btn-primary" onClick={() => onAdd(top)} disabled={busy}>
          <Plus size={15} /> {busy ? 'Adding…' : 'Make a work order'}
        </button>
      </div>

      <h3>By county</h3>
      <ul className="g-bars">
        {byCounty.map(([c, k]) => (
          <li key={c}>
            <span>{c}</span>
            <span className="g-bar">
              <span style={{ width: `${(k / max) * 100}%` }} />
            </span>
            <strong>{k}</strong>
          </li>
        ))}
      </ul>

      <h3>Staging list</h3>
      <ul className="g-seglist">
        {top.map((r) => (
          <li key={r.id}>
            <button type="button" onClick={() => onPick(r)}>
              <span className="g-rank">{r.rank}</span>
              <span>
                {routeName(r.id)}, {countyName(r.id, stats) ?? ''}, mp {(r.bmp ?? parseId(r.id).mp).toFixed(2)}
              </span>
              <em>{r.flood?.toFixed(2)}</em>
            </button>
          </li>
        ))}
      </ul>

      <p className="fine">
        How good is this ranking? In the held-out test, {metric?.with_terrain ?? 18} of the 50 highest-scored roads in the Helene zone were
        actually damaged, against about {metric?.no_model ?? 2} by chance. The model learned from one storm; another storm could behave
        differently. Flood is not assessed outside the Helene zone.
      </p>
    </div>
  );
}

/** Printable staging and detour checklist. Shown only while printing. */
export function PrintStorm({ rows, stats }: { rows: Row[]; stats: Stats | null }) {
  return (
    <div className="print-sheet">
      <header>
        <h1>Storm staging checklist: top {rows.length} flood-score roads, Helene zone</h1>
        <p className="p-demo">
          Unwatched Roads, WolfHacks 2026. A model ranking learned from Hurricane Helene, not a forecast for any coming storm. Held-out test:
          18 of the top 50 were damaged, against about 2 by chance.
        </p>
      </header>
      <table className="p-segs">
        <thead>
          <tr>
            <th>#</th>
            <th>Route</th>
            <th>County</th>
            <th>Mileposts</th>
            <th>From → to</th>
            <th>Score</th>
            <th>Equipment staged</th>
            <th>Detour planned</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.rank}</td>
              <td>{routeName(r.id)}</td>
              <td>{countyName(r.id, stats) ?? ''}</td>
              <td>
                {(r.bmp ?? parseId(r.id).mp).toFixed(2)}
                {r.emp != null && `–${r.emp.toFixed(2)}`}
              </td>
              <td>{r.fr && r.to ? `${r.fr} → ${r.to}` : ''}</td>
              <td>{r.flood?.toFixed(2)}</td>
              <td className="p-box">☐</td>
              <td className="p-box">☐</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
