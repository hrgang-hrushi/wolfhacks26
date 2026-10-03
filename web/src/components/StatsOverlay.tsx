import type { FC } from 'react';
import { Activity, AlertTriangle, TrendingDown } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';

interface StatsOverlayProps {
  segments: RoadSegment[];
}

export const StatsOverlay: FC<StatsOverlayProps> = ({ segments }) => {
  if (segments.length === 0) return null;

  const total = segments.length;
  const avgRating = Math.round(segments.reduce((acc, s) => acc + s.pv_rating, 0) / total);
  const criticalCount = segments.filter((s) => s.score < 0.4 || s.pv_rating < 50).length;
  const avgYearsToPoor = (segments.reduce((acc, s) => acc + s.years_to_poor, 0) / total).toFixed(1);

  return (
    <div className="stats-overlay" aria-label="System Metrics Summary">
      <div className="stat-card">
        <div className="stat-header">
          <Activity size={13} className="text-cyan-400" />
          <span className="stat-title">AVG NETWORK RATING</span>
        </div>
        <div className="stat-value-row">
          <span className="stat-number">{avgRating}</span>
          <span className="stat-unit">/100</span>
        </div>
        <span className="stat-subtitle">Across active filter</span>
      </div>

      <div className="stat-card">
        <div className="stat-header">
          <AlertTriangle size={13} className="text-rose-400" />
          <span className="stat-title">HIGH URGENCY</span>
        </div>
        <div className="stat-value-row">
          <span className="stat-number text-rose-400">{criticalCount}</span>
          <span className="stat-unit text-rose-300">/ {total}</span>
        </div>
        <span className="stat-subtitle">Critical distress priority</span>
      </div>

      <div className="stat-card">
        <div className="stat-header">
          <TrendingDown size={13} className="text-amber-400" />
          <span className="stat-title">MEAN YEARS TO POOR</span>
        </div>
        <div className="stat-value-row">
          <span className="stat-number text-amber-400">{avgYearsToPoor}</span>
          <span className="stat-unit">yrs</span>
        </div>
        <span className="stat-subtitle">Deterioration horizon</span>
      </div>
    </div>
  );
};
