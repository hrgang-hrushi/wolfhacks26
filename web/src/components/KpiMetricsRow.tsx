import type { FC } from 'react';
import {
  Briefcase,
  Filter,
  AlertTriangle,
  UserCheck,
  ArrowUpRight,
  ArrowDown,
  ArrowUp,
  Minus
} from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';

interface KpiMetricsRowProps {
  segments: RoadSegment[];
}

export const KpiMetricsRow: FC<KpiMetricsRowProps> = () => {
  return (
    <div className="kpi-metrics-row-grid">
      {/* Card 1: Close Deals */}
      <div className="kpi-card">
        <div className="kpi-card-header">
          <div className="kpi-title-with-icon">
            <div className="kpi-icon-wrap">
              <Briefcase size={15} />
            </div>
            <span className="kpi-title-text">Close Deals</span>
          </div>
          <button type="button" className="kpi-arrow-btn" aria-label="View close deals">
            <ArrowUpRight size={14} />
          </button>
        </div>

        <div className="kpi-value-row">
          <span className="kpi-big-num">956</span>
          <div className="kpi-badge-pill pill-red">
            <ArrowDown size={11} />
            <span>1012 vs last month</span>
          </div>
        </div>
      </div>

      {/* Card 2: Conversion Rate */}
      <div className="kpi-card">
        <div className="kpi-card-header">
          <div className="kpi-title-with-icon">
            <div className="kpi-icon-wrap">
              <Filter size={15} />
            </div>
            <span className="kpi-title-text">Conversion Rate</span>
          </div>
          <button type="button" className="kpi-arrow-btn" aria-label="View conversion rate">
            <ArrowUpRight size={14} />
          </button>
        </div>

        <div className="kpi-value-row">
          <span className="kpi-big-num">22%</span>
          <div className="kpi-badge-pill pill-green">
            <ArrowUp size={11} />
            <span>19% vs last month</span>
          </div>
        </div>
      </div>

      {/* Card 3: Weak Areas */}
      <div className="kpi-card">
        <div className="kpi-card-header">
          <div className="kpi-title-with-icon">
            <div className="kpi-icon-wrap">
              <AlertTriangle size={15} />
            </div>
            <span className="kpi-title-text">Weak Areas</span>
          </div>
          <button type="button" className="kpi-arrow-btn" aria-label="View weak areas">
            <ArrowUpRight size={14} />
          </button>
        </div>

        <div className="kpi-value-row">
          <span className="kpi-big-num">4</span>
          <div className="kpi-badge-pill pill-amber">
            <Minus size={11} />
            <span>4 vs last month</span>
          </div>
        </div>
      </div>

      {/* Card 4: Active Reps */}
      <div className="kpi-card">
        <div className="kpi-card-header">
          <div className="kpi-title-with-icon">
            <div className="kpi-icon-wrap">
              <UserCheck size={15} />
            </div>
            <span className="kpi-title-text">Active Reps</span>
          </div>
          <button type="button" className="kpi-arrow-btn" aria-label="View active reps">
            <ArrowUpRight size={14} />
          </button>
        </div>

        <div className="kpi-value-row">
          <span className="kpi-big-num">175</span>
          <div className="kpi-badge-pill pill-green">
            <ArrowDown size={11} />
            <span>144 vs last month</span>
          </div>
        </div>
      </div>
    </div>
  );
};
