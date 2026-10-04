import type { Layer } from '@deck.gl/core';
import { TextLayer } from '@deck.gl/layers';
import type { Pin } from './layers';

/** Numbers drawn inside pins (rank on the storm staging list). */
export function pinLabelLayer<T extends Pin>(id: string, pins: T[]): Layer {
  return new TextLayer<T>({
    id: `${id}-labels`,
    data: pins.filter((p) => p.label),
    getPosition: (d) => d.c,
    getText: (d) => d.label ?? '',
    getSize: 10,
    getColor: [255, 255, 255, 255],
    fontWeight: 700,
    fontFamily: 'system-ui, sans-serif',
    getTextAnchor: 'middle',
    getAlignmentBaseline: 'center',
  });
}
