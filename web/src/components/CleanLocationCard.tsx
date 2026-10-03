import { useState } from 'react';
import { Heart, Eye, Thermometer, Calendar } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';

interface CleanLocationCardProps {
  selectedSegment: RoadSegment | null;
}

export const CleanLocationCard: React.FC<CleanLocationCardProps> = ({ selectedSegment }) => {
  const [isFavorite, setIsFavorite] = useState(true);
  const [useReferenceText, setUseReferenceText] = useState(true);

  const seg = selectedSegment;

  return (
    <div className="clean-location-card">
      {/* Top Header Row */}
      <div className="location-top-section">
        <div className="location-header-row">
          <h2
            className="location-title"
            onClick={() => setUseReferenceText(!useReferenceText)}
            title="Click to toggle between Reference mockup text and live telemetry"
          >
            Location
          </h2>

          {/* Golden Amber Heart Favorite Toggle */}
          <button
            type="button"
            className="heart-btn"
            onClick={() => setIsFavorite(!isFavorite)}
            title="Save location"
            aria-label="Save location"
          >
            <Heart
              size={20}
              fill={isFavorite ? '#f59e0b' : 'none'}
              color={isFavorite ? '#f59e0b' : '#9ca3af'}
            />
          </button>
        </div>

        {/* Address / Road Name Line */}
        <p className="location-address">
          {useReferenceText
            ? '789 Costa Mesa, Los Angeles, CA 90210'
            : (seg ? `${seg.name}, ${seg.city}, NC 27607` : 'Capital Blvd (US-401), Raleigh, NC')}
        </p>

        {/* Meta Line: HO tags on left, Date on right */}
        <div className="location-meta-row">
          <span className="location-ho-text">
            {useReferenceText
              ? 'HO-1 , HO-3, HO-7'
              : (seg ? seg.drivers.join(' • ') : 'High Traffic • Freeze-Thaw • Drainage')}
          </span>
          <span className="location-date-text">
            {useReferenceText ? '31 Jan 2025' : 'Surveyed Oct 2026'}
          </span>
        </div>
      </div>

      {/* 3 Metric Sub-Cards Grid matching reference */}
      <div className="location-subcards-grid">
        {/* Sub-Card 1: Building Age */}
        <div className="sub-metric-card">
          <div className="sub-metric-circle-icon">
            <Calendar size={18} strokeWidth={1.8} color="#6b7280" />
          </div>
          <div className="sub-metric-bottom">
            <span className="sub-metric-label">
              {useReferenceText ? 'Building Age' : 'Pavement Age'}
            </span>
            <span className="sub-metric-value">
              {useReferenceText ? '5Y' : (seg ? `${seg.pv_age}Y` : '5.3Y')}
            </span>
          </div>
        </div>

        {/* Sub-Card 2: Daily Visitors */}
        <div className="sub-metric-card">
          <div className="sub-metric-circle-icon">
            <Eye size={18} strokeWidth={1.8} color="#6b7280" />
          </div>
          <div className="sub-metric-bottom">
            <span className="sub-metric-label">
              {useReferenceText ? 'Daily Visitors' : 'Years to Poor'}
            </span>
            <span className="sub-metric-value">
              {useReferenceText ? '10,742' : (seg ? `${seg.years_to_poor}Y` : '7.4Y')}
            </span>
          </div>
        </div>

        {/* Sub-Card 3: Temperature */}
        <div className="sub-metric-card">
          <div className="sub-metric-circle-icon">
            <Thermometer size={18} strokeWidth={1.8} color="#6b7280" />
          </div>
          <div className="sub-metric-bottom">
            <span className="sub-metric-label">
              {useReferenceText ? 'Temperature' : 'Flood Rank'}
            </span>
            <span className="sub-metric-value">
              {useReferenceText
                ? '29°F'
                : (seg ? (typeof seg.flood_rank === 'string' && seg.flood_rank.includes('Zone AE') ? 'Zone AE' : 'Tier 1') : '29°F')}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
