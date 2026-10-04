import {
  HO_CRACK,
  HO_FLOOD,
  HO_RATE,
  parseId,
  routeName,
  type Hist,
  type Mode,
  type Pred,
  type RouteClass,
  type TierIdx,
} from '../lib/data';
import type { RoadFilter } from '../lib/layers';

export interface Filters {
  /** One switch per tier, in TIERS order. */
  tiers: boolean[];
  minCrack: number;
  hzOnly: boolean;
  hoOnly: boolean;
  classes: Record<RouteClass, boolean>;
  /** Three-digit county code, or '' for all counties. */
  county: string;
  /** A route label such as "NC 12", or '' for all routes. */
  route: string;
}

export const DEFAULT_FILTERS: Filters = {
  tiers: [true, true, true, true, true],
  minCrack: 0,
  hzOnly: false,
  hoOnly: false,
  classes: { I: true, US: true, NC: true, SR: true },
  county: '',
  route: '',
};

/** Which held-out flag matters depends on what the map is colouring by. */
export function hoBit(mode: Mode): number {
  return mode === 'crack' ? HO_CRACK : mode === 'flood' ? HO_FLOOD : HO_RATE;
}

export function activeFilterCount(f: Filters): number {
  return (
    (f.tiers.every(Boolean) ? 0 : 1) +
    (f.minCrack > 0 ? 1 : 0) +
    (f.hzOnly ? 1 : 0) +
    (f.hoOnly ? 1 : 0) +
    (Object.values(f.classes).every(Boolean) ? 0 : 1) +
    (f.county ? 1 : 0) +
    (f.route ? 1 : 0)
  );
}

/** One test for map roads and list rows alike. */
export function passes(p: Pred, tier: TierIdx, f: Filters, mode: Mode): boolean {
  if (!f.tiers[tier]) return false;
  if (p.crack < f.minCrack) return false;
  if (f.hzOnly && !p.hz) return false;
  if (f.hoOnly && !(p.ho & hoBit(mode))) return false;
  const { cls, cty } = parseId(p.id);
  if (!f.classes[cls]) return false;
  if (f.county && cty !== f.county) return false;
  if (f.route && routeName(p.id) !== f.route) return false;
  return true;
}

export function mapFilter(f: Filters, mode: Mode): RoadFilter | null {
  if (activeFilterCount(f) === 0) return null;
  return { key: JSON.stringify([f, f.hoOnly ? hoBit(mode) : 0]), test: (s) => passes(s, s.tier, f, mode) };
}

/** "nc12", "NC-12", "i 40", "us 70", "sr2748" -> "NC 12", "I-40", "US 70", "SR 2748". null when it is not a route. */
export function parseRouteQuery(q: string): { label: string; cls: RouteClass; num: number } | null {
  const m = q.trim().toUpperCase().match(/^(I|US|NC|SR)[\s-]*0*(\d{1,5})$/);
  if (!m) return null;
  const cls = m[1] as RouteClass;
  const num = parseInt(m[2], 10);
  return { label: cls === 'I' ? `I-${num}` : `${cls} ${num}`, cls, num };
}

/** Roads at or under a value. The build script bins these so the sum is exact at bin edges. */
export function countAtMost(h: Hist, x: number): number {
  const k = Math.min(h.counts.length - 1, Math.round(x / h.step));
  let n = 0;
  for (let i = 0; i <= k; i++) n += h.counts[i];
  return n;
}

export function countAtLeast(h: Hist, x: number): number {
  const k = Math.max(0, Math.round(x / h.step));
  let n = 0;
  for (let i = k; i < h.counts.length; i++) n += h.counts[i];
  return n;
}
