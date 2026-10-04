import { useRef, useImperativeHandle, forwardRef } from 'react';
import { ArrowUpRight, ZoomIn, ZoomOut, Hand } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { MapView, type MapViewHandle } from './MapView';
import { RadialGauge } from './RadialGauge';

export interface MainMapCardHandle {
  flyToCity: (city: 'Asheville' | 'Raleigh') => void;
  flyToSegment: (segment: RoadSegment) => void;
}

interface MainMapCardProps {
  segments: RoadSegment[];
  selectedSegment: RoadSegment | null;
  onSelectSegment: (segment: RoadSegment) => void;
}

export const MainMapCard = forwardRef<MainMapCardHandle, MainMapCardProps>(({
  segments,
  selectedSegment,
  onSelectSegment
}, ref) => {
  const mapViewRef = useRef<MapViewHandle>(null);

  useImperativeHandle(ref, () => ({
    flyToCity: (city: 'Asheville' | 'Raleigh') => {
      mapViewRef.current?.flyToCity(city);
    },
    flyToSegment: (segment: RoadSegment) => {
      mapViewRef.current?.flyToSegment(segment);
    }
  }));

  return (
    <div className="analytics-card main-map-card">
      {/* Card Header */}
      <div className="card-top-header">
        <h3 className="card-heading">Underperforming areas</h3>
        <button type="button" className="card-arrow-btn" aria-label="Expand map view">
          <ArrowUpRight size={14} />
        </button>
      </div>

      {/* Map Viewport */}
      <div className="map-embed-wrapper">
        <MapView
          ref={mapViewRef}
          segments={segments}
          selectedSegment={selectedSegment}
          onSelectSegment={onSelectSegment}
        />

        {/* Floating Region Badges matching frame 7 */}
        <div className="map-region-badges-overlay pointer-events-none">
          <div className="region-tag tag-raleigh">
            <span className="region-dot-pulse" />
            <span>Raleigh / NC</span>
          </div>

          <div className="region-tag tag-asheville">
            <span className="region-dot-pulse" />
            <span>Asheville / NC</span>
          </div>

          <div className="region-tag tag-texas">
            <span className="region-dot-pulse" />
            <span>Texas</span>
          </div>

          <div className="region-tag tag-california">
            <span className="region-dot-pulse" />
            <span>California</span>
          </div>
        </div>

        {/* Floating Zoom Controls Pill at bottom right of map matching frame 7 */}
        <div className="map-floating-controls-pill">
          <button
            type="button"
            className="map-pill-ctrl-btn"
            title="Zoom In"
            onClick={() => {
              const canvas = document.querySelector('.maplibregl-canvas');
              if (canvas) {
                const event = new WheelEvent('wheel', { deltaY: -120 });
                canvas.dispatchEvent(event);
              }
            }}
          >
            <ZoomIn size={15} />
          </button>
          <button
            type="button"
            className="map-pill-ctrl-btn"
            title="Zoom Out"
            onClick={() => {
              const canvas = document.querySelector('.maplibregl-canvas');
              if (canvas) {
                const event = new WheelEvent('wheel', { deltaY: 120 });
                canvas.dispatchEvent(event);
              }
            }}
          >
            <ZoomOut size={15} />
          </button>
          <button
            type="button"
            className="map-pill-ctrl-btn"
            title="Pan Mode"
          >
            <Hand size={15} />
          </button>
        </div>
      </div>

      {/* 4 Radial Semi-Gauges matching frame 7 */}
      <div className="map-bottom-gauges-row">
        <RadialGauge
          percentage={64}
          label="California"
          subValue="$8.3m"
          colorType="green"
        />
        <RadialGauge
          percentage={32}
          label="Alaska"
          subValue="$2.1m"
          colorType="yellow"
        />
        <RadialGauge
          percentage={57}
          label="Texas"
          subValue="$6.4m"
          colorType="lime"
        />
        <RadialGauge
          percentage={13}
          label="Florida"
          subValue="$1.2m"
          colorType="red"
        />
      </div>
    </div>
  );
});

MainMapCard.displayName = 'MainMapCard';
