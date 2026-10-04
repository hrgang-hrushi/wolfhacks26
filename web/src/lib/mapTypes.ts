import type { Layer, PickingInfo } from '@deck.gl/core';
import type { Bounds } from './data';

/** What the map is showing. `zoom` is in MapLibre units (512 px tiles); Google's zoom is this plus one. */
export interface MapView {
  bounds: Bounds;
  zoom: number;
}

export type Padding = number | { top: number; bottom: number; left: number; right: number };

export interface MapHandle {
  flyTo(lng: number, lat: number, zoom?: number): void;
  fitBounds(b: Bounds, padding?: Padding): void;
  /** Screen pixel (relative to the map) -> [lng, lat]. */
  unproject(x: number, y: number): [number, number] | null;
  setDragPan(enabled: boolean): void;
}

export interface MapProps {
  layers: Layer[];
  initial: { lng: number; lat: number; zoom: number };
  dark?: boolean;
  /** Extra pixels around a tap that still count as hitting a road. */
  pickingRadius?: number;
  onView: (v: MapView) => void;
  /** A click or tap that hit no road. */
  onBackgroundClick?: () => void;
  getTooltip?: (info: PickingInfo) => { html: string } | null;
  /** The basemap could not start (bad key, no WebGL, script blocked). */
  onFail?: (reason: string) => void;
}

/** Rough bounds for a view before the map has loaded, so data can start downloading at once. */
export function boundsFor(lng: number, lat: number, zoom: number, width: number, height: number): Bounds {
  const degPerPx = 360 / (512 * 2 ** zoom);
  const dx = (width * degPerPx) / 2;
  const dy = (height * degPerPx * Math.cos((lat * Math.PI) / 180)) / 2;
  return [lng - dx, lat - dy, lng + dx, lat + dy];
}

export const BASEMAP_LIGHT = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';
export const BASEMAP_DARK = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

export const NC_BOUNDS: Bounds = [-84.33, 33.84, -75.45, 36.6];
export const NC_VIEW = { lng: -79.9, lat: 35.35, zoom: 6.3 };

export const PLACES: Record<string, { lng: number; lat: number; zoom: number }> = {
  Raleigh: { lng: -78.64, lat: 35.79, zoom: 9.6 },
  Asheville: { lng: -82.55, lat: 35.58, zoom: 9.8 },
  Wilmington: { lng: -77.92, lat: 34.22, zoom: 9.8 },
  Charlotte: { lng: -80.84, lat: 35.23, zoom: 9.6 },
};

/** Google Maps is used on /m only when both are set at build time (see web/.env.example). */
export const GOOGLE_KEY: string = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? '';
export const GOOGLE_MAP_ID: string = import.meta.env.VITE_GOOGLE_MAP_ID ?? '';
export const googleConfigured = GOOGLE_KEY !== '' && GOOGLE_MAP_ID !== '';
