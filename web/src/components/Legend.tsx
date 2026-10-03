import React from 'react';
import { Info } from 'lucide-react';

export const Legend: React.FC = () => {
  return (
    <div className="map-legend" aria-label="Road Condition Score Legend">
      <div className="legend-header">
        <span className="legend-title">PAVEMENT CONDITION SCORE</span>
        <span className="legend-scale-tag">0.0 – 1.0</span>
      </div>

      {/* Gradient bar */}
      <div className="legend-bar-container">
        <div className="legend-gradient-bar" />
      </div>

      {/* Range markers */}
      <div className="legend-labels-row">
        <div className="legend-stop">
          <span className="stop-dot stop-critical" />
          <span className="stop-text">0.0 Critical</span>
        </div>
        <div className="legend-stop">
          <span className="stop-dot stop-poor" />
          <span className="stop-text">0.4 Poor</span>
        </div>
        <div className="legend-stop">
          <span className="stop-dot stop-fair" />
          <span className="stop-text">0.6 Fair</span>
        </div>
        <div className="legend-stop">
          <span className="stop-dot stop-good" />
          <span className="stop-text">0.8 Good</span>
        </div>
        <div className="legend-stop">
          <span className="stop-dot stop-optimal" />
          <span className="stop-text">1.0 Optimal</span>
        </div>
      </div>
      
      <div className="legend-footer">
        <Info size={11} />
        <span>Click any road segment line to inspect predictions</span>
      </div>
    </div>
  );
};
