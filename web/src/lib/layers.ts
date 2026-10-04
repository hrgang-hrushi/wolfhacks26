/** deck.gl layers shared by both dashboards. The same PathLayer shards draw on MapLibre and on Google Maps. */
import type { Layer } from '@deck.gl/core';
import { PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import { segColor, segWidth, type Mode, type PathItem, type RGBA, type Seg, type Shard } from './data';

export interface RoadFilter {
  /** Changes whenever the test changes, so filtered arrays can be reused between renders. */
  key: string;
  test: (s: Seg) => boolean;
}

const filteredCache = new WeakMap<Shard, { key: string; items: PathItem[] }>();

function itemsFor(shard: Shard, filter: RoadFilter | null | undefined): PathItem[] {
  if (!filter) return shard.items;
  const hit = filteredCache.get(shard);
  if (hit && hit.key === filter.key) return hit.items;
  const items = shard.items.filter((it) => filter.test(it.seg));
  filteredCache.set(shard, { key: filter.key, items });
  return items;
}

/** Every road visible through the filter, across the given shards. */
export function visibleSegs(shards: Shard[], filter: RoadFilter | null | undefined): Seg[] {
  const out: Seg[] = [];
  for (const sh of shards) for (const s of sh.segs) if (!filter || filter.test(s)) out.push(s);
  return out;
}

export interface RoadLayerOpts {
  shards: Shard[];
  mode: Mode;
  filter?: RoadFilter | null;
  onPick?: (seg: Seg) => void;
  /** Fade the roads back, for when pins are the subject. */
  dim?: boolean;
  widthScale?: number;
}

/** Thinner lines when zoomed out, so a county of roads does not turn into a blob. */
export function widthScaleForZoom(zoom: number): number {
  return Math.round(Math.max(0.45, Math.min(1.4, (zoom - 6.5) / 4.5)) * 20) / 20;
}

export function roadLayers(o: RoadLayerOpts): Layer[] {
  const scale = o.widthScale ?? 1;
  return o.shards.map(
    (shard) =>
      new PathLayer<PathItem>({
        id: `roads-${shard.cell}`,
        data: itemsFor(shard, o.filter),
        positionFormat: 'XY',
        getPath: (d) => d.path,
        getColor: (d) => {
          const c = segColor(d.seg, o.mode);
          return o.dim ? [c[0], c[1], c[2], Math.round(c[3] * 0.3)] : c;
        },
        getWidth: (d) => segWidth(d.seg, o.mode),
        widthUnits: 'pixels',
        widthScale: scale, // a uniform, so zooming does not rebuild the width buffer
        widthMinPixels: 0.75,
        capRounded: true,
        jointRounded: true,
        pickable: !!o.onPick,
        onClick: (info) => {
          if (info.object && o.onPick) o.onPick(info.object.seg);
          return true;
        },
        updateTriggers: { getColor: [o.mode, o.dim], getWidth: [o.mode] },
      }),
  );
}

function partsOf(segs: Seg[]): PathItem[] {
  const out: PathItem[] = [];
  for (const seg of segs) for (const path of seg.paths) out.push({ seg, path });
  return out;
}

/** Roads drawn with a coloured casing and their own colour on top, so they read on any basemap and at any zoom. */
export function casedLayers(
  id: string,
  segs: Seg[],
  mode: Mode,
  casing: RGBA,
  casingWidth = 9,
  fillWidth = 5,
  onPick?: (seg: Seg) => void,
): Layer[] {
  if (segs.length === 0) return [];
  const parts = partsOf(segs);
  return [
    new PathLayer<PathItem>({
      id: `${id}-casing`,
      data: parts,
      positionFormat: 'XY',
      getPath: (d) => d.path,
      getColor: casing,
      getWidth: casingWidth,
      widthUnits: 'pixels',
      capRounded: true,
      jointRounded: true,
      pickable: !!onPick,
      onClick: (info) => {
        if (info.object && onPick) onPick(info.object.seg);
        return true;
      },
    }),
    new PathLayer<PathItem>({
      id: `${id}-fill`,
      data: parts,
      positionFormat: 'XY',
      getPath: (d) => d.path,
      getColor: (d) => {
        const c = segColor(d.seg, mode);
        return [c[0], c[1], c[2], 255];
      },
      getWidth: fillWidth,
      widthUnits: 'pixels',
      capRounded: true,
      jointRounded: true,
      updateTriggers: { getColor: [mode] },
    }),
  ];
}

/** The selected road or roads. */
export function selectionLayers(id: string, segs: Seg[], mode: Mode, dark: boolean): Layer[] {
  return casedLayers(id, segs, mode, dark ? [255, 255, 255, 255] : [15, 23, 42, 255]);
}

export interface Pin {
  id: string;
  c: [number, number];
  color: RGBA;
  label?: string;
  radius?: number;
}

/** Round map pins. Numbers inside them come from pinLabelLayer() in pinLabels.ts. */
export function pinLayer<T extends Pin>(id: string, pins: T[], onPick?: (pin: T) => void, dark = false): Layer {
  return new ScatterplotLayer<T>({
    id: `${id}-dots`,
    data: pins,
    getPosition: (d) => d.c,
    getFillColor: (d) => d.color,
    getLineColor: dark ? [15, 23, 42, 255] : [255, 255, 255, 255],
    getRadius: (d) => d.radius ?? 9,
    radiusUnits: 'pixels',
    stroked: true,
    lineWidthUnits: 'pixels',
    getLineWidth: 2,
    pickable: !!onPick,
    onClick: (info) => {
      if (info.object && onPick) onPick(info.object);
      return true;
    },
    transitions: { getFillColor: 400, getRadius: 400 },
    updateTriggers: {
      getFillColor: [pins.map((p) => p.color.join()).join('|')],
      getRadius: [pins.map((p) => p.radius ?? 9).join()],
    },
  });
}
