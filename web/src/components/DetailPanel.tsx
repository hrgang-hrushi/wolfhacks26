import type { FC } from 'react';
import { X, Navigation, Clock, Calendar, ShieldAlert, Sparkles, Building2, MapPin } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { getConditionInfo } from '../utils/colors';
import { AerialChip } from './AerialChip';

interface DetailPanelProps {
  segment: RoadSegment | null;
  onClose: () => void;
  onFlyTo: (segment: RoadSegment) => void;
}

export const DetailPanel: FC<DetailPanelProps> = ({ segment, onClose, onFlyTo }) => {
  if (!segment) return null;

  const condition = getConditionInfo(segment.score);
  const isNcdot = segment.source === 'ncdot';

  return (
    <aside className="detail-panel" aria-label="Road segment inspection details">
      {/* Panel Header */}
      <div className="detail-panel-header">
        <div className="detail-header-info">
          <div className="segment-badge-row">
            <span className={`source-pill ${isNcdot ? 'pill-ncdot' : 'pill-city'}`}>
              <Building2 size={12} />
              {isNcdot ? 'State Highway (NCDOT)' : 'City Municipal Road'}
            </span>
            <span className="city-pill">
              <MapPin size={12} />
              {segment.city}
            </span>
          </div>
          <h2 className="segment-title">{segment.name}</h2>
          <span className="segment-id">Segment ID: <code>{segment.seg_id}</code></span>
        </div>
        <button
          onClick={onClose}
          className="close-button"
          title="Close details panel"
          aria-label="Close"
        >
          <X size={18} />
        </button>
      </div>

      <div className="detail-panel-body">
        {/* Primary Metric: Rating & Condition */}
        <div
          className="metric-card rating-card"
          style={{ borderColor: condition.borderRgba, backgroundColor: condition.bgRgba }}
        >
          <div className="metric-header">
            <span className="metric-label">PAVEMENT CONDITION RATING</span>
            <span
              className="condition-tag"
              style={{ backgroundColor: condition.color, color: '#090d16' }}
            >
              {condition.category.toUpperCase()}
            </span>
          </div>
          <div className="rating-value-row">
            <span className="rating-number" style={{ color: condition.color }}>
              {segment.pv_rating}
            </span>
            <span className="rating-scale">/ 100</span>
            <div className="score-subtext">
              Model Score: <strong>{(segment.score * 100).toFixed(0)}%</strong>
            </div>
          </div>
          <div className="rating-bar-container">
            <div
              className="rating-bar-fill"
              style={{
                width: `${Math.max(5, Math.min(100, segment.pv_rating))}%`,
                backgroundColor: condition.color
              }}
            />
          </div>
        </div>

        {/* Square Aerial Photo Placeholder */}
        <div className="section-block">
          <AerialChip segment={segment} />
        </div>

        {/* 2-Column Core Predictions Grid */}
        <div className="metrics-grid">
          {/* Pavement Age */}
          <div className="metric-card">
            <div className="metric-icon-title">
              <Calendar size={14} className="text-amber-400" />
              <span>PAVEMENT AGE</span>
            </div>
            <div className="metric-big-value">
              {segment.pv_age} <span className="metric-unit">years</span>
            </div>
            <div className="metric-footnote">Since last resurfacing</div>
          </div>

          {/* Predicted Years Until Poor */}
          <div className="metric-card">
            <div className="metric-icon-title">
              <Clock size={14} className="text-rose-400" />
              <span>YEARS TO POOR</span>
            </div>
            <div className="metric-big-value text-rose-400">
              {segment.years_to_poor} <span className="metric-unit">years</span>
            </div>
            <div className="metric-footnote">Predicted failure horizon</div>
          </div>
        </div>

        {/* Flood Vulnerability Rank */}
        <div className="metric-card flood-card">
          <div className="metric-icon-title">
            <ShieldAlert size={15} className="text-cyan-400" />
            <span>FLOOD VULNERABILITY RANK</span>
          </div>
          <div className="flood-rank-value">
            {segment.flood_rank}
          </div>
          <p className="flood-description">
            Sub-base saturation index derived from NOAA hydrological models and terrain slope.
          </p>
        </div>

        {/* Top 3 Degradation Drivers */}
        <div className="drivers-card">
          <div className="drivers-header">
            <div className="flex items-center gap-1.5">
              <Sparkles size={15} className="text-amber-400" />
              <span className="drivers-title">TOP 3 DETERIORATION DRIVERS</span>
            </div>
            <span className="ai-tag">AI Attribution</span>
          </div>
          <ul className="drivers-list">
            {segment.drivers.map((driver, idx) => (
              <li key={idx} className="driver-item">
                <span className="driver-rank-num">#{idx + 1}</span>
                <span className="driver-text">{driver}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Action Button: Fly to Segment */}
        <div className="panel-actions">
          <button
            onClick={() => onFlyTo(segment)}
            className="fly-to-button"
          >
            <Navigation size={15} />
            <span>Center & Zoom on Segment</span>
          </button>
        </div>
      </div>
    </aside>
  );
};
