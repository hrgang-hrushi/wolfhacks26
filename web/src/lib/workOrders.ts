/**
 * Work orders and crews for the agency dashboard.
 *
 * This is a demo of the dispatch workflow: it lives in this browser's
 * localStorage, the crews are made up, and nothing is sent anywhere.
 */
import { useSyncExternalStore } from 'react';
import {
  HO_RATE,
  TIERS,
  countyName,
  parseId,
  routeName,
  type Detail,
  type Row,
  type Seg,
  type Stats,
  type TierIdx,
} from './data';

export type OrderStatus = 'Queued' | 'Dispatched' | 'In progress' | 'Done';
export const STATUSES: OrderStatus[] = ['Queued', 'Dispatched', 'In progress', 'Done'];

/** A road as stored on a work order: predictions, record fields and geometry, so exports work offline. */
export interface OrderSeg extends Detail {
  id: string;
  paths: number[][];
  tier: TierIdx;
  rate: number;
  ytp: number | null;
  crack: number;
  flood?: number;
  hz: 0 | 1;
  ho: number;
  county?: string;
}

export interface WorkOrder {
  id: string;
  created: string;
  status: OrderStatus;
  crew: string;
  /** yyyy-mm-dd, or '' when not set. */
  due: string;
  notes: string;
  segs: OrderSeg[];
}

interface State {
  orders: WorkOrder[];
  crews: string[];
}

const KEY = 'unwatched-roads.workorders.v1';
const DEMO_CREWS = ['Demo crew A (patching)', 'Demo crew B (resurfacing)', 'Demo crew C (drainage)', 'Demo crew D (sealing)'];

function read(): State {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) {
      const s = JSON.parse(raw) as Partial<State>;
      if (Array.isArray(s.orders) && Array.isArray(s.crews)) return { orders: s.orders, crews: s.crews };
    }
  } catch {
    /* private mode or corrupt entry: start clean */
  }
  return { orders: [], crews: DEMO_CREWS };
}

let state: State = read();
const listeners = new Set<() => void>();

function commit(next: State): void {
  state = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage full or blocked: keep working in memory */
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useWorkOrders(): State {
  return useSyncExternalStore(subscribe, () => state);
}

function nextId(orders: WorkOrder[]): string {
  const max = orders.reduce((m, o) => Math.max(m, parseInt(o.id.slice(3), 10) || 0), 0);
  return `WO-${String(max + 1).padStart(4, '0')}`;
}

export function toOrderSeg(seg: Seg, detail: Detail | null, stats: Stats | null): OrderSeg {
  const out: OrderSeg = {
    ...(detail ?? {}),
    id: seg.id,
    paths: seg.paths,
    tier: seg.tier,
    rate: seg.rate,
    ytp: seg.ytp,
    crack: seg.crack,
    hz: seg.hz,
    ho: seg.ho,
  };
  if (seg.flood != null) out.flood = seg.flood;
  const county = countyName(seg.id, stats);
  if (county) out.county = county;
  return out;
}

export function orderSegToSeg(s: OrderSeg): Seg {
  const { cls, cty } = parseId(s.id);
  let w = 180;
  let so = 90;
  let e = -180;
  let n = -90;
  for (const p of s.paths)
    for (let i = 0; i < p.length; i += 2) {
      w = Math.min(w, p[i]);
      e = Math.max(e, p[i]);
      so = Math.min(so, p[i + 1]);
      n = Math.max(n, p[i + 1]);
    }
  const seg: Seg = {
    id: s.id,
    rate: s.rate,
    ytp: s.ytp,
    crack: s.crack,
    hz: s.hz,
    ho: s.ho,
    paths: s.paths,
    bbox: [w, so, e, n],
    tier: s.tier,
    score: 0,
    cls,
    cty,
  };
  if (s.flood != null) seg.flood = s.flood;
  return seg;
}

export const orders = {
  /** Adds roads to an existing order, or to a new one when `orderId` is null. Returns the order id. */
  addSegs(orderId: string | null, segs: OrderSeg[]): string {
    const existing = orderId ? state.orders.find((o) => o.id === orderId) : undefined;
    if (existing) {
      const have = new Set(existing.segs.map((s) => s.id));
      const merged = [...existing.segs, ...segs.filter((s) => !have.has(s.id))];
      commit({ ...state, orders: state.orders.map((o) => (o.id === existing.id ? { ...o, segs: merged } : o)) });
      return existing.id;
    }
    const id = nextId(state.orders);
    const order: WorkOrder = {
      id,
      created: new Date().toISOString(),
      status: 'Queued',
      crew: '',
      due: '',
      notes: '',
      segs,
    };
    commit({ ...state, orders: [...state.orders, order] });
    return id;
  },
  update(id: string, patch: Partial<Omit<WorkOrder, 'id' | 'segs' | 'created'>>): void {
    commit({ ...state, orders: state.orders.map((o) => (o.id === id ? { ...o, ...patch } : o)) });
  },
  removeSeg(id: string, segId: string): void {
    commit({
      ...state,
      orders: state.orders.map((o) => (o.id === id ? { ...o, segs: o.segs.filter((s) => s.id !== segId) } : o)),
    });
  },
  remove(id: string): void {
    commit({ ...state, orders: state.orders.filter((o) => o.id !== id) });
  },
  addCrew(name: string): void {
    const n = name.trim();
    if (!n || state.crews.includes(n)) return;
    commit({ ...state, crews: [...state.crews, n] });
  },
  removeCrew(name: string): void {
    commit({
      crews: state.crews.filter((c) => c !== name),
      orders: state.orders.map((o) => (o.crew === name ? { ...o, crew: '' } : o)),
    });
  },
};

// ------------------------------------------------------------------ derived values

export function orderTier(o: WorkOrder): TierIdx {
  return o.segs.reduce<TierIdx>((t, s) => (s.tier < t ? s.tier : t), 4);
}

/** Length in miles: NCDOT's figure when we have it, otherwise measured along the line. */
export function segMiles(s: { len?: number; paths: number[][] }): number {
  if (s.len != null) return s.len;
  let m = 0;
  for (const p of s.paths)
    for (let i = 0; i + 3 < p.length; i += 2) {
      const kx = 111_320 * Math.cos((p[i + 1] * Math.PI) / 180);
      m += Math.hypot((p[i + 2] - p[i]) * kx, (p[i + 3] - p[i + 1]) * 110_540);
    }
  return m / 1609.344;
}

export function orderMiles(o: WorkOrder): number {
  return o.segs.reduce((a, s) => a + segMiles(s), 0);
}

export function orderCost(o: WorkOrder): number | null {
  const costs = o.segs.map((s) => s.cost).filter((c): c is number => c != null);
  return costs.length ? costs.reduce((a, c) => a + c, 0) : null;
}

// ------------------------------------------------------------------ exports

function csvCell(v: unknown): string {
  if (v == null) return '';
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function csv(header: string[], rows: unknown[][]): string {
  return [header, ...rows].map((r) => r.map(csvCell).join(',')).join('\n') + '\n';
}

export function orderCsv(o: WorkOrder): string {
  return csv(
    ['work_order', 'status', 'crew', 'due', 'order_tier', 'seg_id', 'route', 'county', 'from_mp', 'to_mp', 'miles',
      'from', 'to', 'tier', 'years_to_poor', 'cracking_prob', 'flood_score_helene_zone', 'ncdot_rating', 'rating_year',
      'ncdot_treatment', 'ncdot_cost_estimate', 'notes', 'data_note'],
    o.segs.map((s) => [
      o.id, o.status, o.crew, o.due, TIERS[orderTier(o)].label, s.id, routeName(s.id), s.county ?? '',
      s.bmp ?? parseId(s.id).mp, s.emp ?? '', segMiles(s).toFixed(3), s.fr ?? '', s.to ?? '', TIERS[s.tier].label,
      s.ytp ?? '', s.crack, s.hz ? (s.flood ?? '') : 'not assessed', s.rtg ?? '', s.sy ?? '', s.trt ?? '', s.cost ?? '',
      o.notes, 'DEMO work order. Predictions, not inspections.',
    ]),
  );
}

export function orderGeoJson(o: WorkOrder): string {
  return JSON.stringify(
    {
      type: 'FeatureCollection',
      name: o.id,
      properties: {
        work_order: o.id, status: o.status, crew: o.crew, due: o.due, notes: o.notes,
        note: 'DEMO work order from Unwatched Roads. Predictions, not inspections.',
      },
      features: o.segs.map((s) => {
        const lines = s.paths.map((p) => {
          const pts: [number, number][] = [];
          for (let i = 0; i < p.length; i += 2) pts.push([p[i], p[i + 1]]);
          return pts;
        });
        return {
          type: 'Feature',
          geometry: lines.length === 1 ? { type: 'LineString', coordinates: lines[0] } : { type: 'MultiLineString', coordinates: lines },
          properties: {
            seg_id: s.id, route: routeName(s.id), county: s.county ?? null,
            from_mp: s.bmp ?? parseId(s.id).mp, to_mp: s.emp ?? null,
            tier: TIERS[s.tier].label, years_to_poor: s.ytp, cracking_prob: s.crack,
            flood_score: s.hz ? (s.flood ?? null) : null, in_helene_zone: s.hz === 1,
            ncdot_treatment: s.trt ?? null, ncdot_cost_estimate: s.cost ?? null,
          },
        };
      }),
    },
    null,
    1,
  );
}

/** Storm staging checklist: the last three columns are left blank for the crew to fill in. */
export function stormCsv(rows: Row[], stats: Stats | null): string {
  return csv(
    ['rank', 'route', 'county', 'from_mp', 'to_mp', 'from', 'to', 'flood_score', 'seg_id', 'longitude', 'latitude',
      'equipment_staged', 'detour_planned', 'checked_by'],
    rows.map((r) => [
      r.rank ?? '', routeName(r.id), countyName(r.id, stats) ?? '', r.bmp ?? parseId(r.id).mp, r.emp ?? '',
      r.fr ?? '', r.to ?? '', r.flood ?? '', r.id, r.c[0], r.c[1], '', '', '',
    ]),
  );
}

/** The work queue as it is filtered and sorted on screen. An empty field means unknown or not assessed. */
export function queueCsv(rows: Row[], stats: Stats | null): string {
  return csv(
    ['route', 'county', 'from_mp', 'to_mp', 'tier', 'priority_score', 'years_to_poor', 'wear_heldout', 'cracking_probability',
      'flood_score', 'rating', 'survey_year', 'vehicles_per_day', 'traffic_source', 'ncdot_treatment', 'ncdot_cost', 'seg_id',
      'longitude', 'latitude'],
    rows.map((r) => [
      routeName(r.id), countyName(r.id, stats) ?? '', r.bmp ?? parseId(r.id).mp, r.emp ?? '', TIERS[r.t].label, r.s, r.ytp ?? '',
      r.ho & HO_RATE ? 'yes' : 'no', r.crack, r.hz ? (r.flood ?? '') : '', r.rtg ?? '', r.sy ?? '', r.aadt ?? '', r.as ?? '',
      r.trt ?? '', r.cost ?? '', r.id, r.c[0], r.c[1],
    ]),
  );
}

export function download(filename: string, text: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
