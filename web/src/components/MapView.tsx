import { useEffect, useRef, useState, useImperativeHandle, forwardRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { PathLayer } from '@deck.gl/layers';
import { Map as MapIcon, Moon, Globe } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { getScoreRGBA, getConditionInfo } from '../utils/colors';

export interface MapViewHandle {
  flyToCity: (city: 'Asheville' | 'Raleigh') => void;
  flyToSegment: (segment: RoadSegment) => void;
}

interface MapViewProps {
  segments: RoadSegment[];
  selectedSegment: RoadSegment | null;
  onSelectSegment: (segment: RoadSegment) => void;
}

export type BasemapMode = 'streets' | 'satellite' | 'dark';

const CITY_COORDINATES = {
  Asheville: {
    center: [-82.5515, 35.5951] as [number, number],
    zoom: 13.5,
    pitch: 35,
    bearing: -15
  },
  Raleigh: {
    center: [-78.6382, 35.7796] as [number, number],
    zoom: 13.2,
    pitch: 25,
    bearing: 0
  }
};

// Available basemaps
const BASEMAP_STYLES: Record<BasemapMode, string | maplibregl.StyleSpecification> = {
  streets: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
  dark: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
  satellite: {
    version: 8,
    sources: {
      'esri-satellite': {
        type: 'raster',
        tiles: [
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
        ],
        tileSize: 256,
        attribution: '&copy; Esri, Maxar, Earthstar Geographics'
      }
    },
    layers: [
      {
        id: 'esri-satellite-layer',
        type: 'raster',
        source: 'esri-satellite',
        minzoom: 0,
        maxzoom: 19
      }
    ]
  }
};

export const MapView = forwardRef<MapViewHandle, MapViewProps>(({
  segments,
  selectedSegment,
  onSelectSegment
}, ref) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [basemapMode, setBasemapMode] = useState<BasemapMode>('streets');

  // Hover state for interactive tooltip
  const [hoveredInfo, setHoveredInfo] = useState<{
    segment: RoadSegment | null;
    x: number;
    y: number;
  }>({ segment: null, x: 0, y: 0 });

  // Expose imperative methods to parent for city navigation and segment zoom
  useImperativeHandle(ref, () => ({
    flyToCity: (city: 'Asheville' | 'Raleigh') => {
      if (!mapRef.current) return;
      const target = CITY_COORDINATES[city];
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
      if (!mapRef.current || !segment.path || segment.path.length === 0) return;
      const midIdx = Math.floor(segment.path.length / 2);
      const [lng, lat] = segment.path[midIdx];
      mapRef.current.flyTo({
        center: [lng, lat],
        zoom: 15.6,
        pitch: 40,
        duration: 1400,
        essential: true
      });
    }
  }));

  // Switch basemap style
  const handleSwitchBasemap = (mode: BasemapMode) => {
    setBasemapMode(mode);
    if (!mapRef.current) return;
    mapRef.current.setStyle(BASEMAP_STYLES[mode]);
  };

  // Initialize MapLibre GL map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const mapInstance = new maplibregl.Map({
      container: mapContainerRef.current,
      style: BASEMAP_STYLES[basemapMode],
      center: CITY_COORDINATES.Raleigh.center,
      zoom: CITY_COORDINATES.Raleigh.zoom,
      pitch: CITY_COORDINATES.Raleigh.pitch,
      bearing: CITY_COORDINATES.Raleigh.bearing,
      attributionControl: false
    });

    mapInstance.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
    mapInstance.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left');

    const overlayInstance = new MapboxOverlay({
      interleaved: false,
      layers: []
    });

    mapInstance.addControl(overlayInstance as unknown as maplibregl.IControl);

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
  }, []);

  // Update deck.gl PathLayer whenever segments or selection changes
  useEffect(() => {
    if (!overlayRef.current) return;

    const layers = [];

    // Transparent wide hit-detection layer for effortless clicking
    layers.push(
      new PathLayer<RoadSegment>({
        id: 'road-segments-hit-area',
        data: segments,
        pickable: true,
        widthScale: 1,
        widthMinPixels: 20,
        rounded: true,
        capRounded: true,
        jointRounded: true,
        getPath: (d) => d.path,
        getColor: [0, 0, 0, 0], // completely transparent
        getWidth: 18,
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

    // Dark casing shadow under all segments for high contrast on any basemap
    layers.push(
      new PathLayer<RoadSegment>({
        id: 'road-segments-casing',
        data: segments,
        pickable: false,
        widthScale: 1,
        widthMinPixels: 9,
        rounded: true,
        capRounded: true,
        jointRounded: true,
        getPath: (d) => d.path,
        getColor: [15, 23, 42, 220],
        getWidth: 9
      })
    );

    // Radiant cyan halo under selected segment
    if (selectedSegment) {
      layers.push(
        new PathLayer<RoadSegment>({
          id: 'selected-segment-glow',
          data: [selectedSegment],
          pickable: false,
          widthScale: 1,
          widthMinPixels: 14,
          rounded: true,
          capRounded: true,
          jointRounded: true,
          getPath: (d) => d.path,
          getColor: [56, 189, 248, 255],
          getWidth: 16
        })
      );
    }

    // Main colored road segment layer
    layers.push(
      new PathLayer<RoadSegment>({
        id: 'road-segments-core',
        data: segments,
        pickable: true,
        widthScale: 1,
        widthMinPixels: 6,
        rounded: true,
        capRounded: true,
        jointRounded: true,
        getPath: (d) => d.path,
        getColor: (d) => {
          if (selectedSegment && selectedSegment.seg_id === d.seg_id) {
            return [255, 255, 255, 255]; // Crisp white core on selection
          }
          return getScoreRGBA(d.score, 245);
        },
        getWidth: (d) => {
          if (selectedSegment && selectedSegment.seg_id === d.seg_id) {
            return 10;
          }
          return 6;
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

    overlayRef.current.setProps({ layers });
  }, [segments, selectedSegment, onSelectSegment]);

  return (
    <div className="map-view-wrapper">
      <div ref={mapContainerRef} className="map-container" />

      {/* Basemap Switcher Controls */}
      <div className="basemap-switcher" aria-label="Select Basemap Cartography">
        <button
          type="button"
          className={`basemap-btn ${basemapMode === 'streets' ? 'active' : ''}`}
          onClick={() => handleSwitchBasemap('streets')}
          title="Street Map with City Labels"
        >
          <MapIcon size={13} />
          <span>Streets</span>
        </button>
        <button
          type="button"
          className={`basemap-btn ${basemapMode === 'satellite' ? 'active' : ''}`}
          onClick={() => handleSwitchBasemap('satellite')}
          title="High-Res Aerial Satellite Imagery"
        >
          <Globe size={13} />
          <span>Satellite</span>
        </button>
        <button
          type="button"
          className={`basemap-btn ${basemapMode === 'dark' ? 'active' : ''}`}
          onClick={() => handleSwitchBasemap('dark')}
          title="Dark Night Mode"
        >
          <Moon size={13} />
          <span>Dark</span>
        </button>
      </div>

      {/* Floating Hover Tooltip */}
      {hoveredInfo.segment && (
        <div
          className="map-tooltip"
          style={{
            transform: `translate(${hoveredInfo.x + 16}px, ${hoveredInfo.y + 16}px)`
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
              <span className="tooltip-stat-val" style={{ color: getConditionInfo(hoveredInfo.segment.score).color }}>
                {hoveredInfo.segment.pv_rating} / 100
              </span>
            </div>
            <div className="tooltip-stat">
              <span className="tooltip-stat-label">Score</span>
              <span className="tooltip-stat-val">
                {(hoveredInfo.segment.score * 100).toFixed(0)}%
              </span>
            </div>
            <div className="tooltip-stat">
              <span className="tooltip-stat-label">Years to Poor</span>
              <span className="tooltip-stat-val text-rose-400">
                {hoveredInfo.segment.years_to_poor}y
              </span>
            </div>
          </div>
          <div className="tooltip-hint">Click segment to open full predictions</div>
        </div>
      )}
    </div>
  );
});

MapView.displayName = 'MapView';
