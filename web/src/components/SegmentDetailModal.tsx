import type { FC } from 'react';
import { X, Navigation, Calendar, Clock, ShieldAlert, Sparkles, Building2, MapPin } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { getConditionInfo } from '../utils/colors';
import { AerialChip } from './AerialChip';

interface SegmentDetailModalProps {
  segment: RoadSegment | null;
  onClose: () => void;
  onFlyTo: (segment: RoadSegment) => void;
}

export const SegmentDetailModal: FC<SegmentDetailModalProps> = ({
  segment,
  onClose,
  onFlyTo
}) => {
  if (!segment) return null;

  const condition = getConditionInfo(segment.score);
  const isNcdot = segment.source === 'ncdot';

  return (
    <div className="segment-detail-drawer" aria-label="Road segment inspection details">
      <div className="drawer-header-light">
        <div className="drawer-badges-row">
          <span className={`jurisdiction-pill ${isNcdot ? 'pill-state' : 'pill-municipal'}`}>
            <Building2 size={12} />
            {isNcdot ? 'State Highway (NCDOT)' : 'City Municipal Street'}
          </span>
          <span className="city-location-pill">
            <MapPin size={12} />
            {segment.city}
          </span>
        </div>

        <div className="drawer-title-close-row">
          <div>
            <h2 className="drawer-segment-name">{segment.name}</h2>
            <span className="drawer-segment-id">Segment ID: <code>{segment.seg_id}</code></span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="drawer-close-circle-btn"
            aria-label="Close details"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="drawer-scroll-body">
        {/* Pavement Condition Rating Card */}
        <div className="detail-metric-card rating-highlight-card">
          <div className="card-sub-header">
            <span className="sub-header-title">PAVEMENT CONDITION RATING</span>
            <span
              className="condition-pill-badge"
              style={{ backgroundColor: condition.color, color: '#FFFFFF' }}
            >
              {condition.category.toUpperCase()}
            </span>
          </div>
          <div className="rating-value-display">
            <span className="big-rating-num" style={{ color: condition.color }}>
              {segment.pv_rating}
            </span>
            <span className="rating-max-scale">/ 100</span>
            <div className="model-confidence-tag">
              Score: <strong>{(segment.score * 100).toFixed(0)}%</strong>
            </div>
          </div>
          <div className="rating-progress-track">
            <div
              className="rating-progress-bar"
              style={{
                width: `${Math.max(5, Math.min(100, segment.pv_rating))}%`,
                backgroundColor: condition.color
              }}
            />
          </div>
        </div>

        {/* 1:1 Aspect Ratio Square Aerial Photo Placeholder */}
        <div className="aerial-section-wrap">
          <AerialChip segment={segment} />
        </div>

        {/* 2-Column Metrics Grid */}
        <div className="detail-two-col-grid">
          {/* Pavement Age */}
          <div className="detail-metric-card">
            <div className="col-metric-title">
              <Calendar size={13} className="text-amber-500" />
              <span>PAVEMENT AGE</span>
            </div>
            <div className="col-metric-val">
              {segment.pv_age} <span className="val-unit">yrs</span>
            </div>
            <span className="col-metric-sub">Since last repaving</span>
          </div>

          {/* Predicted Years to Poor */}
          <div className="detail-metric-card">
            <div className="col-metric-title">
              <Clock size={13} className="text-rose-500" />
              <span>YEARS TO POOR</span>
            </div>
            <div className="col-metric-val text-rose-500">
              {segment.years_to_poor} <span className="val-unit">yrs</span>
            </div>
            <span className="col-metric-sub">Deterioration horizon</span>
          </div>
        </div>

        {/* Flood Vulnerability Rank */}
        <div className="detail-metric-card flood-vulnerability-card">
          <div className="col-metric-title">
            <ShieldAlert size={14} className="text-cyan-600" />
            <span>FLOOD VULNERABILITY RANK</span>
          </div>
          <div className="flood-tier-value">{segment.flood_rank}</div>
          <p className="flood-detail-desc">
            Calculated from FEMA hydrological zones, terrain runoff slope, and storm surge susceptibility.
          </p>
        </div>

        {/* Top 3 Degradation Drivers */}
        <div className="detail-metric-card drivers-breakdown-card">
          <div className="card-sub-header">
            <div className="flex items-center gap-1.5">
              <Sparkles size={14} className="text-amber-500" />
              <span className="sub-header-title">TOP 3 DETERIORATION DRIVERS</span>
            </div>
            <span className="ai-model-tag">AI Attribution</span>
          </div>

          <div className="drivers-reasons-list">
            {segment.drivers.map((driver, i) => (
              <div key={i} className="driver-reason-box">
                <span className="reason-rank-number">#{i + 1}</span>
                <span className="reason-text">{driver}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Fly to Segment Action */}
        <div className="detail-action-footer">
          <button
            type="button"
            onClick={() => onFlyTo(segment)}
            className="center-segment-btn"
          >
            <Navigation size={14} />
            <span>Center &amp; Zoom on Road</span>
          </button>
        </div>
      </div>
    </div>
  );
};
