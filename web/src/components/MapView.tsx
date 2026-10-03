import { useEffect, useRef, useState, useImperativeHandle, forwardRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { PathLayer } from '@deck.gl/layers';
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

// Coordinate anchors for city zoom buttons
const CITY_COORDINATES = {
  Asheville: {
    center: [-82.5515, 35.5951] as [number, number],
    zoom: 13.4,
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

// Dark basemap with high visual contrast for neon path layers
const BASEMAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

// Offline/fallback OSM raster basemap style in case remote vector tiles are blocked
const FALLBACK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    'osm-tiles': {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '&copy; OpenStreetMap contributors'
    }
  },
  layers: [
    {
      id: 'osm-tiles-layer',
      type: 'raster',
      source: 'osm-tiles',
      minzoom: 0,
      maxzoom: 19
    }
  ]
};

export const MapView = forwardRef<MapViewHandle, MapViewProps>(({
  segments,
  selectedSegment,
  onSelectSegment
}, ref) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);

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
        pitch: 45,
        duration: 1400,
        essential: true
      });
    }
  }));

  // Initialize MapLibre GL map and deck.gl MapboxOverlay
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    let mapInstance: maplibregl.Map;

    try {
      mapInstance = new maplibregl.Map({
        container: mapContainerRef.current,
        style: BASEMAP_STYLE,
        center: CITY_COORDINATES.Raleigh.center,
        zoom: CITY_COORDINATES.Raleigh.zoom,
        pitch: CITY_COORDINATES.Raleigh.pitch,
        bearing: CITY_COORDINATES.Raleigh.bearing,
        attributionControl: false
      });
    } catch {
      // Graceful fallback to raster OSM style if GL style fetch fails
      mapInstance = new maplibregl.Map({
        container: mapContainerRef.current,
        style: FALLBACK_STYLE,
        center: CITY_COORDINATES.Raleigh.center,
        zoom: CITY_COORDINATES.Raleigh.zoom,
        attributionControl: false
      });
    }

    // Standard map navigation controls
    mapInstance.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
    mapInstance.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left');

    // Create deck.gl MapboxOverlay
    const overlayInstance = new MapboxOverlay({
      interleaved: false,
      layers: []
    });

    mapInstance.addControl(overlayInstance as unknown as maplibregl.IControl);

    mapRef.current = mapInstance;
    overlayRef.current = overlayInstance;

    // Handle map container resize
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

    // Layer 1: Glow halo under selected segment
    if (selectedSegment) {
      layers.push(
        new PathLayer<RoadSegment>({
          id: 'selected-segment-glow',
          data: [selectedSegment],
          pickable: false,
          widthScale: 1,
          widthMinPixels: 10,
          widthMaxPixels: 22,
          rounded: true,
          capRounded: true,
          jointRounded: true,
          getPath: (d) => d.path,
          getColor: [56, 189, 248, 220], // Radiant cyan halo
          getWidth: 16
        })
      );
    }

    // Layer 2: Main Road Segments PathLayer
    layers.push(
      new PathLayer<RoadSegment>({
        id: 'road-segments-path-layer',
        data: segments,
        pickable: true,
        widthScale: 1,
        widthMinPixels: 4,
        widthMaxPixels: 16,
        rounded: true,
        capRounded: true,
        jointRounded: true,
        getPath: (d) => d.path,
        getColor: (d) => {
          if (selectedSegment && selectedSegment.seg_id === d.seg_id) {
            return [255, 255, 255, 255]; // Crisp white core on selection
          }
          return getScoreRGBA(d.score, 240);
        },
        getWidth: (d) => {
          if (selectedSegment && selectedSegment.seg_id === d.seg_id) {
            return 9;
          }
          return 5;
        },
        updateTriggers: {
          getColor: [selectedSegment?.seg_id],
          getWidth: [selectedSegment?.seg_id]
        },
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

    overlayRef.current.setProps({ layers });
  }, [segments, selectedSegment, onSelectSegment]);

  return (
    <div className="map-view-wrapper">
      <div ref={mapContainerRef} className="map-container" />

      {/* Floating Hover Tooltip */}
      {hoveredInfo.segment && (
        <div
          className="map-tooltip"
          style={{
            transform: `translate(${hoveredInfo.x + 14}px, ${hoveredInfo.y + 14}px)`
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
