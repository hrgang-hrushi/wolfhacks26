/**
 * Google Maps JavaScript API basemap with deck.gl's GoogleMapsOverlay, for /m.
 *
 * Needs VITE_GOOGLE_MAPS_API_KEY and a vector Map ID in VITE_GOOGLE_MAP_ID.
 * Any failure (no key, bad key, script blocked, slow network) calls onFail, and
 * the caller swaps in MapLibre with the same layers.
 */
import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef } from 'react';
import { importLibrary, setOptions } from '@googlemaps/js-api-loader';
import { GoogleMapsOverlay } from '@deck.gl/google-maps';
import { GOOGLE_KEY, GOOGLE_MAP_ID, googleConfigured, type MapHandle, type MapProps } from './mapTypes';

const LOAD_TIMEOUT_MS = 7000;
let optionsSet = false;

declare global {
  interface Window {
    gm_authFailure?: () => void;
  }
}

export const GoogleDeck = forwardRef<MapHandle, MapProps>(function GoogleDeck(props, ref) {
  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const overlayRef = useRef<GoogleMapsOverlay | null>(null);
  const propsRef = useRef(props);
  useLayoutEffect(() => {
    propsRef.current = props;
  });

  useEffect(() => {
    let live = true;
    let failed = false;
    const fail = (reason: string) => {
      if (!live || failed) return;
      failed = true;
      propsRef.current.onFail?.(reason);
    };
    if (!googleConfigured) {
      fail('Google Maps key or Map ID not set');
      return;
    }
    // Google calls this global when the key is rejected (wrong key, referrer not allowed, billing off).
    window.gm_authFailure = () => fail('Google Maps rejected the API key');
    const timer = window.setTimeout(() => {
      if (!mapRef.current) fail('Google Maps did not load in time');
    }, LOAD_TIMEOUT_MS);

    if (!optionsSet) {
      setOptions({ key: GOOGLE_KEY, v: 'weekly', mapIds: [GOOGLE_MAP_ID] });
      optionsSet = true;
    }
    importLibrary('maps')
      .then(({ Map }) => {
        if (!live || failed || !elRef.current) return;
        const p = propsRef.current;
        const map = new Map(elRef.current, {
          center: { lat: p.initial.lat, lng: p.initial.lng },
          zoom: p.initial.zoom + 1,
          mapId: GOOGLE_MAP_ID,
          colorScheme: p.dark ? 'DARK' : 'LIGHT',
          disableDefaultUI: true,
          clickableIcons: false,
          gestureHandling: 'greedy',
          minZoom: 6,
          maxZoom: 18,
          tilt: 0,
        });
        const overlay = new GoogleMapsOverlay({
          layers: p.layers,
          pickingRadius: p.pickingRadius ?? 12,
          onClick: (info) => {
            if (!info.picked) propsRef.current.onBackgroundClick?.();
          },
        });
        overlay.setMap(map);
        map.addListener('idle', () => {
          const b = map.getBounds();
          const z = map.getZoom();
          if (!b || z == null) return;
          const sw = b.getSouthWest();
          const ne = b.getNorthEast();
          propsRef.current.onView({ bounds: [sw.lng(), sw.lat(), ne.lng(), ne.lat()], zoom: z - 1 });
        });
        mapRef.current = map;
        overlayRef.current = overlay;
        window.clearTimeout(timer);
      })
      .catch((e: unknown) => fail(e instanceof Error ? e.message : 'Google Maps failed to load'));

    return () => {
      live = false;
      window.clearTimeout(timer);
      overlayRef.current?.setMap(null);
      overlayRef.current?.finalize();
      overlayRef.current = null;
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    overlayRef.current?.setProps({ layers: props.layers });
  }, [props.layers]);

  useEffect(() => {
    mapRef.current?.setOptions({ colorScheme: props.dark ? 'DARK' : 'LIGHT' });
  }, [props.dark]);

  useImperativeHandle(ref, () => ({
    flyTo: (lng, lat, zoom) => {
      const map = mapRef.current;
      if (!map) return;
      map.panTo({ lat, lng });
      map.setZoom(zoom != null ? zoom + 1 : Math.max(map.getZoom() ?? 12, 13));
    },
    fitBounds: (b, padding = 48) => {
      mapRef.current?.fitBounds({ west: b[0], south: b[1], east: b[2], north: b[3] }, padding);
    },
    unproject: () => null,
    setDragPan: (enabled) => {
      mapRef.current?.setOptions({ gestureHandling: enabled ? 'greedy' : 'none' });
    },
  }));

  return <div ref={elRef} className="map-canvas" />;
});

export default GoogleDeck;
