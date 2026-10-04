/** Layout controls for /gov: the draggable dividers between panels and the display settings menu. */
import { useEffect, useRef, useState } from 'react';
import { Monitor, Moon, RotateCcw, Settings, Sun } from 'lucide-react';
import { COLUMN_LABEL, GOV_DEFAULTS, KPI_KEYS, QUEUE_COLUMNS, type GovPrefs, type KpiKey, type ThemePref } from '../lib/prefs';

const STEP = 24;

/**
 * A divider the user drags (or moves with the arrow keys) to resize the panel after it.
 * While dragging it calls onDrag on every move, so the caller can resize without re-rendering,
 * and onCommit once at the end.
 */
export function Splitter({
  axis,
  label,
  size,
  limits,
  onDrag,
  onCommit,
  onReset,
}: {
  /** 'x' sits between left and right panels, 'y' between top and bottom ones. */
  axis: 'x' | 'y';
  label: string;
  /** The current size, in pixels, of the panel after the divider. */
  size: () => number;
  /** Smallest and largest size allowed right now. */
  limits: () => [number, number];
  onDrag: (px: number) => void;
  onCommit: (px: number) => void;
  onReset: () => void;
}) {
  const [active, setActive] = useState(false);
  const clamp = (v: number) => {
    const [lo, hi] = limits();
    return Math.round(Math.min(Math.max(v, lo), Math.max(lo, hi)));
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    const start = axis === 'x' ? e.clientX : e.clientY;
    const startSize = size();
    let last = startSize;
    setActive(true);
    document.body.style.cursor = axis === 'x' ? 'col-resize' : 'row-resize';
    const move = (ev: PointerEvent) => {
      // The panel sits after the divider, so dragging toward it makes it smaller.
      last = clamp(startSize - ((axis === 'x' ? ev.clientX : ev.clientY) - start));
      onDrag(last);
    };
    const up = () => {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      document.body.style.cursor = '';
      setActive(false);
      if (last !== startSize) onCommit(last);
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const grow = axis === 'x' ? 'ArrowLeft' : 'ArrowUp';
    const shrink = axis === 'x' ? 'ArrowRight' : 'ArrowDown';
    const step = e.shiftKey ? STEP * 4 : STEP;
    if (e.key === grow) onCommit(clamp(size() + step));
    else if (e.key === shrink) onCommit(clamp(size() - step));
    else if (e.key === 'Home') onCommit(clamp(Infinity));
    else if (e.key === 'End') onCommit(clamp(0));
    else if (e.key === 'Enter') onReset();
    else return;
    e.preventDefault();
  };

  return (
    <div
      className={`g-split g-split-${axis} ${active ? 'on' : ''}`}
      role="separator"
      aria-orientation={axis === 'x' ? 'vertical' : 'horizontal'}
      aria-label={label}
      title={`${label}. Drag to resize, double-click to reset.`}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
    />
  );
}

const THEME_CHOICES: { key: ThemePref; label: string; icon: React.ReactNode }[] = [
  { key: 'light', label: 'Light', icon: <Sun size={14} /> },
  { key: 'dark', label: 'Dark', icon: <Moon size={14} /> },
  { key: 'system', label: 'Match device', icon: <Monitor size={14} /> },
];

const KPI_LABEL: Record<KpiKey, string> = {
  total: 'State roads',
  fix_now: 'Fix now',
  within_year: 'Fix within a year',
  within_five: 'Plan within five years',
  high_flood: 'High flood score',
  heldout: 'Held-out share',
  no_ytp: 'No estimate',
};

function toggleIn<T>(list: readonly T[], item: T, on: boolean, order: readonly T[]): T[] {
  const next = new Set(list);
  if (on) next.add(item);
  else next.delete(item);
  return order.filter((k) => next.has(k));
}

/** The rail button that opens the display settings: theme, density, which panels, tiles and columns show. */
export function DisplayMenu({
  prefs,
  onPrefs,
  onReset,
  theme,
  onTheme,
}: {
  prefs: GovPrefs;
  onPrefs: (patch: Partial<GovPrefs>) => void;
  onReset: () => void;
  theme: ThemePref;
  onTheme: (t: ThemePref) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  const changed = JSON.stringify(prefs) !== JSON.stringify(GOV_DEFAULTS);

  return (
    <div className="g-display" ref={ref}>
      <button type="button" className={open ? 'on' : ''} title="Display settings" aria-label="Display settings" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Settings size={20} />
      </button>
      {open && (
        <div className="g-pop g-display-pop" role="dialog" aria-label="Display settings">
          <fieldset>
            <legend>Theme</legend>
            <div className="g-seg" role="radiogroup" aria-label="Theme">
              {THEME_CHOICES.map((t) => (
                <button key={t.key} type="button" role="radio" aria-checked={theme === t.key} className={theme === t.key ? 'on' : ''} onClick={() => onTheme(t.key)}>
                  {t.icon} {t.label}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>Table density</legend>
            <div className="g-seg" role="radiogroup" aria-label="Table density">
              {(['comfortable', 'compact'] as const).map((d) => (
                <button key={d} type="button" role="radio" aria-checked={prefs.density === d} className={prefs.density === d ? 'on' : ''} onClick={() => onPrefs({ density: d })}>
                  {d === 'comfortable' ? 'Comfortable' : 'Compact'}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>Show</legend>
            <div className="g-display-grid">
              {(
                [
                  ['sideOpen', 'Side panel'],
                  ['bottomOpen', 'Bottom panel'],
                  ['showKpis', 'Summary tiles'],
                  ['showLegend', 'Map legend'],
                  ['showHints', 'Map hints'],
                ] as [keyof GovPrefs, string][]
              ).map(([k, label]) => (
                <label key={k} className="g-check">
                  <input type="checkbox" checked={prefs[k] as boolean} onChange={(e) => onPrefs({ [k]: e.target.checked })} />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset disabled={!prefs.showKpis}>
            <legend>Summary tiles</legend>
            <div className="g-display-grid">
              {KPI_KEYS.map((k) => (
                <label key={k} className="g-check">
                  <input type="checkbox" checked={prefs.kpis.includes(k)} onChange={(e) => onPrefs({ kpis: toggleIn(prefs.kpis, k, e.target.checked, KPI_KEYS) })} />
                  {KPI_LABEL[k]}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>Work queue columns</legend>
            <div className="g-display-grid">
              {QUEUE_COLUMNS.map((c) => (
                <label key={c} className="g-check">
                  <input
                    type="checkbox"
                    checked={!prefs.hiddenCols.includes(c)}
                    onChange={(e) => onPrefs({ hiddenCols: toggleIn(prefs.hiddenCols, c, !e.target.checked, QUEUE_COLUMNS) })}
                  />
                  {COLUMN_LABEL[c]}
                </label>
              ))}
            </div>
          </fieldset>

          <p className="fine">
            Drag the dividers between the map and the panels to resize them; double-click a divider to put it back. Keys: <kbd>/</kbd> search,{' '}
            <kbd>1</kbd>–<kbd>4</kbd> map colouring, <kbd>Esc</kbd> clear the selection. Saved in this browser.
          </p>
          <button type="button" className="g-btn" disabled={!changed} onClick={onReset}>
            <RotateCcw size={14} /> Reset layout
          </button>
        </div>
      )}
    </div>
  );
}
