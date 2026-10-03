import type { FC } from 'react';
import type { RoadSegment } from '../types/roadSegment';

interface CleanPhotoCardProps {
  selectedSegment: RoadSegment | null;
}

export const CleanPhotoCard: FC<CleanPhotoCardProps> = ({ selectedSegment: _selectedSegment }) => {
  return (
    <div className="pixel-photo-card" title="Modern Architecture">
      <img
        src="/assets/reference/architecture_card.webp"
        alt="Modern Architecture"
        className="card-crop-img photo-zoom-img"
      />
    </div>
  );
};
