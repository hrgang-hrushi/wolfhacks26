import { useEffect, useRef, useState } from 'react';
import { Search, SlidersHorizontal, X } from 'lucide-react';
import { CLASS_LABEL, TIERS, fmtPct, rgbCss, type Mode, type RouteClass, type Stats } from '../lib/data';
import { DEFAULT_FILTERS, activeFilterCount, type Filters } from './filters';

const MODES: { key: Mode; label: string }[] = [
  { key: 'ytp', label: 'Years to Poor' },
  { key: 'crack', label: 'Cracking risk' },
  { key: 'flood', label: 'Flood risk (Helene zone)' },
  { key: 'tier', label: 'Priority tier' },
];

export function LayerSwitch({ mode, onMode }: { mode: Mode; onMode: (m: Mode) => void }) {
  return (
    <div className="g-layers" role="radiogroup" aria-label="Colour the map by">
      {MODES.map((m) => (
        <button key={m.key} type="button" role="radio" aria-checked={mode === m.key} className={mode === m.key ? 'on' : ''} onClick={() => onMode(m.key)}>
          {m.label}
        </button>
      ))}
    </div>
  );
}

export function CountySelect({ stats, value, onChange }: { stats: Stats | null; value: string; onChange: (code: string) => void }) {
  const list = stats ? Object.entries(stats.counties).sort((a, b) => a[1].name.localeCompare(b[1].name)) : [];
  return (
    <select className="g-select g-county" value={value} onChange={(e) => onChange(e.target.value)} aria-label="County">
      <option value="">All 100 counties</option>
      {list.map(([code, c]) => (
        <option key={code} value={code}>
          {c.name}
        </option>
      ))}
    </select>
  );
}

export function SearchBox({
  onSearch,
  message,
  choices,
  onChoose,
  inputRef,
  routeActive,
}: {
  onSearch: (q: string) => void;
  message: string | null;
  /** County choices when an SR number exists in several counties. */
  choices: { code: string; name: string }[] | null;
  onChoose: (code: string) => void;
  inputRef?: React.Ref<HTMLInputElement>;
  /** A route filter is on. When it is cleared elsewhere (a chip), the box empties too. */
  routeActive: boolean;
}) {
  const [q, setQ] = useState('');
  const [hadRoute, setHadRoute] = useState(routeActive);
  if (hadRoute !== routeActive) {
    setHadRoute(routeActive);
    if (!routeActive) setQ('');
  }
  const clear = () => {
    setQ('');
    onSearch('');
  };
  return (
    <div className="g-search-wrap">
      <form
        className="g-search"
        onSubmit={(e) => {
          e.preventDefault();
          onSearch(q);
        }}
      >
        <Search size={15} />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              clear();
              e.currentTarget.blur();
            }
          }}
          placeholder="Find a route: NC 12, I-40, SR 2748"
          aria-label="Find a route or county (press / to focus)"
        />
        {(q || message || choices) && (
          <button type="button" className="g-x" aria-label="Clear the search" title="Clear the search" onClick={clear}>
            <X size={14} />
          </button>
        )}
      </form>
      {(message || choices) && (
        <div className="g-pop g-search-pop">
          {message && <p>{message}</p>}
          {choices && (
            <ul>
              {choices.map((c) => (
                <li key={c.code}>
                  <button type="button" onClick={() => onChoose(c.code)}>
                    {c.name} County
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function FilterButton({ filters, onChange, mode }: { filters: Filters; onChange: (f: Filters) => void; mode: Mode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const n = activeFilterCount(filters);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  return (
    <div className="g-filter-wrap" ref={ref}>
      <button type="button" className={`g-btn ${n ? 'g-btn-on' : ''}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <SlidersHorizontal size={14} /> Filters{n ? ` (${n})` : ''}
      </button>
      {open && (
        <div className="g-pop g-filter-pop">
          <fieldset>
            <legend>Repair tier</legend>
            {TIERS.map((t, i) => (
              <label key={t.key} className="g-check">
                <input
                  type="checkbox"
                  checked={filters.tiers[i]}
                  onChange={(e) => onChange({ ...filters, tiers: filters.tiers.map((v, j) => (j === i ? e.target.checked : v)) })}
                />
                <span className="g-dot" style={{ background: rgbCss(t.rgb) }} />
                {t.label}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Route class</legend>
            {(Object.keys(CLASS_LABEL) as RouteClass[]).map((c) => (
              <label key={c} className="g-check">
                <input
                  type="checkbox"
                  checked={filters.classes[c]}
                  onChange={(e) => onChange({ ...filters, classes: { ...filters.classes, [c]: e.target.checked } })}
                />
                {CLASS_LABEL[c]}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>
              Cracking probability at least <strong>{fmtPct(filters.minCrack)}</strong>
            </legend>
            <input type="range" min={0} max={0.9} step={0.05} value={filters.minCrack} onChange={(e) => onChange({ ...filters, minCrack: Number(e.target.value) })} aria-label="Minimum cracking probability" />
          </fieldset>
          <fieldset>
            <label className="g-check">
              <input type="checkbox" checked={filters.hzOnly} onChange={(e) => onChange({ ...filters, hzOnly: e.target.checked })} />
              Helene zone only
            </label>
            <label className="g-check">
              <input type="checkbox" checked={filters.hoOnly} onChange={(e) => onChange({ ...filters, hoOnly: e.target.checked })} />
              Held-out predictions only ({mode === 'crack' ? 'cracking' : mode === 'flood' ? 'flood' : 'wear'})
            </label>
          </fieldset>
          <button type="button" className="g-btn" onClick={() => onChange({ ...DEFAULT_FILTERS, county: filters.county })}>
            Reset filters
          </button>
        </div>
      )}
    </div>
  );
}

export function FilterChips({ filters, onChange, stats }: { filters: Filters; onChange: (f: Filters) => void; stats: Stats | null }) {
  const chips: { label: string; clear: Filters }[] = [];
  if (filters.route) chips.push({ label: `Route: ${filters.route}`, clear: { ...filters, route: '' } });
  if (filters.county) chips.push({ label: `${stats?.counties[filters.county]?.name ?? filters.county} County`, clear: { ...filters, county: '' } });
  if (filters.hzOnly) chips.push({ label: 'Helene zone only', clear: { ...filters, hzOnly: false } });
  if (filters.hoOnly) chips.push({ label: 'Held-out only', clear: { ...filters, hoOnly: false } });
  if (filters.minCrack > 0) chips.push({ label: `Cracking ≥ ${fmtPct(filters.minCrack)}`, clear: { ...filters, minCrack: 0 } });
  if (!filters.tiers.every(Boolean)) chips.push({ label: 'Some tiers hidden', clear: { ...filters, tiers: DEFAULT_FILTERS.tiers } });
  if (!Object.values(filters.classes).every(Boolean)) chips.push({ label: 'Some route classes hidden', clear: { ...filters, classes: DEFAULT_FILTERS.classes } });
  if (chips.length === 0) return null;
  return (
    <div className="g-chips">
      {chips.map((c) => (
        <button key={c.label} type="button" className="g-chip" onClick={() => onChange(c.clear)}>
          {c.label} <X size={12} />
        </button>
      ))}
      {chips.length > 1 && (
        <button type="button" className="g-chip g-chip-ghost" onClick={() => onChange(DEFAULT_FILTERS)}>
          Clear all
        </button>
      )}
    </div>
  );
}
