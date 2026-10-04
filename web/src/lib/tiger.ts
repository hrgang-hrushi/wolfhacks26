/**
 * Client for the Tiger Data service (Postgres + TimescaleDB), which the hosted API attaches
 * under /api/tiger when its database setting is present. It holds what the static files cannot:
 * time-stamped camera and water-level readings, kept as hourly summaries by the database.
 *
 * Everything here is optional. On a deployment without the database, `useTiger` reports 'off'
 * and the dashboard shows no trace of it.
 */
import { useEffect, useState } from 'react';

const rawBase: string = import.meta.env.VITE_API_BASE_URL ?? '';
// A build made with a localhost API address must not call localhost from the hosted site.
const hosted = typeof window !== 'undefined' && !/^(localhost|127\.0\.0\.1)$/.test(window.location.hostname);
const API_BASE = hosted && /localhost|127\.0\.0\.1/.test(rawBase) ? '' : rawBase;
export const TIGER_API = `${API_BASE}/api/tiger`;

export interface CameraReading {
  time: string;
  p_flooded: number | null;
  depth_pred_cm: number | null;
  depth_measured_cm: number | null;
}

export interface CameraAlert {
  camera_id: string;
  name: string | null;
  lat: number | null;
  lon: number | null;
  role: string | null;
  /** An NCDOT still taken on a dry road: a known false alarm, listed apart. */
  known_dry: boolean;
  note: string | null;
  /** A row copied from the recorded storm with its time shifted to now. */
  replay: boolean;
  replay_of: string | null;
  road: { seg_id: string; distance_m: number | null; route: string | null; county: string | null; rating: number | null; bucket: string | null; rank: number | null } | null;
  worst: CameraReading;
  latest: CameraReading;
}

export interface SensorReading {
  time: string;
  depth_on_road_cm: number | null;
  level_m: number | null;
}

export interface SensorAlert {
  station: string;
  name: string | null;
  lat: number | null;
  lon: number | null;
  road_level_m: number | null;
  replay: boolean;
  replay_of: string | null;
  note: string;
  worst: SensorReading;
  latest: SensorReading;
}

export interface AlertsReply {
  as_of: string | null;
  as_of_was_given: boolean;
  window_start: string | null;
  window_hours?: number;
  /** True only when as_of is within the last hour of the real clock. */
  live: boolean;
  flag_at: number;
  flooded_cm: number;
  caveat: string;
  camera_alerts: CameraAlert[];
  sensor_alerts: SensorAlert[];
}

export interface PeakHour {
  hour: string;
  as_of: string;
  camera_flags: number;
  sensor_alerts: number;
  known_dry_flags: number;
}

export interface TigerStats {
  time_partitioned_tables: Record<
    string,
    { rows: number; chunks: number; compressed_chunks: number; bytes_before: number | null; bytes_after: number | null; compression_ratio: number | null; chunk_interval: string }
  >;
  running_summaries: Record<string, { rows: number; includes_rows_newer_than_last_refresh: boolean; over: string }>;
  background_jobs: { job: string; on: string; scheduled: boolean }[];
  plain_tables: Record<string, number>;
  replay_rows: number;
  database_size_bytes: number;
  timescaledb_version: string | null;
  postgres_version: string | null;
  load: { status?: string; finished_at?: string | null } | null;
}

export class TigerError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${TIGER_API}${path}`, { signal, headers: { Accept: 'application/json' } });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const b = (body ?? {}) as { error?: string; detail?: string; load_status?: string };
    throw new TigerError(res.status, b.detail ?? b.error ?? `HTTP ${res.status}`);
  }
  return body as T;
}

export const tiger = {
  alerts: (asOf: string | null, hours: 1 | 2, signal?: AbortSignal) =>
    get<AlertsReply>(`/alerts?hours=${hours}${asOf ? `&as_of=${encodeURIComponent(asOf)}` : ''}`, signal),
  peaks: (signal?: AbortSignal) => get<{ hours: PeakHour[]; note: string }>('/alerts/peaks?limit=8', signal),
  stats: (signal?: AbortSignal) => get<TigerStats>('/stats', signal),
  riskCsvUrl: `${TIGER_API}/export/risk.csv`,
  dictionaryUrl: `${TIGER_API}/export/dictionary`,
};

export type TigerState =
  | { kind: 'checking' }
  /** This deployment has no database setting: show nothing. */
  | { kind: 'off' }
  /** The routes exist but the database did not answer. */
  | { kind: 'down'; reason: string }
  /** The database answers but its latest load has not finished. */
  | { kind: 'loading'; status: string }
  | { kind: 'ready' };

const RECHECK_MS = 45_000;

/** Whether the Tiger Data service is there, checked once and then again while it is not ready. */
export function useTiger(): TigerState {
  const [state, setState] = useState<TigerState>({ kind: 'checking' });
  useEffect(() => {
    let live = true;
    let timer = 0;
    const check = async () => {
      let next: TigerState;
      try {
        const status = await get<{ configured: boolean }>('/status');
        if (!status.configured) next = { kind: 'off' };
        else {
          try {
            const h = await get<{ load_status: string }>('/health');
            next = h.load_status === 'complete' ? { kind: 'ready' } : { kind: 'loading', status: h.load_status };
          } catch (e) {
            next = { kind: 'down', reason: e instanceof Error ? e.message : 'the database did not answer' };
          }
        }
      } catch {
        next = { kind: 'off' }; // no API, or an API without these routes
      }
      if (!live) return;
      setState(next);
      if (next.kind === 'down' || next.kind === 'loading') timer = window.setTimeout(() => void check(), RECHECK_MS);
    };
    void check();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, []);
  return state;
}

/** "Sep 27, 15:06 UTC". The readings are stored in UTC and shown in UTC so they match the storm record. */
export function fmtUtc(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })} UTC`;
}

export function fmtBytes(n: number | null | undefined): string {
  if (n == null) return '';
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} kB`;
  return `${n} B`;
}
