import type { FC } from 'react';
import { ArrowUpRight } from 'lucide-react';

export const DonutChartCard: FC = () => {
  return (
    <div className="analytics-card donut-chart-card">
      <div className="card-top-header">
        <h3 className="card-heading">Sales platforms</h3>
        <button type="button" className="card-arrow-btn" aria-label="Expand platforms breakdown">
          <ArrowUpRight size={14} />
        </button>
      </div>

      <div className="donut-chart-container">
        {/* Floating Percentage Pills */}
        <div className="donut-pill pill-18">18%</div>
        <div className="donut-pill pill-26">26%</div>
        <div className="donut-pill pill-56">56%</div>

        {/* SVG Donut Ring */}
        <svg viewBox="0 0 160 160" className="donut-svg">
          <defs>
            <linearGradient id="donut-green" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#A3E635" />
              <stop offset="100%" stopColor="#84CC16" />
            </linearGradient>
            <linearGradient id="donut-yellow" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FDE047" />
              <stop offset="100%" stopColor="#F59E0B" />
            </linearGradient>
            <linearGradient id="donut-coral" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#F87171" />
              <stop offset="100%" stopColor="#EF4444" />
            </linearGradient>
          </defs>

          {/* Background circle track */}
          <circle
            cx="80"
            cy="80"
            r="56"
            fill="none"
            stroke="#F8F9FA"
            strokeWidth="20"
          />

          {/* Segment 1: Green (56%) -> 0.56 * 351.86 = 197.04 */}
          <circle
            cx="80"
            cy="80"
            r="56"
            fill="none"
            stroke="url(#donut-green)"
            strokeWidth="18"
            strokeDasharray="197 352"
            strokeDashoffset="0"
            strokeLinecap="round"
            transform="rotate(-50 80 80)"
          />

          {/* Segment 2: Yellow (26%) -> 0.26 * 351.86 = 91.48 */}
          <circle
            cx="80"
            cy="80"
            r="56"
            fill="none"
            stroke="url(#donut-yellow)"
            strokeWidth="18"
            strokeDasharray="91 352"
            strokeDashoffset="-203"
            strokeLinecap="round"
            transform="rotate(-50 80 80)"
          />

          {/* Segment 3: Coral (18%) -> 0.18 * 351.86 = 63.33 */}
          <circle
            cx="80"
            cy="80"
            r="56"
            fill="none"
            stroke="url(#donut-coral)"
            strokeWidth="18"
            strokeDasharray="63 352"
            strokeDashoffset="-300"
            strokeLinecap="round"
            transform="rotate(-50 80 80)"
          />
        </svg>
      </div>

      {/* Legend at bottom */}
      <div className="donut-legend-row">
        <div className="legend-item">
          <span className="legend-dot dot-green" />
          <span>Amazon</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-yellow" />
          <span>Ebay</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-pink" />
          <span>Shopify</span>
        </div>
      </div>
    </div>
  );
};
