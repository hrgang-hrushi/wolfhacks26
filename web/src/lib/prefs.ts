/**
 * Display preferences kept in this browser: the colour theme (shared by every page) and
 * the /gov layout. Nothing here is sent anywhere. A private window or blocked storage
 * just means the choices last until the tab closes.
 */
import { useCallback, useSyncExternalStore } from 'react';

function readJson(key: string): unknown {
  try {
    const raw = window.localStorage.getItem(key);
    return raw == null ? null : JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage blocked or full: keep the value in memory only
  }
}

/** A small store over one localStorage key. Tabs of the same site stay in step through the storage event. */
function createStore<T extends object>(key: string, defaults: T, clean: (raw: unknown) => T) {
  let value = clean(readJson(key));
  const subs = new Set<() => void>();
  const emit = () => subs.forEach((f) => f());
  window.addEventListener('storage', (e) => {
    if (e.key !== key) return;
    value = clean(readJson(key));
    emit();
  });
  return {
    get: () => value,
    set(patch: Partial<T> | ((prev: T) => Partial<T>)) {
      const next = typeof patch === 'function' ? patch(value) : patch;
      const keys = Object.keys(next) as (keyof T)[];
      if (keys.every((k) => Object.is(value[k], next[k]))) return;
      value = { ...value, ...next };
      writeJson(key, value);
      emit();
    },
    reset() {
      value = { ...defaults };
      writeJson(key, value);
      emit();
    },
    subscribe(f: () => void) {
      subs.add(f);
      return () => {
        subs.delete(f);
      };
    },
  };
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

// ---- colour theme -------------------------------------------------------------------------

export type ThemePref = 'light' | 'dark' | 'system';
export const THEME_KEY = 'ur.theme';
const THEMES: ThemePref[] = ['light', 'dark', 'system'];

const themeStore = createStore<{ pref: ThemePref }>(THEME_KEY, { pref: 'light' }, (raw) => ({
  pref: isRecord(raw) && THEMES.includes(raw.pref as ThemePref) ? (raw.pref as ThemePref) : 'light',
}));

const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
const darkSubs = new Set<() => void>();
darkQuery.addEventListener('change', () => darkSubs.forEach((f) => f()));

function resolveDark(pref: ThemePref): boolean {
  return pref === 'dark' || (pref === 'system' && darkQuery.matches);
}

/** Stamps the choice on <html>, so the stylesheets and the browser chrome follow it. index.html does the same before first paint. */
function applyTheme(): void {
  const dark = resolveDark(themeStore.get().pref);
  const root = document.documentElement;
  root.dataset.theme = dark ? 'dark' : 'light';
  root.style.colorScheme = dark ? 'dark' : 'light';
}
themeStore.subscribe(applyTheme);
darkSubs.add(applyTheme);
applyTheme();

function subscribeTheme(f: () => void): () => void {
  const off = themeStore.subscribe(f);
  darkSubs.add(f);
  return () => {
    off();
    darkSubs.delete(f);
  };
}

export function useTheme(): { pref: ThemePref; dark: boolean; setPref: (p: ThemePref) => void; toggle: () => void } {
  const pref = useSyncExternalStore(subscribeTheme, () => themeStore.get().pref);
  const dark = useSyncExternalStore(subscribeTheme, () => resolveDark(themeStore.get().pref));
  const setPref = useCallback((p: ThemePref) => themeStore.set({ pref: p }), []);
  const toggle = useCallback(() => themeStore.set((prev) => ({ pref: resolveDark(prev.pref) ? 'light' : 'dark' })), []);
  return { pref, dark, setPref, toggle };
}

// ---- /gov layout ----------------------------------------------------------------------------

export const KPI_KEYS = ['total', 'fix_now', 'within_year', 'within_five', 'high_flood', 'heldout', 'no_ytp'] as const;
export type KpiKey = (typeof KPI_KEYS)[number];

export const QUEUE_COLUMNS = ['county', 'mileposts', 'ytp', 'crack', 'flood', 'rating', 'aadt', 'trt', 'cost'] as const;
export type QueueColumn = (typeof QUEUE_COLUMNS)[number];
export const COLUMN_LABEL: Record<QueueColumn, string> = {
  county: 'County',
  mileposts: 'Mileposts',
  ytp: 'Years to Poor',
  crack: 'Cracking',
  flood: 'Flood',
  rating: 'Rating',
  aadt: 'Traffic / day',
  trt: 'NCDOT treatment',
  cost: 'NCDOT cost',
};

export interface GovPrefs {
  /** Side panel width in pixels; null follows the window. */
  sideW: number | null;
  /** Bottom panel height in pixels; null follows the window. */
  bottomH: number | null;
  sideOpen: boolean;
  bottomOpen: boolean;
  density: 'comfortable' | 'compact';
  showKpis: boolean;
  showLegend: boolean;
  showHints: boolean;
  /** Summary tiles to show, in KPI_KEYS order. */
  kpis: KpiKey[];
  /** Work queue columns the user turned off. */
  hiddenCols: QueueColumn[];
}

export const GOV_DEFAULTS: GovPrefs = {
  sideW: null,
  bottomH: null,
  sideOpen: true,
  bottomOpen: true,
  density: 'comfortable',
  showKpis: true,
  showLegend: true,
  showHints: true,
  kpis: ['total', 'fix_now', 'within_year', 'high_flood', 'heldout'],
  hiddenCols: [],
};

function px(v: unknown, lo: number, hi: number): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, Math.round(v))) : null;
}

function pickList<T extends string>(v: unknown, allowed: readonly T[], fallback: T[]): T[] {
  if (!Array.isArray(v)) return fallback;
  return allowed.filter((k) => v.includes(k));
}

/** Stored values come from an older build or a hand-edited store, so every field is checked. */
function cleanGov(raw: unknown): GovPrefs {
  if (!isRecord(raw)) return { ...GOV_DEFAULTS };
  const bool = (k: keyof GovPrefs) => (typeof raw[k] === 'boolean' ? (raw[k] as boolean) : (GOV_DEFAULTS[k] as boolean));
  return {
    sideW: px(raw.sideW, 240, 1200),
    bottomH: px(raw.bottomH, 96, 1200),
    sideOpen: bool('sideOpen'),
    bottomOpen: bool('bottomOpen'),
    density: raw.density === 'compact' ? 'compact' : 'comfortable',
    showKpis: bool('showKpis'),
    showLegend: bool('showLegend'),
    showHints: bool('showHints'),
    kpis: pickList(raw.kpis, KPI_KEYS, GOV_DEFAULTS.kpis),
    hiddenCols: pickList(raw.hiddenCols, QUEUE_COLUMNS, []),
  };
}

const govStore = createStore<GovPrefs>('ur.gov.layout', GOV_DEFAULTS, cleanGov);

export function useGovPrefs(): { prefs: GovPrefs; setPrefs: (patch: Partial<GovPrefs>) => void; resetPrefs: () => void } {
  const prefs = useSyncExternalStore(govStore.subscribe, govStore.get);
  return { prefs, setPrefs: govStore.set, resetPrefs: govStore.reset };
}
