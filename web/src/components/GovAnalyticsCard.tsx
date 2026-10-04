import React, { useMemo } from 'react';
import type { RoadSegment } from '../types/roadSegment';
import { Activity, ChevronRight } from 'lucide-react';

interface GovAnalyticsCardProps {
  selectedSegment: RoadSegment | null;
  onOpenDetails?: () => void;
}

export const GovAnalyticsCard: React.FC<GovAnalyticsCardProps> = ({
  selectedSegment,
  onOpenDetails
}) => {
  const seg = selectedSegment;
  const rating = seg ? seg.pv_rating : 81;
  const yearsToPoor = seg ? Math.max(0.8, seg.years_to_poor) : 4.6;

  // Real ML wear rate (PCI degradation points per year)
  const wearRate = useMemo(() => {
    if (seg?.pred_rate && seg.pred_rate > 0) {
      return seg.pred_rate;
    }
    const drop = Math.max(5, rating - 60);
    return Math.max(0.8, Math.min(6.5, drop / yearsToPoor));
  }, [seg, rating, yearsToPoor]);

  // SVG Chart Geometry
  const W = 460;
  const H = 135;
  const padL = 36;
  const padR = 24;
  const padT = 16;
  const padB = 26;

  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  const maxYears = 15;
  const minPCI = 30;
  const maxPCI = 100;
  const poorThreshold = 60;

  const xPos = (yr: number) => padL + (yr / maxYears) * chartW;
  const yPos = (pci: number) => padT + ((maxPCI - Math.max(minPCI, Math.min(maxPCI, pci))) / (maxPCI - minPCI)) * chartH;

  const startX = xPos(0);
  const startY = yPos(rating);

  const endPCI = Math.max(minPCI, rating - wearRate * maxYears);
  const endX = xPos(maxYears);
  const endY = yPos(endPCI);

  // Exact intercept year with 60 PCI poor threshold
  const crossYear = rating > poorThreshold ? (rating - poorThreshold) / wearRate : 0;
  const crossX = xPos(Math.min(maxYears, crossYear));
  const crossY = yPos(poorThreshold);

  const thresholdY = yPos(poorThreshold);

  // Polygon points for area fill under the trajectory
  const areaPoints = `${startX},${startY} ${endX},${endY} ${endX},${yPos(minPCI)} ${startX},${yPos(minPCI)}`;

  return (
    <div
      className="pixel-gov-analytics-card live-html-card degradation-card"
      onClick={onOpenDetails}
      style={{ cursor: 'pointer' }}
      title="Click to view full NCDOT wear model and deterioration telemetry"
    >
      <div className="gov-card-inner">
        {/* Header Row */}
        <div className="gov-header-row">
          <div className="gov-title-cluster">
            <div className="gov-title-tag-row">
              <span className="gov-tag-pill">
                <Activity size={10} className="text-emerald-600" />
                NCDOT DEGRADATION MODEL
              </span>
              <span className="gov-jurisdiction-label">
                {seg ? seg.name : 'Capital Blvd (US-401)'}
              </span>
            </div>
            <h2 className="gov-main-title">Infrastructure Life-Cycle Forecast</h2>
            <p className="gov-subtitle">
              Linear wear projection at <strong>-{wearRate.toFixed(1)} PCI/yr</strong> • Action horizon {yearsToPoor.toFixed(1)} yrs
            </p>
          </div>
          <div className="gov-arrow-indicator" aria-hidden="true">
            <ChevronRight size={14} />
          </div>
        </div>

        {/* Minimalist Authentic Linear Wear Projection Chart */}
        <div className="gov-projection-container">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="gov-projection-svg"
            role="img"
            aria-label={`Linear projection from current rating of ${rating} PCI at -${wearRate.toFixed(1)} wear rate`}
          >
            <defs>
              <linearGradient id="wearSlopeFade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#059669" stopOpacity="0.14" />
                <stop offset="100%" stopColor="#059669" stopOpacity="0.01" />
              </linearGradient>
            </defs>

            {/* Horizontal Gridlines & PCI Y Ticks */}
            {[100, 80, 60, 40].map((pci) => (
              <g key={pci}>
                <line
                  x1={padL}
                  y1={yPos(pci)}
                  x2={W - padR}
                  y2={yPos(pci)}
                  stroke={pci === poorThreshold ? '#fca5a5' : '#f1f5f9'}
                  strokeWidth={pci === poorThreshold ? 1.2 : 1}
                  strokeDasharray={pci === poorThreshold ? '4 3' : undefined}
                />
                <text
                  x={padL - 6}
                  y={yPos(pci) + 3.5}
                  textAnchor="end"
                  className={`chart-tick-label ${pci === poorThreshold ? 'warn' : ''}`}
                >
                  {pci}
                </text>
              </g>
            ))}

            {/* Poor Threshold Label */}
            <text
              x={W - padR}
              y={thresholdY - 4}
              textAnchor="end"
              className="chart-threshold-badge"
            >
              Action Threshold (60 PCI)
            </text>

            {/* X-Axis Year Ticks */}
            {[0, 3, 6, 9, 12, 15].map((yr) => (
              <text
                key={yr}
                x={xPos(yr)}
                y={H - 8}
                textAnchor="middle"
                className="chart-tick-label"
              >
                {2026 + yr}
              </text>
            ))}

            {/* Subtle Gradient Area under slope */}
            <polygon points={areaPoints} fill="url(#wearSlopeFade)" />

            {/* Projection Line */}
            <line
              x1={startX}
              y1={startY}
              x2={endX}
              y2={endY}
              stroke="#0f172a"
              strokeWidth="2"
              strokeLinecap="round"
            />

            {/* Origin Node (Present Survey Rating) */}
            <circle cx={startX} cy={startY} r="3.5" fill="#0f172a" />
            <text x={startX + 6} y={startY - 6} className="chart-point-annotation">
              {rating} PCI (Now)
            </text>

            {/* Critical Intercept Marker at 60 PCI */}
            {crossYear > 0 && crossYear <= maxYears && (
              <g>
                <circle cx={crossX} cy={crossY} r="4" fill="#ef4444" stroke="#ffffff" strokeWidth="1.5" />
                <text
                  x={Math.min(W - padR - 55, crossX + 6)}
                  y={crossY + 12}
                  className="chart-intercept-annotation"
                >
                  Year {crossYear.toFixed(1)} (Critical)
                </text>
              </g>
            )}
          </svg>
        </div>

        {/* Clean Footer Telemetry */}
        <div className="gov-footer-telemetry">
          <span className="gov-footer-note">
            Target Intervention: <strong>Within {yearsToPoor.toFixed(1)} Years</strong>
          </span>
          <span className="gov-footer-rating">
            Current Score: <strong>{rating} / 100</strong>
          </span>
        </div>
      </div>
    </div>
  );
};
