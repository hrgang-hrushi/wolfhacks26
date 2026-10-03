import type { FC } from 'react';
import { Camera, Satellite, Crosshair, Layers } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';

interface AerialChipProps {
  segment: RoadSegment;
}

export const AerialChip: FC<AerialChipProps> = ({ segment }) => {
  const [lng, lat] = segment.path[Math.floor(segment.path.length / 2)] || [-78.6382, 35.7796];

  return (
    <div className="aerial-chip-container">
      <div className="aerial-chip-header">
        <div className="aerial-chip-title">
          <Satellite size={14} className="text-cyan-400" />
          <span>AERIAL ORTHOPHOTO CHIP</span>
        </div>
        <span className="aerial-chip-badge">0.15m GSD</span>
      </div>

      <div className="aerial-chip-square">
        {segment.chip_url ? (
          <img
            src={segment.chip_url}
            alt={`Aerial view of ${segment.seg_id}`}
            className="aerial-image"
          />
        ) : (
          <div className="aerial-placeholder">
            {/* High-tech satellite simulation texture */}
            <div className="aerial-grid-bg" />
            <div className="aerial-satellite-texture" />
            
            {/* Road trajectory overlay */}
            <svg className="aerial-road-overlay" viewBox="0 0 200 200">
              <defs>
                <linearGradient id="roadGlow" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.8" />
                  <stop offset="100%" stopColor="#818cf8" stopOpacity="0.8" />
                </linearGradient>
              </defs>
              <line
                x1="25"
                y1="165"
                x2="175"
                y2="35"
                stroke="rgba(0,0,0,0.6)"
                strokeWidth="18"
                strokeLinecap="round"
              />
              <line
                x1="25"
                y1="165"
                x2="175"
                y2="35"
                stroke="url(#roadGlow)"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray="8 4"
              />
            </svg>

            {/* Target reticle HUD */}
            <div className="aerial-reticle">
              <Crosshair size={36} className="reticle-icon" />
              <div className="reticle-circle" />
            </div>

            {/* Placeholder notification overlay */}
            <div className="aerial-meta-overlay">
              <div className="aerial-coords">
                {lat.toFixed(5)}°N, {Math.abs(lng).toFixed(5)}°W
              </div>
              <div className="aerial-placeholder-text">
                <Camera size={13} />
                <span>Aerial Photo Placeholder ({segment.seg_id})</span>
              </div>
              <div className="aerial-tag">Ready for Drop-in (chip_url)</div>
            </div>

            {/* Scale indicator */}
            <div className="aerial-scale-bar">
              <div className="scale-line" />
              <span>50 m</span>
            </div>
          </div>
        )}
      </div>

      <div className="aerial-chip-footer">
        <span className="source-label">
          <Layers size={11} /> NAIP / USGS Ortho Layer
        </span>
        <span className="timestamp-label">Q3 Flight Survey</span>
      </div>
    </div>
  );
};
