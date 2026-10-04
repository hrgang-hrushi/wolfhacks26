import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Download, Plus } from 'lucide-react';
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
import { COLUMN_LABEL, type QueueColumn } from '../lib/prefs';
import { download, queueCsv } from '../lib/workOrders';
import { passes, type Filters } from './filters';

type SortKey = 'score' | 'ytp' | 'crack' | 'flood' | 'cost' | 'aadt' | 'rating';

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'score', label: 'Priority score' },
  { key: 'ytp', label: 'Soonest to Poor' },
  { key: 'crack', label: 'Cracking risk' },
  { key: 'flood', label: 'Flood score' },
  { key: 'rating', label: 'Lowest rating' },
  { key: 'aadt', label: 'Traffic' },
  { key: 'cost', label: 'NCDOT cost estimate' },
];

const PAGE = 150;

/** Worst first. null when the road has no value for that key, so blanks sort last in either direction. */
function sortValue(r: Row, k: SortKey): number | null {
  if (k === 'score') return -r.s;
  if (k === 'ytp') return r.ytp;
  if (k === 'crack') return -r.crack;
  if (k === 'flood') return r.hz && r.flood != null ? -r.flood : null;
  if (k === 'cost') return r.cost != null && r.cost > 0 ? -r.cost : null;
  if (k === 'rating') return r.rtg ?? null;
  return r.aadt != null ? -r.aadt : null;
}

const COLUMNS: { key: QueueColumn; num?: boolean; sort?: SortKey; cls?: string; cell: (r: Row, stats: Stats | null) => React.ReactNode }[] = [
  { key: 'county', cell: (r, stats) => countyName(r.id, stats) ?? '' },
  {
    key: 'mileposts',
    cell: (r) => (
      <>
        {(r.bmp ?? parseId(r.id).mp).toFixed(2)}
        {r.emp != null && `–${r.emp.toFixed(2)}`}
      </>
    ),
  },
  { key: 'ytp', num: true, sort: 'ytp', cell: (r) => fmtYtpShort(r.ytp) },
  { key: 'crack', num: true, sort: 'crack', cell: (r) => fmtPct(r.crack) },
  { key: 'flood', num: true, sort: 'flood', cell: (r) => (r.hz && r.flood != null ? r.flood.toFixed(2) : <span className="g-na">not assessed</span>) },
  { key: 'rating', num: true, sort: 'rating', cell: (r) => (r.rtg != null ? `${r.rtg}${r.sy != null ? ` (${r.sy})` : ''}` : '') },
  { key: 'aadt', num: true, sort: 'aadt', cell: (r) => (r.aadt != null ? `${fmtInt(r.aadt)}${r.as === 'estimate' ? ' est.' : ''}` : '') },
  { key: 'trt', cls: 'g-trt', cell: (r) => r.trt ?? '' },
  { key: 'cost', num: true, sort: 'cost', cell: (r) => (r.cost != null && r.cost > 0 ? fmtMoney(r.cost) : '') },
];

/** The ranked work list: fix now, within a year, within five. */
export function WorkQueue({
  rows,
  scope,
  stats,
  filters,
  mode,
  selectedId,
  hiddenCols,
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
  /** Columns the user turned off in the display settings. */
  hiddenCols: QueueColumn[];
  onPick: (row: Row) => void;
  onAdd: (rows: Row[]) => void;
  busy: boolean;
}) {
  const [tier, setTier] = useState<TierIdx>(0);
  const [sort, setSort] = useState<SortKey>('score');
  /** false = worst first (the default for every key). */
  const [flip, setFlip] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(PAGE);

  const filtered = useMemo(() => {
    if (!rows) return [];
    // The tier tabs choose the tier here, so the map's tier switches are not applied twice.
    const f = { ...filters, tiers: [true, true, true, true, true] };
    const dir = flip ? -1 : 1;
    return rows
      .filter((r) => r.t === tier && passes(r, r.t, f, mode))
      .sort((a, b) => {
        const x = sortValue(a, sort);
        const y = sortValue(b, sort);
        if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
        return (x - y) * dir;
      });
  }, [rows, tier, filters, mode, sort, flip]);

  const columns = COLUMNS.filter((c) => !hiddenCols.includes(c.key));
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

  const sortBy = (k: SortKey) => {
    if (k === sort) setFlip((f) => !f);
    else {
      setSort(k);
      setFlip(false);
    }
    setLimit(PAGE);
  };

  const exportCsv = () => {
    const where = scope.county ? (stats?.counties[scope.county]?.name ?? scope.county).toLowerCase().replace(/\s+/g, '-') : 'statewide';
    download(`work-queue-${TIERS[tier].key}-${where}.csv`, queueCsv(filtered, stats), 'text/csv');
  };

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
          <select
            className="g-select"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value as SortKey);
              setFlip(false);
              setLimit(PAGE);
            }}
          >
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
        <button type="button" className="g-btn" disabled={filtered.length === 0} onClick={exportCsv} title="Download the rows listed here, as filtered and sorted">
          <Download size={14} /> CSV
        </button>
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
              {columns.map((c) => {
                const on = c.sort != null && c.sort === sort;
                return (
                  <th key={c.key} className={c.num ? 'g-num' : undefined} aria-sort={on ? (flip ? 'ascending' : 'descending') : undefined}>
                    {c.sort ? (
                      <button type="button" className={`g-th-sort ${on ? 'on' : ''}`} onClick={() => sortBy(c.sort!)} title={`Sort by ${COLUMN_LABEL[c.key].toLowerCase()}`}>
                        {COLUMN_LABEL[c.key]}
                        {on && (flip ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
                      </button>
                    ) : (
                      COLUMN_LABEL[c.key]
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr
                key={r.id}
                className={r.id === selectedId ? 'sel' : ''}
                tabIndex={0}
                onClick={() => onPick(r)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.target === e.currentTarget) onPick(r);
                }}
              >
                <td className="g-c-check" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" aria-label={`Select ${routeName(r.id)}`} checked={checked.has(r.id)} onChange={() => toggle(r.id)} />
                </td>
                <td>
                  <strong>{routeName(r.id)}</strong>
                  {!(r.ho & HO_RATE) && <span className="badge badge-in g-badge-s" title="In-sample wear prediction">in-sample</span>}
                </td>
                {columns.map((c) => (
                  <td key={c.key} className={[c.num ? 'g-num' : '', c.cls ?? ''].join(' ').trim() || undefined}>
                    {c.cell(r, stats)}
                  </td>
                ))}
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
