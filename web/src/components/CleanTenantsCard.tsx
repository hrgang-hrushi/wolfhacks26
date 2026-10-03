import type { FC } from 'react';
import type { RoadSegment } from '../types/roadSegment';

interface CleanTenantsCardProps {
  selectedSegment: RoadSegment | null;
}

export const CleanTenantsCard: FC<CleanTenantsCardProps> = ({ selectedSegment: _selectedSegment }) => {
  return (
    <div className="pixel-tenants-card" title="Tenants & Community">
      <img
        src="/assets/reference/tenants_card_crop.webp"
        alt="Tenants"
        className="card-crop-img"
      />
    </div>
  );
};
