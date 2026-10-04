import { useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import {
  HO_RATE,
  TIERS,
  countyName,
  fmtInt,
  fmtMoney,
  fmtPct,
  fmtYtpShort,
  parseId,
  rgbCss,
  routeName,
  type Mode,
  type Row,
  type Stats,
  type TierIdx,
} from '../lib/data';
import { passes, type Filters } from './filters';

type SortKey = 'score' | 'ytp' | 'crack' | 'flood' | 'cost' | 'aadt';

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'score', label: 'Priority score' },
  { key: 'ytp', label: 'Soonest to Poor' },
  { key: 'crack', label: 'Cracking risk' },
  { key: 'flood', label: 'Flood score' },
  { key: 'aadt', label: 'Traffic' },
  { key: 'cost', label: 'NCDOT cost estimate' },
];

const PAGE = 150;

function sortValue(r: Row, k: SortKey): number {
  if (k === 'score') return -r.s;
  if (k === 'ytp') return r.ytp ?? Infinity;
  if (k === 'crack') return -r.crack;
  if (k === 'flood') return -(r.hz ? (r.flood ?? 0) : -1);
  if (k === 'cost') return -(r.cost ?? -1);
  return -(r.aadt ?? -1);
}

/** The ranked work list: fix now, within a year, within five. */
export function WorkQueue({
  rows,
  scope,
  stats,
  filters,
  mode,
  selectedId,
  onPick,
  onAdd,
  busy,
}: {
  rows: Row[] | null;
  /** What `rows` covers, for the caption. */
  scope: { county: string | null; perTier: number | null };
  stats: Stats | null;
  filters: Filters;
  mode: Mode;
  selectedId: string | null;
  onPick: (row: Row) => void;
  onAdd: (rows: Row[]) => void;
  busy: boolean;
}) {
  const [tier, setTier] = useState<TierIdx>(0);
  const [sort, setSort] = useState<SortKey>('score');
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(PAGE);

  const filtered = useMemo(() => {
    if (!rows) return [];
    // The tier tabs choose the tier here, so the map's tier switches are not applied twice.
    const f = { ...filters, tiers: [true, true, true, true, true] };
    return rows.filter((r) => r.t === tier && passes(r, r.t, f, mode)).sort((a, b) => sortValue(a, sort) - sortValue(b, sort));
  }, [rows, tier, filters, mode, sort]);

  const shown = filtered.slice(0, limit);
  const checkedRows = filtered.filter((r) => checked.has(r.id));
  const total = stats ? (scope.county ? stats.counties[scope.county]?.tiers[tier] : stats.tiers[TIERS[tier].key]) : null;

  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="g-queue">
      <div className="g-queue-bar">
        <div className="g-tabs" role="tablist" aria-label="Repair tier">
          {([0, 1, 2] as TierIdx[]).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tier === t}
              className={tier === t ? 'on' : ''}
              title={TIERS[t].rule}
              onClick={() => {
                setTier(t);
                setLimit(PAGE);
              }}
            >
              <span className="g-dot" style={{ background: rgbCss(TIERS[t].rgb) }} />
              {TIERS[t].label}
              {stats && (
                <em>{fmtInt(scope.county ? (stats.counties[scope.county]?.tiers[t] ?? 0) : stats.tiers[TIERS[t].key])}</em>
              )}
            </button>
          ))}
        </div>
        <label className="g-inline">
          Sort
          <select className="g-select" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <span className="g-queue-note">
          {rows == null
            ? 'Loading…'
            : scope.county
              ? `All ${fmtInt(total ?? 0)} roads in ${stats?.counties[scope.county]?.name ?? ''} County in this tier${filtered.length !== total ? `; ${fmtInt(filtered.length)} match the filters` : ''}.`
              : `Top ${fmtInt(scope.perTier ?? 0)} of ${fmtInt(total ?? 0)} statewide by priority score${filtered.length !== scope.perTier ? `; ${fmtInt(filtered.length)} match the filters` : ''}. Pick a county for its full list.`}
        </span>
        <button type="button" className="g-btn g-btn-primary" disabled={checkedRows.length === 0 || busy} onClick={() => onAdd(checkedRows)}>
          <Plus size={15} /> {busy ? 'Adding…' : `Add ${checkedRows.length || ''} to work order`}
        </button>
      </div>

      <div className="g-table-wrap">
        <table className="g-table">
          <thead>
            <tr>
              <th className="g-c-check">
                <input
                  type="checkbox"
                  aria-label="Select all shown"
                  checked={shown.length > 0 && shown.every((r) => checked.has(r.id))}
                  onChange={(e) => setChecked(e.target.checked ? new Set(shown.map((r) => r.id)) : new Set())}
                />
              </th>
              <th>Road</th>
              <th>County</th>
              <th>Mileposts</th>
              <th className="g-num">Years to Poor</th>
              <th className="g-num">Cracking</th>
              <th className="g-num">Flood</th>
              <th className="g-num">Rating</th>
              <th className="g-num">Traffic / day</th>
              <th>NCDOT treatment</th>
              <th className="g-num">NCDOT cost</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className={r.id === selectedId ? 'sel' : ''} onClick={() => onPick(r)}>
                <td className="g-c-check" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" aria-label={`Select ${routeName(r.id)}`} checked={checked.has(r.id)} onChange={() => toggle(r.id)} />
                </td>
                <td>
                  <strong>{routeName(r.id)}</strong>
                  {!(r.ho & HO_RATE) && <span className="badge badge-in g-badge-s" title="In-sample wear prediction">in-sample</span>}
                </td>
                <td>{countyName(r.id, stats) ?? ''}</td>
                <td>
                  {(r.bmp ?? parseId(r.id).mp).toFixed(2)}
                  {r.emp != null && `–${r.emp.toFixed(2)}`}
                </td>
                <td className="g-num">{fmtYtpShort(r.ytp)}</td>
                <td className="g-num">{fmtPct(r.crack)}</td>
                <td className="g-num">{r.hz && r.flood != null ? r.flood.toFixed(2) : <span className="g-na">not assessed</span>}</td>
                <td className="g-num">{r.rtg != null ? `${r.rtg} (${r.sy})` : ''}</td>
                <td className="g-num">{r.aadt != null ? `${fmtInt(r.aadt)}${r.as === 'estimate' ? ' est.' : ''}` : ''}</td>
                <td className="g-trt">{r.trt ?? ''}</td>
                <td className="g-num">{r.cost != null && r.cost > 0 ? fmtMoney(r.cost) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows != null && filtered.length === 0 && <p className="g-empty-row">No roads in this tier match the current filters.</p>}
        {filtered.length > limit && (
          <button type="button" className="g-btn g-more" onClick={() => setLimit((l) => l + PAGE)}>
            Show {Math.min(PAGE, filtered.length - limit)} more
          </button>
        )}
      </div>
    </div>
  );
}
