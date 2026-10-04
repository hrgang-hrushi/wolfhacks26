import { useEffect, useLayoutEffect, useRef, useState, useImperativeHandle, forwardRef } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import { Sun, Globe, Crosshair } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { getScoreRGBA } from '../utils/colors';
import { MAPBOX_TOKEN, NC_CITY_COORDINATES, CARTO_LIGHT_STYLE, CARTO_DARK_STYLE } from '../config/mapbox';

export interface MapViewHandle {
  flyToCity: (city: string) => void;
  flyToSegment: (segment: RoadSegment) => void;
  flyToCoords: (lng: number, lat: number, zoom?: number) => void;
}

interface MapViewProps {
  segments: RoadSegment[];
  selectedSegment: RoadSegment | null;
  onSelectSegment: (segment: RoadSegment) => void;
}

// Focused North Carolina Basemaps with automatic fallback
const NC_BASEMAPS = {
  light: {
    label: 'Clean Light',
    url: 'mapbox://styles/mapbox/light-v11',
    fallback: CARTO_LIGHT_STYLE
  },
  satellite: {
    label: 'Satellite HD',
    url: 'mapbox://styles/mapbox/satellite-streets-v12',
    fallback: CARTO_DARK_STYLE
  }
};

type NCBasemapKey = keyof typeof NC_BASEMAPS;

// North Carolina geographic bounds
const NC_BOUNDS: [mapboxgl.LngLatLike, mapboxgl.LngLatLike] = [
  [-84.5, 33.7], // Southwest NC / mountains
  [-75.2, 36.7]  // Northeast NC / Outer Banks
];

export const MapView = forwardRef<MapViewHandle, MapViewProps>(({
  segments,
  selectedSegment,
  onSelectSegment
}, ref) => {
  const mapWrapperRef = useRef<HTMLDivElement>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [activeStyleKey, setActiveStyleKey] = useState<NCBasemapKey>('light');

  // Hover state for interactive tooltip
  const [hoveredInfo, setHoveredInfo] = useState<{
    segment: RoadSegment | null;
    x: number;
    y: number;
  }>({ segment: null, x: 0, y: 0 });
  const [tooltipPosition, setTooltipPosition] = useState({ left: 0, top: 0 });

  useLayoutEffect(() => {
    const wrapper = mapWrapperRef.current;
    const tooltip = tooltipRef.current;
    if (!hoveredInfo.segment || !wrapper || !tooltip) return;

    const gap = 16;
    const edge = 12;
    const tooltipWidth = tooltip.offsetWidth;
    const tooltipHeight = tooltip.offsetHeight;
    const left = hoveredInfo.x + gap + tooltipWidth + edge <= wrapper.clientWidth
      ? hoveredInfo.x + gap
      : hoveredInfo.x - tooltipWidth - gap;
    const top = hoveredInfo.y + gap + tooltipHeight + edge <= wrapper.clientHeight
      ? hoveredInfo.y + gap
      : hoveredInfo.y - tooltipHeight - gap;

    setTooltipPosition({
      left: Math.max(edge, Math.min(left, wrapper.clientWidth - tooltipWidth - edge)),
      top: Math.max(edge, Math.min(top, wrapper.clientHeight - tooltipHeight - edge))
    });
  }, [hoveredInfo]);

  const [webGlSupported, setWebGlSupported] = useState(true);
  const [locatingUser, setLocatingUser] = useState(false);

  // Set user's Mapbox access token
  mapboxgl.accessToken = MAPBOX_TOKEN;

  // Expose imperative methods to parent for city navigation and segment zoom
  useImperativeHandle(ref, () => ({
    flyToCity: (city: string) => {
      if (!mapRef.current) return;
      const target = NC_CITY_COORDINATES[city] || NC_CITY_COORDINATES['Statewide'];
      if (!target) return;
      mapRef.current.flyTo({
        center: target.center,
        zoom: target.zoom,
        pitch: target.pitch,
        bearing: target.bearing,
        duration: 1800,
        essential: true
      });
    },
    flyToSegment: (segment: RoadSegment) => {
      if (!mapRef.current) return;
      const path = (Array.isArray(segment.path) && segment.path.length > 0)
        ? segment.path
        : (Array.isArray((segment as any).paths?.[0]) ? (segment as any).paths[0] : null);
      if (!path || path.length === 0) return;
      const midIdx = Math.floor(path.length / 2);
      const targetCoord = path[midIdx] || path[0];
      if (!targetCoord || isNaN(targetCoord[0]) || isNaN(targetCoord[1])) return;
      const [lng, lat] = targetCoord;
      mapRef.current.flyTo({
        center: [lng, lat],
        zoom: 15.2,
        pitch: 35,
        bearing: 0,
        duration: 1400,
        essential: true
      });
    },
    flyToCoords: (lng: number, lat: number, zoom: number = 14.5) => {
      if (!mapRef.current || isNaN(lng) || isNaN(lat)) return;
      mapRef.current.flyTo({
        center: [lng, lat],
        zoom,
        pitch: 30,
        duration: 1500,
        essential: true
      });
    }
  }));

  // Switch basemap style
  const handleSwitchBasemap = (key: NCBasemapKey) => {
    setActiveStyleKey(key);
    if (!mapRef.current) return;
    const targetUrl = (MAPBOX_TOKEN && MAPBOX_TOKEN.startsWith('pk.'))
      ? NC_BASEMAPS[key].url
      : NC_BASEMAPS[key].fallback;
    mapRef.current.setStyle(targetUrl);
  };

  // Current Location handler
  const handleCurrentLocation = () => {
    setLocatingUser(true);
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setLocatingUser(false);
          const { longitude, latitude } = pos.coords;
          // Check if within NC bounds, otherwise center on Raleigh Capital District
          if (longitude >= -84.5 && longitude <= -75.0 && latitude >= 33.7 && latitude <= 36.7) {
            mapRef.current?.flyTo({
              center: [longitude, latitude],
              zoom: 15,
              pitch: 35,
              duration: 1600,
              essential: true
            });
          } else {
            // Default to Fitts-Woolard Hall / NC State Centennial Campus
            mapRef.current?.flyTo({
              center: [-78.6748, 35.7725],
              zoom: 15.2,
              pitch: 35,
              duration: 1600,
              essential: true
            });
          }
        },
        () => {
          setLocatingUser(false);
          // Default to Fitts-Woolard Hall / NC State Centennial Campus
          mapRef.current?.flyTo({
            center: [-78.6748, 35.7725],
            zoom: 15.2,
            pitch: 35,
            duration: 1600,
            essential: true
          });
        },
        { timeout: 5000, enableHighAccuracy: true }
      );
    } else {
      setLocatingUser(false);
      mapRef.current?.flyTo({
        center: [-78.6748, 35.7725],
        zoom: 15.2,
        pitch: 35,
        duration: 1600,
        essential: true
      });
    }
  };

  // Helper to extract coordinates safely from path or paths
  const getSegmentPath = (d: RoadSegment): [number, number][] => {
    if (Array.isArray(d.path) && d.path.length > 0) return d.path;
    if (Array.isArray((d as any).paths) && (d as any).paths.length > 0 && Array.isArray((d as any).paths[0])) {
      return (d as any).paths[0];
    }
    return [];
  };

  // Initialize Mapbox GL map constrained strictly to North Carolina
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    try {
      const initialStyle = (MAPBOX_TOKEN && MAPBOX_TOKEN.startsWith('pk.'))
        ? NC_BASEMAPS[activeStyleKey].url
        : NC_BASEMAPS[activeStyleKey].fallback;

      const mapInstance = new mapboxgl.Map({
        container: mapContainerRef.current,
        style: initialStyle,
        center: NC_CITY_COORDINATES.Raleigh.center,
        zoom: NC_CITY_COORDINATES.Raleigh.zoom,
        pitch: NC_CITY_COORDINATES.Raleigh.pitch,
        bearing: NC_CITY_COORDINATES.Raleigh.bearing,
        maxBounds: NC_BOUNDS,
        attributionControl: false,
        antialias: true
      });

      // Controls
      mapInstance.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), 'bottom-right');
      mapInstance.addControl(new mapboxgl.ScaleControl({ unit: 'imperial' }), 'bottom-left');

      // Listen for tile authorization / token failures and seamlessly switch to free Carto vector basemap
      mapInstance.on('error', (e) => {
        const msg = String(e.error?.message || '');
        const status = (e.error as any)?.status;
        if (status === 401 || status === 403 || msg.toLowerCase().includes('token') || msg.toLowerCase().includes('unauthorized') || msg.toLowerCase().includes('forbidden')) {
          console.warn('Mapbox basemap unauthorized or rate limited, switching to Carto vector basemap:', msg);
          const fallbackUrl = NC_BASEMAPS[activeStyleKey]?.fallback || CARTO_LIGHT_STYLE;
          mapInstance.setStyle(fallbackUrl);
        }
      });

      // Deck.gl overlay
      const overlayInstance = new MapboxOverlay({
        interleaved: false,
        layers: []
      });

      mapInstance.addControl(overlayInstance as unknown as mapboxgl.IControl);

      mapRef.current = mapInstance;
      overlayRef.current = overlayInstance;

      const handleResize = () => {
        mapInstance.resize();
      };
      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        if (overlayRef.current) {
          overlayRef.current.finalize();
        }
        mapInstance.remove();
        mapRef.current = null;
        overlayRef.current = null;
      };
    } catch (e) {
      console.warn('Mapbox GL initial style error, retrying with Carto vector basemap:', e);
      try {
        if (!mapContainerRef.current) return;
        const fallbackMap = new mapboxgl.Map({
          container: mapContainerRef.current,
          style: CARTO_LIGHT_STYLE,
          center: NC_CITY_COORDINATES.Raleigh.center,
          zoom: NC_CITY_COORDINATES.Raleigh.zoom,
          pitch: NC_CITY_COORDINATES.Raleigh.pitch,
          bearing: NC_CITY_COORDINATES.Raleigh.bearing,
          maxBounds: NC_BOUNDS,
          attributionControl: false,
          antialias: true
        });
        const overlayInstance = new MapboxOverlay({ interleaved: false, layers: [] });
        fallbackMap.addControl(overlayInstance as unknown as mapboxgl.IControl);
        mapRef.current = fallbackMap;
        overlayRef.current = overlayInstance;
      } catch (err2) {
        console.error('All WebGL basemaps failed:', err2);
        setWebGlSupported(false);
      }
    }
  }, []);

  // Update deck.gl PathLayer with crisp, uncluttered styling
  useEffect(() => {
    if (!overlayRef.current) return;

    const layers = [];

    // 1. Transparent wide hit-detection layer for effortless clicking
    layers.push(
      new PathLayer<RoadSegment>({
        id: 'road-segments-hit-area',
        data: segments,
        pickable: true,
        widthScale: 1,
        widthMinPixels: 18,
        capRounded: true,
        jointRounded: true,
        getPath: (d) => getSegmentPath(d),
        getColor: [0, 0, 0, 0],
        getWidth: 16,
        onClick: (info) => {
          if (info.object) {
            onSelectSegment(info.object as RoadSegment);
          }
        },
        onHover: (info) => {
          if (info.object) {
            setHoveredInfo({
              segment: info.object as RoadSegment,
              x: info.x,
              y: info.y
            });
          } else {
            setHoveredInfo({ segment: null, x: 0, y: 0 });
          }
        }
      })
    );

    // 2. Slender subtle shadow casing under all segments (prevents clumsiness while maintaining contrast)
    layers.push(
      new PathLayer<RoadSegment>({
        id: 'road-segments-casing',
        data: segments,
        pickable: false,
        widthScale: 1,
        widthMinPixels: 3.5,
        capRounded: true,
        jointRounded: true,
        getPath: (d) => getSegmentPath(d),
        getColor: [15, 23, 42, 120],
        getWidth: 3.5
      })
    );

    // 3. Radiant cyan halo ONLY under the currently selected segment
    if (selectedSegment) {
      layers.push(
        new PathLayer<RoadSegment>({
          id: 'selected-segment-glow',
          data: [selectedSegment],
          pickable: false,
          widthScale: 1,
          widthMinPixels: 9,
          capRounded: true,
          jointRounded: true,
          getPath: (d) => getSegmentPath(d),
          getColor: [56, 189, 248, 255],
          getWidth: 10
        })
      );
    }

    // 4. Main clean colored road segment lines
    layers.push(
      new PathLayer<RoadSegment>({
        id: 'road-segments-core',
        data: segments,
        pickable: true,
        widthScale: 1,
        widthMinPixels: 2.5,
        capRounded: true,
        jointRounded: true,
        getPath: (d) => getSegmentPath(d),
        getColor: (d) => {
          if (selectedSegment && selectedSegment.seg_id === d.seg_id) {
            return [255, 255, 255, 255]; // Crisp white highlight when selected
          }
          const sScore = typeof d.score === 'number' && !isNaN(d.score) ? d.score : (d.pv_rating ? d.pv_rating / 100 : 0.75);
          return getScoreRGBA(sScore, 245);
        },
        getWidth: (d) => {
          if (selectedSegment && selectedSegment.seg_id === d.seg_id) {
            return 6;
          }
          return 2.8;
        },
        updateTriggers: {
          getColor: [selectedSegment?.seg_id],
          getWidth: [selectedSegment?.seg_id]
        },
        onClick: (info) => {
          if (info.object) {
            onSelectSegment(info.object as RoadSegment);
          }
        }
      })
    );

    // 5. Warning Beacon Pins: ONLY on Critical/High-Hazard segments (no clutter on normal roads)
    const hazardSegments = segments.filter(
      (s) => {
        const sScore = typeof s.score === 'number' && !isNaN(s.score) ? s.score : (s.pv_rating ? s.pv_rating / 100 : 0.75);
        return (sScore < 0.45) || (s.pred_crack && s.pred_crack > 0.4) || (selectedSegment && selectedSegment.seg_id === s.seg_id);
      }
    );

    const pinData = hazardSegments.map(s => {
      const p = getSegmentPath(s);
      if (!p || p.length === 0) return null;
      const midIdx = Math.floor(p.length / 2);
      const pos = p[midIdx] || p[0];
      if (!pos || isNaN(pos[0]) || isNaN(pos[1])) return null;
      return {
        segment: s,
        pos,
        isSelected: selectedSegment?.seg_id === s.seg_id
      };
    }).filter((item): item is { segment: RoadSegment; pos: [number, number]; isSelected: boolean } => item !== null);


    if (pinData.length > 0) {
      // Outer translucent amber warning pulse
      layers.push(
        new ScatterplotLayer({
          id: 'hazard-pins-pulse',
          data: pinData,
          getPosition: (d) => d.pos,
          getRadius: (d) => d.isSelected ? 18 : 12,
          radiusUnits: 'pixels',
          getFillColor: [245, 158, 11, 55],
          pickable: false,
          updateTriggers: {
            getRadius: [selectedSegment?.seg_id]
          }
        })
      );

      // Inner solid core dot
      layers.push(
        new ScatterplotLayer({
          id: 'hazard-pins-dot',
          data: pinData,
          getPosition: (d) => d.pos,
          getRadius: (d) => d.isSelected ? 5.5 : 4,
          radiusUnits: 'pixels',
          getFillColor: [245, 158, 11, 255],
          stroked: true,
          getLineColor: [255, 255, 255, 240],
          lineWidthUnits: 'pixels',
          lineWidthMinPixels: 1.5,
          pickable: true,
          onClick: (info) => {
            if (info.object && info.object.segment) {
              onSelectSegment(info.object.segment);
            }
          },
          updateTriggers: {
            getRadius: [selectedSegment?.seg_id]
          }
        })
      );
    }

    overlayRef.current.setProps({ layers });
  }, [segments, selectedSegment, onSelectSegment]);

  return (
    <div className="map-view-wrapper" ref={mapWrapperRef}>
      {!webGlSupported ? (
        <div className="vector-fallback-map">
          <svg className="vector-map-svg" viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid slice">
            <rect width="1000" height="600" fill="#edece8" />
            <path d="M 0,280 C 150,290 300,340 450,420 C 580,500 700,560 850,600 L 0,600 Z" fill="#c3e4e1" />
            <text x="240" y="240" fill="#718096" fontSize="13" fontWeight="600">Hillsborough St, Raleigh, NC</text>
            <text x="460" y="320" fill="#4a5568" fontSize="16" fontWeight="700">Capital Blvd Corridor</text>
          </svg>
        </div>
      ) : (
        <div ref={mapContainerRef} className="map-container" />
      )}

      {/* Real-time Mapbox Telemetry Badge */}
      <div className="mapbox-live-badge">
        <span className="live-dot" />
        <span className="live-label">NCDOT Highway Network</span>
        <span className="live-count">{segments.length} NC Segments</span>
      </div>

      {/* Floating Bottom-Right Toolbar: Current Location + Basemap Switcher */}
      <div className="map-bottom-right-toolbar">
        {/* Current Location Button */}
        <button
          type="button"
          className={`current-location-btn ${locatingUser ? 'active' : ''}`}
          onClick={handleCurrentLocation}
          title="Zoom to current location (NC State Centennial Campus, Raleigh)"
          aria-label="Current location"
        >
          <Crosshair size={13} className={locatingUser ? 'animate-spin' : ''} />
          <span>Current Location</span>
        </button>

        {/* Clean NC Basemap Switcher */}
        <div className="basemap-switcher" aria-label="Select Basemap Cartography">
          <button
            type="button"
            className={`basemap-btn ${activeStyleKey === 'light' ? 'active' : ''}`}
            onClick={() => handleSwitchBasemap('light')}
            title="Clean Light Map (Matches Executive UI)"
          >
            <Sun size={12} />
            <span>Clean Light</span>
          </button>
          <button
            type="button"
            className={`basemap-btn ${activeStyleKey === 'satellite' ? 'active' : ''}`}
            onClick={() => handleSwitchBasemap('satellite')}
            title="High-Res Aerial Satellite Imagery"
          >
            <Globe size={12} />
            <span>Satellite</span>
          </button>
        </div>
      </div>

      {/* Floating Hover Tooltip */}
      {hoveredInfo.segment && (
        <div
          className="map-tooltip"
          ref={tooltipRef}
          style={{
            left: tooltipPosition.left,
            top: tooltipPosition.top
          }}
        >
          <div className="tooltip-header">
            <span className="tooltip-id">{hoveredInfo.segment.seg_id}</span>
            <span className={`tooltip-pill ${hoveredInfo.segment.source === 'ncdot' ? 'pill-ncdot' : 'pill-city'}`}>
              {hoveredInfo.segment.source === 'ncdot' ? 'State NCDOT' : 'City Road'}
            </span>
          </div>
          <div className="tooltip-name">{hoveredInfo.segment.name}</div>
          <div className="tooltip-stats">
            <div className="tooltip-stat">
              <span className="tooltip-stat-label">Rating</span>
              <span className="tooltip-stat-val">
                {hoveredInfo.segment.pv_rating} / 100
              </span>
            </div>
            <div className="tooltip-stat">
              <span className="tooltip-stat-label">Years to Poor</span>
              <span className="tooltip-stat-val text-rose-400">
                {hoveredInfo.segment.years_to_poor}y
              </span>
            </div>
            <div className="tooltip-stat">
              <span className="tooltip-stat-label">Degradation</span>
              <span className="tooltip-stat-val text-amber-300">
                -{hoveredInfo.segment.pred_rate || 1.2}/yr
              </span>
            </div>
          </div>
          <div className="tooltip-hint">Click segment to inspect NCDOT forecast</div>
        </div>
      )}
    </div>
  );
});

MapView.displayName = 'MapView';
