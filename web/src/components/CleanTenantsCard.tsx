import { useState } from 'react';
import type { RoadSegment } from '../types/roadSegment';

interface CleanTenantsCardProps {
  selectedSegment: RoadSegment | null;
}

export const CleanTenantsCard: React.FC<CleanTenantsCardProps> = ({ selectedSegment }) => {
  const [useReferenceText, setUseReferenceText] = useState(true);

  const rating = selectedSegment ? selectedSegment.pv_rating : 85;

  return (
    <div className="clean-tenants-card">
      {/* Header Row */}
      <div className="tenants-header-row">
        <div className="tenants-title-group">
          <h2
            className="tenants-title"
            onClick={() => setUseReferenceText(!useReferenceText)}
            title="Click to toggle between Reference Tenants and Pavement Rating"
          >
            {useReferenceText ? 'Tenants' : 'Pavement Rating'}
          </h2>
          <p className="tenants-subtitle">
            {useReferenceText
              ? 'Join our growing\ncommunity of active\nmembers.'
              : 'NC DOT & AI pavement\ndistress index score\nconfidence.'}
          </p>
        </div>

        {/* Avatars Cluster matching reference */}
        <div className="tenants-avatar-cluster" title="Active Community & Surveyors">
          <img
            src="/assets/reference/avatars.webp"
            alt="Tenants & Surveyors"
            className="tenants-avatars-img"
          />
        </div>
      </div>

      {/* Donut Slice Gauge Matching Reference (ref_card3.png) */}
      <div className="tenants-gauge-area">
        <svg
          viewBox="0 0 320 220"
          className="tenants-gauge-svg"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            {/* Smooth Amber Gradient */}
            <linearGradient id="amberDonutGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#f59e0b" />
              <stop offset="100%" stopColor="#e8931a" />
            </linearGradient>
          </defs>

          {/* Background Soft Track Ring */}
          <path
            d="M 25 180 A 130 130 0 0 1 270 180"
            fill="none"
            stroke="#f2f5f7"
            strokeWidth="38"
            strokeLinecap="butt"
          />

          {/* Active Amber Filled Donut Slice (from 180 deg to ~45 deg) */}
          <path
            d="M 25 180 A 130 130 0 0 1 228 88"
            fill="none"
            stroke="url(#amberDonutGrad)"
            strokeWidth="38"
            strokeLinecap="butt"
          />

          {/* Fine Outer Golden Edge Line matching reference */}
          <path
            d="M 12 180 A 148 148 0 0 1 245 74"
            fill="none"
            stroke="#e8931a"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </svg>

        {/* Center Values */}
        <div className="tenants-gauge-center">
          <span className="gauge-number">
            {useReferenceText ? '8,5k' : rating}
          </span>
          <span className="gauge-label">
            {useReferenceText ? 'members' : 'pavement score'}
          </span>
        </div>
      </div>
    </div>
  );
};
