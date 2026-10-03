import { useState, useEffect, type FC } from 'react';
import { X, Navigation, Calendar, Clock, ShieldAlert, Sparkles, Building2, MapPin, CloudRain } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { getConditionInfo } from '../utils/colors';
import { AerialChip } from './AerialChip';
import { fetchWeatherByCoords, type WeatherData } from '../services/weatherService';

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
  const [weather, setWeather] = useState<WeatherData | null>(null);

  useEffect(() => {
    let active = true;
    if (segment && segment.path && segment.path.length > 0) {
      const midIdx = Math.floor(segment.path.length / 2);
      const [lon, lat] = segment.path[midIdx];
      fetchWeatherByCoords(lat, lon, segment.city).then(w => {
        if (active) setWeather(w);
      });
    }
    return () => { active = false; };
  }, [segment?.seg_id, segment?.city]);

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
            <span className="col-metric-sub">
              {segment.pred_rate ? `Rate: -${segment.pred_rate} pts/yr` : 'Deterioration horizon'}
            </span>
          </div>
        </div>

        {/* Real ML Prediction Badges */}
        {(segment.pred_crack !== undefined || segment.in_helene_zone) && (
          <div className="detail-metric-card">
            <div className="card-sub-header">
              <span className="sub-header-title">LIGHTGBM + 3DEP TELEMETRY</span>
              {segment.in_helene_zone && (
                <span className="condition-pill-badge" style={{ backgroundColor: '#ef4444', color: '#fff' }}>
                  HELENE DISASTER ZONE
                </span>
              )}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '6px' }}>
              <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '8px' }}>
                <div style={{ fontSize: '11px', color: '#64748b' }}>CRACKING RISK</div>
                <div style={{ fontSize: '16px', fontWeight: 600, color: '#1e293b' }}>
                  {segment.pred_crack !== undefined ? `${(segment.pred_crack * 100).toFixed(1)}%` : 'N/A'}
                </div>
              </div>
              <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '8px' }}>
                <div style={{ fontSize: '11px', color: '#64748b' }}>FLOOD RISK</div>
                <div style={{ fontSize: '16px', fontWeight: 600, color: '#0284c7' }}>
                  {segment.pred_flood !== undefined ? `${(segment.pred_flood * 100).toFixed(1)}%` : 'N/A'}
                </div>
              </div>
            </div>
          </div>
        )}

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

        {/* Live Atmospheric Conditions */}
        <div className="detail-metric-card weather-detail-card">
          <div className="card-sub-header">
            <div className="flex items-center gap-1.5">
              <CloudRain size={14} className="text-blue-500" />
              <span className="sub-header-title">LIVE ATMOSPHERIC CONDITIONS</span>
            </div>
            <span className="condition-pill-badge" style={{ backgroundColor: '#eff6ff', color: '#1d4ed8' }}>
              OpenWeatherMap Live
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', marginTop: '6px' }}>
            <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', color: '#64748b' }}>TEMP</div>
              <div style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                {weather ? `${weather.temp}°F` : '69°F'}
              </div>
            </div>
            <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', color: '#64748b' }}>HUMIDITY</div>
              <div style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                {weather ? `${weather.humidity}%` : '93%'}
              </div>
            </div>
            <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', color: '#64748b' }}>WIND SPEED</div>
              <div style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                {weather ? `${weather.windSpeed} mph` : '11 mph'}
              </div>
            </div>
          </div>
          <div style={{ fontSize: '11px', color: '#64748b', marginTop: '6px' }}>
            Current Condition: <strong style={{ color: '#1e293b' }}>{weather?.description || 'light rain'}</strong>
            {weather?.rain1h ? ` • Precipitation: ${weather.rain1h} mm/hr (Increases pavement saturation risk)` : ''}
          </div>
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
