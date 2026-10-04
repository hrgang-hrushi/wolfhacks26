import { useEffect, useMemo, useState } from 'react';
import { cellsForBounds, loadOverview, loadShard, loadStats, type Shard, type Stats } from './data';
import type { MapView } from './mapTypes';

const STATS_RETRY_MS = [1500, 4000, 9000];

/** stats.json, with a few retries: one dropped request on venue wifi should not leave the page empty. */
export function useStats(): { stats: Stats | null; error: string | null } {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    let timer = 0;
    const attempt = (n: number) => {
      loadStats()
        .then((s) => {
          if (!live) return;
          setStats(s);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!live) return;
          setError(e instanceof Error ? e.message : String(e));
          if (n < STATS_RETRY_MS.length) timer = window.setTimeout(() => attempt(n + 1), STATS_RETRY_MS[n]);
        });
    };
    attempt(0);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, []);
  return { stats, error };
}

export interface RoadData {
  /** 'overview' = only the highest-priority roads are drawn; 'detail' = every road in view. */
  level: 'overview' | 'detail';
  shards: Shard[];
  /** Files still downloading for this view. */
  pending: number;
}

/**
 * Loads only the shards the viewport touches. When the view covers more than
 * `maxShards` of them (zoomed out), it falls back to overview.json.
 */
export function useRoadData(stats: Stats | null, view: MapView | null, maxShards: number): RoadData {
  const keys = useMemo(() => (stats && view ? cellsForBounds(view.bounds, stats) : []), [stats, view]);
  const level: RoadData['level'] = keys.length === 0 || keys.length > maxShards ? 'overview' : 'detail';
  const keyStr = level === 'detail' ? keys.join(',') : '';

  const [overview, setOverview] = useState<Shard | null>(null);
  const [loaded, setLoaded] = useState<{ key: string; shards: Shard[]; left: number }>({ key: '', shards: [], left: 0 });

  const overviewShards = useMemo(() => (overview ? [overview] : []), [overview]);

  useEffect(() => {
    if (!stats || level !== 'overview' || overview) return;
    let live = true;
    loadOverview()
      .then((s) => live && setOverview(s))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [stats, level, overview]);

  useEffect(() => {
    if (!keyStr) return;
    let live = true;
    const want = keyStr.split(',');
    const got = new Map<string, Shard>();
    let left = want.length;
    let scheduled = false;
    const flush = () => {
      scheduled = false;
      if (live) setLoaded({ key: keyStr, shards: want.flatMap((k) => got.get(k) ?? []), left });
    };
    for (const k of want)
      loadShard(k)
        .then((s) => got.set(k, s))
        .catch(() => undefined)
        .finally(() => {
          left--;
          if (!scheduled) {
            scheduled = true;
            queueMicrotask(flush);
          }
        });
    return () => {
      live = false;
    };
  }, [keyStr]);

  if (level === 'overview') return { level, shards: overviewShards, pending: stats && !overview ? 1 : 0 };
  // While a new view's shards arrive, keep drawing the previous view's so the map never blanks.
  return { level, shards: loaded.shards, pending: loaded.key === keyStr ? loaded.left : keys.length };
}
