import { useState } from 'react';
import type { RoadSegment } from '../types/roadSegment';

interface CleanLocationCardProps {
  selectedSegment: RoadSegment | null;
}

export const CleanLocationCard: React.FC<CleanLocationCardProps> = ({ selectedSegment }) => {
  const [isFavorite, setIsFavorite] = useState(true);

  return (
    <div className="pixel-location-card">
      {/* High-Resolution Location Card Crop matching reference pixel-to-pixel */}
      <img
        src="/assets/reference/location_card_crop.webp"
        alt="Location Details"
        className="card-crop-img"
      />

      {/* Interactive Overlays */}
      <button
        type="button"
        className="heart-interactive-overlay"
        onClick={() => setIsFavorite(!isFavorite)}
        title="Toggle favorite"
        aria-label="Toggle favorite"
      />

      {/* Subcard Interactive Areas */}
      <div className="subcards-overlay-container">
        <div
          className="subcard-clickable-area"
          title={`Pavement / Building Age: ${selectedSegment ? selectedSegment.pv_age + 'Y' : '5Y'}`}
        />
        <div
          className="subcard-clickable-area"
          title={`Visitors / Traffic: ${selectedSegment ? selectedSegment.years_to_poor + ' Y to Poor' : '10,742'}`}
        />
        <div
          className="subcard-clickable-area"
          title={`Temperature / Climate: ${selectedSegment ? selectedSegment.flood_rank : '29°F'}`}
        />
      </div>
    </div>
  );
};
