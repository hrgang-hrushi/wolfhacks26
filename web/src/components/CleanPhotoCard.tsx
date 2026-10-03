import { useState } from 'react';
import { Camera, Satellite, Maximize2 } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';

interface CleanPhotoCardProps {
  selectedSegment: RoadSegment | null;
}

export const CleanPhotoCard: React.FC<CleanPhotoCardProps> = ({ selectedSegment }) => {
  const [viewMode, setViewMode] = useState<'architecture' | 'satellite'>('architecture');

  const seg = selectedSegment;
  const [lng, lat] = seg && seg.path.length > 0
    ? seg.path[Math.floor(seg.path.length / 2)]
    : [-78.6382, 35.7796];

  return (
    <div className="clean-photo-card">
      {/* Background Image: Authentic Reference Architectural Photo or Satellite Chip */}
      {viewMode === 'architecture' ? (
        <div className="photo-image-container">
          <img
            src="/assets/reference/architecture_card.webp"
            alt="Modern Architecture"
            className="photo-main-img"
          />

          {/* Subtle Hover Action overlay to switch to aerial satellite chip */}
          <div className="photo-hover-overlay">
            <button
              type="button"
              className="photo-toggle-btn"
              onClick={() => setViewMode('satellite')}
              title="Switch to Aerial Satellite Orthophoto"
            >
              <Satellite size={14} />
              <span>View Aerial Chip</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="photo-satellite-container">
          {seg?.chip_url ? (
            <img
              src={seg.chip_url}
              alt={`Aerial view of ${seg.seg_id}`}
              className="photo-main-img"
            />
          ) : (
            <div className="satellite-simulation-view">
              <div className="satellite-grid" />
              <div className="satellite-hud">
                <div className="hud-header">
                  <span className="hud-badge">0.15m GSD ORTHOPHOTO</span>
                  <button
                    type="button"
                    className="hud-back-btn"
                    onClick={() => setViewMode('architecture')}
                    title="Back to Reference Architecture"
                  >
                    <Camera size={13} />
                    <span>Mockup View</span>
                  </button>
                </div>

                <div className="hud-center">
                  <div className="hud-crosshair" />
                  <span className="hud-coords">
                    {lat.toFixed(4)}°N, {Math.abs(lng).toFixed(4)}°W
                  </span>
                  <span className="hud-id">
                    CHIP #{seg ? seg.seg_id : 'NC-RAL-001'}
                  </span>
                </div>

                <div className="hud-footer">
                  <span>USGS NAIP High-Res Pavement Corridor</span>
                  <Maximize2 size={14} className="hud-zoom-icon" />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
