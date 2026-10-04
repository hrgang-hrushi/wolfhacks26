/**
 * Shared data layer for both dashboards.
 *
 * Everything here reads the static files written by scripts/build_web_data.py
 * into web/public/data/. There is no backend. Tier thresholds and score weights
 * live in priority.json, which the build script reads too.
 */
import priority from './priority.json';
import { getScoreRGB } from '../utils/colors';

export const PRIORITY = priority;
export const DATA_BASE = `${import.meta.env.BASE_URL}data`;

// ------------------------------------------------------------------ types

export type RGBA = [number, number, number, number];
export type Bounds = [west: number, south: number, east: number, north: number];
export type RouteClass = 'I' | 'US' | 'NC' | 'SR';
export type Mode = 'ytp' | 'crack' | 'flood' | 'tier';
export type TierIdx = 0 | 1 | 2 | 3 | 4;

/** Held-out bits in `ho`: the prediction came from a model that never saw this road. */
export const HO_RATE = 1;
export const HO_CRACK = 2;
export const HO_FLOOD = 4;

/** The prediction fields every road carries. */
export interface Pred {
  id: string;
  /** Predicted rating points lost per year. Can be slightly negative; clamp for display. */
  rate: number;
  /** Years until the rating drops below 60, capped at 50. null = no estimate. */
  ytp: number | null;
  /** Probability of cracking above 10%. */
  crack: number;
  /** Helene-style flood-failure score. Present only inside the Helene zone. */
  flood?: number;
  hz: 0 | 1;
  ho: number;
}

/** Real NCDOT record fields, joined at build time. Any of them can be absent. */
export interface Detail {
  bmp?: number;
  emp?: number;
  /** Length in miles. */
  len?: number;
  fr?: string;
  to?: string;
  /** NCDOT pavement rating, 0 to 100, as surveyed. */
  rtg?: number;
  /** Survey year of that rating. */
  sy?: number;
  /** Year last resurfaced. */
  ry?: number;
  ln?: number;
  /** NCDOT's recommended treatment and its cost estimate. */
  trt?: string;
  cost?: number;
  aadt?: number;
  as?: 'count' | 'estimate';
}

const DETAIL_KEYS = ['bmp', 'emp', 'len', 'fr', 'to', 'rtg', 'sy', 'ry', 'ln', 'trt', 'cost', 'aadt', 'as'] as const;

/** Just the NCDOT record fields of a list row. */
export function detailOf(r: Detail): Detail {
  const out: Record<string, unknown> = {};
  for (const k of DETAIL_KEYS) if (r[k] != null) out[k] = r[k];
  return out as Detail;
}

/** A road on the map. */
export interface Seg extends Pred {
  /** One flat [lng, lat, lng, lat, ...] array per part (almost always one part). */
  paths: number[][];
  bbox: Bounds;
  tier: TierIdx;
  score: number;
  cls: RouteClass;
  cty: string;
}

/** A road in a list (work queue, storm list, backtest). */
export interface Row extends Pred, Detail {
  t: TierIdx;
  s: number;
  c: [number, number];
  rank?: number;
  failed?: 0 | 1;
  path?: number[] | number[][];
}

/** What deck.gl draws: one item per line part. */
export interface PathItem {
  seg: Seg;
  path: number[];
}

export interface Shard {
  cell: string;
  segs: Seg[];
  items: PathItem[];
}

export interface CountyInfo {
  name: string;
  n: number;
  tiers: number[];
  hz: number;
  hf: number;
  b: Bounds;
}

export interface Hist {
  step: number;
  counts: number[];
}

export interface MetricRow {
  label: string;
  no_model: number;
  baseline: number;
  with_terrain: number;
}

export interface Stats {
  generated: string;
  version: string;
  source: string;
  total: number;
  has_join: boolean;
  tiers: Record<TierKey, number>;
  classes: Record<RouteClass, number>;
  helene: { zone: number; high_flood: number };
  heldout: { rate: number; crack: number; flood: number };
  no_ytp: number;
  avg: { rate: number; ytp_median: number; crack: number };
  hist: { ytp: Hist; crack: Hist; flood_zone: Hist };
  cell_deg: number;
  cells: Record<string, { n: number; gz: number }>;
  counties: Record<string, CountyInfo>;
  backtest: BacktestSummary | null;
  featured: Featured | null;
  readme_metrics: {
    source: string;
    wear_mae: MetricRow;
    crack_aucpr: MetricRow;
    helene_top50: MetricRow;
  };
  files: { overview_n: number; ranked_per_tier: number; storm_n: number };
}

export interface BacktestSummary {
  n: number;
  damaged: number;
  zone_roads: number;
  zone_damaged: number;
  expected_by_chance: number;
}

export interface Backtest extends BacktestSummary {
  rows: Row[];
}

export interface Featured {
  id: string;
  c: [number, number];
  path: number[];
  readme: {
    source: string;
    rating: number;
    survey_year: number;
    resurfaced: number;
    aadt: number;
    wear_actual: number;
    wear_predicted: number;
    years_to_poor: number;
    crack_top_pct: number;
    length_mi: number;
  };
  data: Detail & { rate: number; ytp: number | null; crack: number; crack_top_pct: number };
}

export interface CountyFile {
  code: string;
  name: string;
  rows: Row[];
  /** SR number -> bounds of that road inside this county. */
  sr: Record<string, Bounds>;
}

export interface RoutesFile {
  /** "I-40", "US 70", "NC 12" -> statewide bounds and segment count. */
  primary: Record<string, { b: Bounds; n: number }>;
  /** SR number -> space-separated county codes that have a road with that number. */
  sr: Record<string, string>;
}

// ------------------------------------------------------------------ tiers

export type TierKey = 'fix_now' | 'within_year' | 'within_five' | 'monitor' | 'no_estimate';

const T = priority.tiers;

export const TIERS: { key: TierKey; label: string; short: string; rule: string; rgb: [number, number, number] }[] = [
  {
    key: 'fix_now',
    label: 'Fix now',
    short: 'Now',
    rule: `Reaches Poor within ${T.fix_now.ytp_max} year, or cracking risk at least ${pct0(T.fix_now.crack_min)}, or (Helene zone) flood score at least ${T.fix_now.flood_min}`,
    rgb: [220, 38, 38],
  },
  {
    key: 'within_year',
    label: 'Fix within a year',
    short: '1 yr',
    rule: `Reaches Poor within ${T.within_year.ytp_max} years, or cracking risk at least ${pct0(T.within_year.crack_min)}`,
    rgb: [234, 108, 12],
  },
  {
    key: 'within_five',
    label: 'Plan within five years',
    short: '5 yr',
    rule: `Reaches Poor within ${T.within_five.ytp_max} years`,
    rgb: [217, 158, 11],
  },
  { key: 'monitor', label: 'Monitor', short: 'Monitor', rule: 'Everything else with an estimate', rgb: [22, 163, 106] },
  {
    key: 'no_estimate',
    label: 'No estimate',
    short: 'None',
    rule: 'No years-to-Poor estimate (rating out of date) and no other trigger',
    rgb: [148, 163, 184],
  },
];

function pct0(v: number): string {
  return `${Math.round(v * 100)}%`;
}

/** Mirrors tier_index() in scripts/build_web_data.py. */
export function tierOf(p: Pred): TierIdx {
  const has = p.ytp != null;
  const ytp = p.ytp ?? Infinity;
  const flood = p.hz ? (p.flood ?? 0) : 0;
  if ((has && ytp <= T.fix_now.ytp_max) || p.crack >= T.fix_now.crack_min || (p.hz === 1 && flood >= T.fix_now.flood_min))
    return 0;
  if ((has && ytp <= T.within_year.ytp_max) || p.crack >= T.within_year.crack_min) return 1;
  if (has && ytp <= T.within_five.ytp_max) return 2;
  return has ? 3 : 4;
}

/** Mirrors priority_score() in scripts/build_web_data.py. 0 to 1, higher = more urgent. */
export function scoreOf(p: Pred): number {
  const s = priority.score;
  const h = s.ytp_horizon_years;
  const ytpPart = p.ytp == null ? 0 : 1 - Math.min(p.ytp, h) / h;
  const floodPart = p.hz ? (p.flood ?? 0) : 0;
  return s.w_ytp * ytpPart + s.w_crack * p.crack + s.w_flood * floodPart;
}

// ------------------------------------------------------------------ ids and labels

const CLASS_BY_DIGIT: Record<string, RouteClass> = { '1': 'I', '2': 'US', '3': 'NC', '4': 'SR' };
export const CLASS_LABEL: Record<RouteClass, string> = { I: 'Interstate', US: 'US route', NC: 'NC route', SR: 'Secondary road' };

/** seg_id is `ncdot:<ROUTE 8 chars><county 3 digits>:<begin milepost>`. */
export function parseId(id: string): { route: string; cls: RouteClass; num: number; cty: string; mp: number } {
  const route = id.slice(6, 14);
  return {
    route,
    cls: CLASS_BY_DIGIT[route[0]] ?? 'SR',
    num: parseInt(route.slice(3), 10),
    cty: id.slice(14, 17),
    mp: parseFloat(id.slice(18)),
  };
}

/** "NC 12", "I-40", "SR 2748": route class and number, which is all the route code tells us for certain. */
export function routeName(id: string): string {
  const { cls, num } = parseId(id);
  return cls === 'I' ? `I-${num}` : `${cls} ${num}`;
}

/** "NC 12, mp 0.20" */
export function roadLabel(id: string): string {
  return `${routeName(id)}, mp ${parseId(id).mp.toFixed(2)}`;
}

export function countyName(id: string, stats: Stats | null): string | null {
  return stats?.counties[parseId(id).cty]?.name ?? null;
}

// ------------------------------------------------------------------ formatting

export function fmtInt(n: number): string {
  return n.toLocaleString('en-US');
}

export function fmtPct(v: number, digits = 0): string {
  return `${(v * 100).toFixed(digits)}%`;
}

/** Years to Poor in plain words. */
export function fmtYtp(ytp: number | null): string {
  if (ytp == null) return 'No estimate';
  if (ytp >= 50) return '50+ years';
  if (ytp < 0.05) return 'Already Poor';
  if (ytp < 1) return 'Under 1 year';
  return `${ytp.toFixed(ytp < 10 ? 1 : 0)} years`;
}

export function fmtYtpShort(ytp: number | null): string {
  if (ytp == null) return 'n/a';
  if (ytp >= 50) return '50+';
  return ytp.toFixed(ytp < 10 ? 1 : 0);
}

/** Wear rate, clamped at zero: a negative prediction means "not measurably wearing". */
export function fmtRate(rate: number): string {
  return `${Math.max(0, rate).toFixed(2)} pts/yr`;
}

export function fmtMoney(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 10_000) return `$${Math.round(v / 1000)}k`;
  return `$${fmtInt(Math.round(v))}`;
}

export function fmtMiles(v: number): string {
  return `${v.toFixed(v < 10 ? 2 : 1)} mi`;
}

/** Why a road has no years-to-Poor estimate, from its own record. */
export function noEstimateReason(d: Detail | null): string {
  if (d?.rtg === 0) return 'Its rating is 0, so there is nothing left to count down.';
  if (d?.ry != null && d.sy != null && d.ry > d.sy)
    return `It was resurfaced in ${d.ry}, after its ${d.sy} inspection, so the rating describes the old surface.`;
  return 'Its rating is out of date (resurfaced after the last inspection).';
}

// ------------------------------------------------------------------ colours

const GREY: [number, number, number] = [148, 163, 184];

/** 0 = worst (crimson), 1 = best (emerald), or null for "no value to show". */
export function conditionScore(p: Pred, mode: Mode): number | null {
  if (mode === 'ytp') return p.ytp == null ? null : Math.sqrt(Math.min(p.ytp, 30) / 30);
  if (mode === 'crack') return 1 - Math.min(p.crack / T.fix_now.crack_min, 1);
  if (mode === 'flood') return p.hz && p.flood != null ? 1 - Math.min(1, Math.sqrt(p.flood / T.fix_now.flood_min)) : null;
  return null;
}

export function segRGB(p: Pred & { tier?: TierIdx }, mode: Mode): [number, number, number] {
  if (mode === 'tier') return TIERS[p.tier ?? tierOf(p)].rgb;
  const s = conditionScore(p, mode);
  return s == null ? GREY : getScoreRGB(s);
}

/** Bad roads are opaque and thick, good roads recede, so the eye lands on the work. */
export function segColor(p: Pred & { tier?: TierIdx }, mode: Mode): RGBA {
  const [r, g, b] = segRGB(p, mode);
  if (mode === 'tier') {
    const t = p.tier ?? tierOf(p);
    return [r, g, b, t <= 2 ? 240 : 110];
  }
  const s = conditionScore(p, mode);
  if (s == null) return [r, g, b, mode === 'flood' ? 45 : 120];
  return [r, g, b, Math.round(250 - 130 * s)];
}

export function segWidth(p: Pred & { tier?: TierIdx }, mode: Mode): number {
  if (mode === 'tier') return [4, 3.2, 2.6, 1.4, 1.4][p.tier ?? tierOf(p)];
  const s = conditionScore(p, mode);
  if (s == null) return 1.2;
  return 1.4 + 2.8 * (1 - s);
}

export function rgbCss([r, g, b]: [number, number, number], a = 1): string {
  return a === 1 ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${a})`;
}

export interface LegendSpec {
  title: string;
  stops: { label: string; rgb: [number, number, number] }[];
  note?: string;
}

export function legendFor(mode: Mode): LegendSpec {
  const at = (p: Partial<Pred>) =>
    segRGB({ id: '', rate: 0, ytp: 50, crack: 0, hz: 1, ho: 0, flood: 0, ...p } as Pred, mode);
  if (mode === 'ytp')
    return {
      title: 'Years until Poor',
      stops: [0, 2, 5, 10, 20, 30].map((y) => ({ label: y === 30 ? '30+' : String(y), rgb: at({ ytp: y }) })),
      note: 'Grey: no estimate',
    };
  if (mode === 'crack')
    return {
      title: 'Cracking risk',
      stops: [0.6, 0.4, 0.2, 0.1, 0].map((c) => ({ label: c === 0.6 ? '60%+' : pct0(c), rgb: at({ crack: c }) })),
    };
  if (mode === 'flood')
    return {
      title: 'Flood-failure score',
      stops: [0.5, 0.2, 0.05, 0.01, 0].map((f) => ({ label: f === 0.5 ? '0.5+' : String(f), rgb: at({ flood: f }) })),
      note: 'Faint grey: outside the Helene zone, not assessed',
    };
  return { title: 'Repair tier', stops: TIERS.map((t) => ({ label: t.short, rgb: t.rgb })) };
}

// ------------------------------------------------------------------ geometry

const Q = 100_000;

/** Undo the build script's encoding: first pair absolute (degrees * 1e5), the rest deltas. */
export function decodePath(a: number[]): number[] {
  const out = new Array<number>(a.length);
  let x = 0;
  let y = 0;
  for (let i = 0; i < a.length; i += 2) {
    x += a[i];
    y += a[i + 1];
    out[i] = x / Q;
    out[i + 1] = y / Q;
  }
  return out;
}

export function decodePaths(p: number[] | number[][] | undefined): number[][] {
  if (!p || p.length === 0) return [];
  return typeof p[0] === 'number' ? [decodePath(p as number[])] : (p as number[][]).map(decodePath);
}

export function pathsBounds(paths: number[][]): Bounds {
  let w = 180;
  let s = 90;
  let e = -180;
  let n = -90;
  for (const p of paths)
    for (let i = 0; i < p.length; i += 2) {
      if (p[i] < w) w = p[i];
      if (p[i] > e) e = p[i];
      if (p[i + 1] < s) s = p[i + 1];
      if (p[i + 1] > n) n = p[i + 1];
    }
  return [w, s, e, n];
}

export function midOf(paths: number[][]): [number, number] {
  const p = paths[0];
  const i = Math.floor(p.length / 4) * 2;
  return [p[i], p[i + 1]];
}

export function boundsIntersect(a: Bounds, b: Bounds): boolean {
  return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
}

function segmentHitsBox(x1: number, y1: number, x2: number, y2: number, b: Bounds): boolean {
  // Liang-Barsky clip of one line piece against the box.
  let t0 = 0;
  let t1 = 1;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const p = [-dx, dx, -dy, dy];
  const q = [x1 - b[0], b[2] - x1, y1 - b[1], b[3] - y1];
  for (let i = 0; i < 4; i++) {
    if (p[i] === 0) {
      if (q[i] < 0) return false;
    } else {
      const r = q[i] / p[i];
      if (p[i] < 0) {
        if (r > t1) return false;
        if (r > t0) t0 = r;
      } else {
        if (r < t0) return false;
        if (r < t1) t1 = r;
      }
    }
  }
  return true;
}

/** True when any part of the road passes through the box. */
export function segInBox(seg: { paths: number[][]; bbox: Bounds }, box: Bounds): boolean {
  if (!boundsIntersect(seg.bbox, box)) return false;
  for (const p of seg.paths)
    for (let i = 0; i + 3 < p.length; i += 2) if (segmentHitsBox(p[i], p[i + 1], p[i + 2], p[i + 3], box)) return true;
  return false;
}

/** Rough distance in metres from a point to the nearest vertex of a road. */
export function distanceToSeg(lng: number, lat: number, seg: { paths: number[][] }): number {
  const kx = 111_320 * Math.cos((lat * Math.PI) / 180);
  const ky = 110_540;
  let best = Infinity;
  for (const p of seg.paths)
    for (let i = 0; i + 3 < p.length; i += 2) {
      const ax = (p[i] - lng) * kx;
      const ay = (p[i + 1] - lat) * ky;
      const bx = (p[i + 2] - lng) * kx;
      const by = (p[i + 3] - lat) * ky;
      const dx = bx - ax;
      const dy = by - ay;
      const len2 = dx * dx + dy * dy;
      const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2));
      const d = Math.hypot(ax + t * dx, ay + t * dy);
      if (d < best) best = d;
    }
  return best;
}

// ------------------------------------------------------------------ loading

interface RawSeg extends Pred {
  path?: number[];
  paths?: number[][];
}

function hydrate(raw: RawSeg): Seg {
  const paths = decodePaths(raw.paths ?? raw.path);
  const { cls, cty } = parseId(raw.id);
  const seg: Seg = {
    id: raw.id,
    rate: raw.rate,
    ytp: raw.ytp ?? null,
    crack: raw.crack,
    hz: raw.hz,
    ho: raw.ho,
    paths,
    bbox: pathsBounds(paths),
    tier: 3,
    score: 0,
    cls,
    cty,
  };
  if (raw.flood != null) seg.flood = raw.flood;
  seg.tier = tierOf(seg);
  seg.score = scoreOf(seg);
  return seg;
}

function toShard(cell: string, raws: RawSeg[]): Shard {
  const segs = raws.map(hydrate);
  const items: PathItem[] = [];
  for (const seg of segs) for (const path of seg.paths) items.push({ seg, path });
  return { cell, segs, items };
}

let dataVersion = '';

async function getJson<T>(path: string): Promise<T> {
  const url = `${DATA_BASE}/${path}${dataVersion ? `?v=${dataVersion}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

let statsPromise: Promise<Stats> | null = null;
export function loadStats(): Promise<Stats> {
  statsPromise ??= getJson<Stats>('stats.json').then((s) => {
    dataVersion = s.version;
    return s;
  });
  return statsPromise;
}

const MAX_CACHED_SHARDS = 96;
const shardCache = new Map<string, Promise<Shard>>();

export function loadShard(cell: string): Promise<Shard> {
  let p = shardCache.get(cell);
  if (p) {
    shardCache.delete(cell); // re-insert so the map stays in least-recently-used order
    shardCache.set(cell, p);
    return p;
  }
  p = getJson<{ cell: string; segs: RawSeg[] }>(`shards/${cell}.json`).then((j) => toShard(cell, j.segs));
  p.catch(() => shardCache.delete(cell));
  shardCache.set(cell, p);
  if (shardCache.size > MAX_CACHED_SHARDS) {
    const oldest = shardCache.keys().next().value;
    if (oldest !== undefined) shardCache.delete(oldest);
  }
  return p;
}

let overviewPromise: Promise<Shard> | null = null;
export function loadOverview(): Promise<Shard> {
  overviewPromise ??= getJson<{ segs: RawSeg[] }>('overview.json').then((j) => toShard('overview', j.segs));
  overviewPromise.catch(() => (overviewPromise = null));
  return overviewPromise;
}

const detailCache = new Map<string, Promise<Record<string, Detail>>>();
/** NCDOT record fields for one road. Resolves to null when the join was not built. */
export async function loadDetail(seg: { id: string; paths: number[][] }, stats: Stats): Promise<Detail | null> {
  if (!stats.has_join) return null;
  const candidates = cellsNear(seg, stats);
  for (const cell of candidates) {
    let p = detailCache.get(cell);
    if (!p) {
      p = getJson<Record<string, Detail>>(`detail/${cell}.json`);
      p.catch(() => detailCache.delete(cell));
      detailCache.set(cell, p);
    }
    try {
      const d = (await p)[seg.id];
      if (d) return d;
    } catch {
      /* try the next candidate */
    }
  }
  return null;
}

const onceCache = new Map<string, Promise<unknown>>();
function once<T>(path: string): Promise<T> {
  let p = onceCache.get(path) as Promise<T> | undefined;
  if (!p) {
    p = getJson<T>(path);
    p.catch(() => onceCache.delete(path));
    onceCache.set(path, p);
  }
  return p;
}

export const loadRanked = () => once<{ per_tier: number; rows: Row[] }>('ranked.json');
export const loadStorm = () => once<{ n_zone: number; min_flood: number; rows: Row[] }>('storm.json');
export const loadBacktest = () => once<Backtest>('backtest.json');
export const loadRoutes = () => once<RoutesFile>('routes.json');
export const loadCounty = (code: string) => once<CountyFile>(`county/${code}.json`);

// ------------------------------------------------------------------ shard grid

/** Shard a point falls in. Same arithmetic as cell_key() in the build script. */
export function cellOf(lng: number, lat: number, deg = 0.25): string {
  return `${Math.floor((lng + 180) / deg)}_${Math.floor((lat + 90) / deg)}`;
}

/** Existing shards a bounding box touches, nearest to its centre first. */
export function cellsForBounds(b: Bounds, stats: Stats, pad = 0.02): string[] {
  const deg = stats.cell_deg;
  const x0 = Math.floor((b[0] - pad + 180) / deg);
  const x1 = Math.floor((b[2] + pad + 180) / deg);
  const y0 = Math.floor((b[1] - pad + 90) / deg);
  const y1 = Math.floor((b[3] + pad + 90) / deg);
  if ((x1 - x0 + 1) * (y1 - y0 + 1) > 2000) return Object.keys(stats.cells);
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const out: { k: string; d: number }[] = [];
  for (let x = x0; x <= x1; x++)
    for (let y = y0; y <= y1; y++) {
      const k = `${x}_${y}`;
      if (stats.cells[k]) out.push({ k, d: Math.hypot(x - cx, y - cy) });
    }
  return out.sort((a, c) => a.d - c.d).map((o) => o.k);
}

/** The shard holding a road's midpoint, then its neighbours (the build bins by exact midpoint). */
function cellsNear(seg: { paths: number[][] }, stats: Stats): string[] {
  const b = pathsBounds(seg.paths);
  return cellsForBounds(b, stats, 0);
}

/** Turn a list row (work queue, storm list, backtest) into something the map can draw. */
export function rowToSeg(row: Row): Seg | null {
  const paths = decodePaths(row.path);
  if (paths.length === 0) return null;
  const { cls, cty } = parseId(row.id);
  const seg: Seg = {
    id: row.id,
    rate: row.rate,
    ytp: row.ytp ?? null,
    crack: row.crack,
    hz: row.hz,
    ho: row.ho,
    paths,
    bbox: pathsBounds(paths),
    tier: row.t,
    score: row.s,
    cls,
    cty,
  };
  if (row.flood != null) seg.flood = row.flood;
  return seg;
}

/** Find a road's geometry by id, loading the shard around a known point. */
export async function findSeg(id: string, near: [number, number], stats: Stats): Promise<Seg | null> {
  const d = stats.cell_deg;
  const cells = cellsForBounds([near[0] - d / 2, near[1] - d / 2, near[0] + d / 2, near[1] + d / 2], stats, 0);
  const home = cellOf(near[0], near[1], d);
  const ordered = [home, ...cells.filter((c) => c !== home)].filter((c) => stats.cells[c]);
  for (const cell of ordered) {
    try {
      const shard = await loadShard(cell);
      const hit = shard.segs.find((s) => s.id === id);
      if (hit) return hit;
    } catch {
      /* next */
    }
  }
  return null;
}
