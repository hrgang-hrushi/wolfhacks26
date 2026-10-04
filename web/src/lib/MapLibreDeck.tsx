/** MapLibre GL basemap (free Carto style, no token) with a deck.gl overlay. Used by /gov, and by /m as the fallback. */
import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef } from 'react';
import { Map as MlMap, setWorkerUrl, type IControl } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// MapLibre 6 looks for its worker next to its own file, which a bundler moves. Hand it the bundled one.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { BASEMAP_DARK, BASEMAP_LIGHT, type MapHandle, type MapProps } from './mapTypes';

setWorkerUrl(workerUrl);

export const MapLibreDeck = forwardRef<MapHandle, MapProps>(function MapLibreDeck(props, ref) {
  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const propsRef = useRef(props);
  useLayoutEffect(() => {
    propsRef.current = props;
  });

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    let map: MlMap;
    try {
      map = new MlMap({
        container: el,
        style: propsRef.current.dark ? BASEMAP_DARK : BASEMAP_LIGHT,
        center: [propsRef.current.initial.lng, propsRef.current.initial.lat],
        zoom: propsRef.current.initial.zoom,
        minZoom: 5,
        maxZoom: 17,
        boxZoom: false, // shift-drag is box-select on /gov
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        attributionControl: { compact: true },
      });
    } catch (e) {
      propsRef.current.onFail?.(e instanceof Error ? e.message : 'map failed to start');
      return;
    }
    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();

    const overlay = new MapboxOverlay({
      interleaved: false,
      layers: propsRef.current.layers,
      pickingRadius: propsRef.current.pickingRadius ?? 4,
      getTooltip: (info) => propsRef.current.getTooltip?.(info) ?? null,
      onClick: (info) => {
        if (!info.picked) propsRef.current.onBackgroundClick?.();
      },
      getCursor: ({ isHovering }) => (isHovering ? 'pointer' : 'grab'),
    });
    map.addControl(overlay as unknown as IControl);

    const emit = () => {
      const b = map.getBounds();
      propsRef.current.onView({ bounds: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], zoom: map.getZoom() });
    };
    map.on('moveend', emit);
    map.on('load', emit);
    emit();

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);

    mapRef.current = map;
    overlayRef.current = overlay;
    return () => {
      ro.disconnect();
      overlayRef.current = null;
      mapRef.current = null;
      map.remove();
    };
  }, []);

  useEffect(() => {
    overlayRef.current?.setProps({ layers: props.layers });
  }, [props.layers]);

  const firstStyle = useRef(true);
  useEffect(() => {
    if (firstStyle.current) {
      firstStyle.current = false;
      return;
    }
    mapRef.current?.setStyle(props.dark ? BASEMAP_DARK : BASEMAP_LIGHT);
  }, [props.dark]);

  useImperativeHandle(ref, () => ({
    flyTo: (lng, lat, zoom) => {
      const map = mapRef.current;
      if (map) map.flyTo({ center: [lng, lat], zoom: zoom ?? Math.max(map.getZoom(), 12), duration: 900 });
    },
    fitBounds: (b, padding = 48) => {
      mapRef.current?.fitBounds(
        [
          [b[0], b[1]],
          [b[2], b[3]],
        ],
        { padding, duration: 900, maxZoom: 14 },
      );
    },
    unproject: (x, y) => {
      const map = mapRef.current;
      if (!map) return null;
      const p = map.unproject([x, y]);
      return [p.lng, p.lat];
    },
    setDragPan: (enabled) => {
      const map = mapRef.current;
      if (!map) return;
      if (enabled) map.dragPan.enable();
      else map.dragPan.disable();
    },
  }));

  return <div ref={elRef} className="map-canvas" />;
});

export default MapLibreDeck;
