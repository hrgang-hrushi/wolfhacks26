import { useState } from 'react';
import type { FC } from 'react';
import { ArrowUpRight, X } from 'lucide-react';

interface MonthData {
  month: string;
  current: number; // in millions
  previous: number;
  predicted: number;
}

const DEFAULT_DATA: MonthData[] = [
  { month: 'Mar', current: 16.5, previous: 7.2, predicted: 12.8 },
  { month: 'Apr', current: 14.1, previous: 19.5, predicted: 11.2 },
  { month: 'May', current: 7.8, previous: 14.0, predicted: 15.6 },
  { month: 'Jun', current: 18.2, previous: 9.4, predicted: 13.5 },
  { month: 'Jul', current: 9.1, previous: 12.3, predicted: 13.9 },
  { month: 'Aug', current: 28.56, previous: 19.25, predicted: 18.71 },
  { month: 'Sep', current: 19.4, previous: 8.6, predicted: 13.2 },
  { month: 'Oct', current: 9.8, previous: 14.2, predicted: 12.5 },
  { month: 'Nov', current: 8.5, previous: 15.3, predicted: 11.8 },
  { month: 'Dec', current: 17.6, previous: 8.4, predicted: 13.6 },
  { month: 'Jan', current: 11.2, previous: 9.1, predicted: 12.0 },
  { month: 'Feb', current: 9.4, previous: 7.8, predicted: 11.3 }
];

export const RevenueBarChartCard: FC = () => {
  const [activeMonth, setActiveMonth] = useState<string>('Aug');
  const [showTooltip, setShowTooltip] = useState<boolean>(true);

  const maxVal = 32; // max for 30m scaling

  return (
    <div className="analytics-card revenue-chart-card">
      <div className="card-top-header">
        <h3 className="card-heading">CY Revenue vs PY Revenue</h3>
        <button type="button" className="card-arrow-btn" aria-label="Expand chart">
          <ArrowUpRight size={14} />
        </button>
      </div>

      <div className="bar-chart-body">
        {/* Y Axis Guide */}
        <div className="chart-y-axis">
          <span>30m</span>
          <span>20m</span>
          <span>10m</span>
          <span>0</span>
        </div>

        {/* Main Bars Canvas */}
        <div className="chart-bars-container">
          {/* Subtle horizontal grid lines */}
          <div className="chart-grid-line line-30m" />
          <div className="chart-grid-line line-20m" />
          <div className="chart-grid-line line-10m" />
          <div className="chart-grid-line line-0m" />

          {/* Month Columns */}
          <div className="bars-columns-wrap">
            {DEFAULT_DATA.map((item) => {
              const isSelected = item.month === activeMonth;

              return (
                <div
                  key={item.month}
                  className={`month-bar-group ${isSelected ? 'active-group' : ''}`}
                  onClick={() => {
                    setActiveMonth(item.month);
                    setShowTooltip(true);
                  }}
                >
                  {/* Floating Tooltip Card over active month */}
                  {isSelected && showTooltip && (
                    <div className="chart-floating-tooltip">
                      <div className="tooltip-inner">
                        <div className="tooltip-metric">
                          <span className="tooltip-key">CY:</span>
                          <span className="tooltip-val">${item.current.toFixed(3)}m</span>
                        </div>
                        <div className="tooltip-metric">
                          <span className="tooltip-key">PY:</span>
                          <span className="tooltip-val">${item.previous.toFixed(3)}m</span>
                        </div>
                        <div className="tooltip-metric">
                          <span className="tooltip-key">AI:</span>
                          <span className="tooltip-val">${item.predicted.toFixed(3)}m</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="tooltip-close"
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowTooltip(false);
                        }}
                      >
                        <X size={11} />
                      </button>
                    </div>
                  )}

                  {/* 3 Bars */}
                  <div className="bars-cluster">
                    {/* Current (Green) */}
                    <div
                      className="single-bar bar-current"
                      style={{ height: `${(item.current / maxVal) * 100}%` }}
                    />
                    {/* Previous (Pink/Coral) */}
                    <div
                      className="single-bar bar-previous"
                      style={{ height: `${(item.previous / maxVal) * 100}%` }}
                    />
                    {/* Predicted (Yellow) */}
                    <div
                      className="single-bar bar-predicted"
                      style={{ height: `${(item.predicted / maxVal) * 100}%` }}
                    />
                  </div>

                  {/* Month Label */}
                  <div className={`month-label-pill ${isSelected ? 'selected-pill' : ''}`}>
                    {item.month}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Legend at bottom */}
      <div className="chart-legend-row">
        <div className="legend-item">
          <span className="legend-dot dot-green" />
          <span>Current</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-pink" />
          <span>Previous</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-yellow" />
          <span>AI-Predicted</span>
        </div>
      </div>
    </div>
  );
};
