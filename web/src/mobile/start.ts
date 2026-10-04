/**
 * Where the phone dashboard opens, and a head start on its data.
 *
 * Kept apart from MobileApp so the entry script can begin downloading road data
 * while the map code is still on its way.
 */
import { cellsForBounds, loadBacktest, loadOverview, loadShard, loadStats } from '../lib/data';
import { boundsFor, PLACES } from '../lib/mapTypes';

/** `?demo=1` (the poster QR code) opens straight into "Model in action". */
export const DEMO = new URLSearchParams(window.location.search).get('demo') === '1';

/** Western NC, wide enough to hold the Helene zone before the backtest pins arrive. */
export const HELENE_VIEW = { lng: -82.2, lat: 35.75, zoom: 7.4 };

export const START = DEMO ? HELENE_VIEW : { ...PLACES.Raleigh, zoom: 9.4 };

/** Shards a phone may hold on screen before the map falls back to the overview. */
export const PHONE_MAX_SHARDS = 16;

export function prefetchStart(): void {
  loadStats()
    .then((stats) => {
      const cells = cellsForBounds(boundsFor(START.lng, START.lat, START.zoom, window.innerWidth, window.innerHeight), stats);
      if (DEMO && stats.backtest) void loadBacktest().catch(() => undefined);
      if (cells.length === 0 || cells.length > PHONE_MAX_SHARDS) void loadOverview().catch(() => undefined);
      else for (const c of cells) void loadShard(c).catch(() => undefined);
    })
    .catch(() => undefined);
}
