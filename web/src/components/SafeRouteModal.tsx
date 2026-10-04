import { useState, useMemo, type FC } from 'react';
import {
  X,
  Navigation,
  ArrowRight,
  Shield,
  Clock,
  MapPin,
  Check,
  AlertCircle
} from 'lucide-react';
import { NC_SAFE_ROUTE_CORRIDORS } from '../data/safeRoutes';
import type { RouteCorridor } from '../types/safeRoute';

interface SafeRouteModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPreviewOnMap: (corridor: RouteCorridor, option: 'fastest' | 'safest' | 'both') => void;
  initialCorridorId?: string;
}

export const SafeRouteModal: FC<SafeRouteModalProps> = ({
  isOpen,
  onClose,
  onPreviewOnMap,
  initialCorridorId = 'asheville-helene'
}) => {
  const [selectedCorridorId, setSelectedCorridorId] = useState<string>(initialCorridorId);
  const [selectedOption, setSelectedOption] = useState<'fastest' | 'safest' | 'both'>('safest');

  const corridor = useMemo(() => {
    return NC_SAFE_ROUTE_CORRIDORS.find(c => c.id === selectedCorridorId) || NC_SAFE_ROUTE_CORRIDORS[0];
  }, [selectedCorridorId]);

  if (!isOpen) return null;

  const handleHighlight = () => {
    onPreviewOnMap(corridor, selectedOption);
    onClose();
  };

  const timeDelta = corridor.safest.travelTimeMinutes - corridor.fastest.travelTimeMinutes;
  const distDelta = (corridor.safest.distanceMiles - corridor.fastest.distanceMiles).toFixed(1);

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="safe-route-title">
      <div className="modal-card clean-safe-route-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="safe-modal-header">
          <div className="safe-modal-header-meta">
            <span className="safe-modal-eyebrow">CORRIDOR SAFETY NAVIGATION</span>
            <h2 id="safe-route-title" className="safe-modal-title">
              Alternative Route Safety Analysis
            </h2>
            <p className="safe-modal-subtitle">
              Comparing default shortest-path navigation against hazard-penalized infrastructure pathfinding
            </p>
          </div>
          <button onClick={onClose} className="safe-modal-close-btn" aria-label="Close modal">
            <X size={16} />
          </button>
        </div>

        <div className="safe-modal-body">
          {/* Corridor Selection Segmented Control */}
          <div className="safe-corridor-tabs">
            {NC_SAFE_ROUTE_CORRIDORS.map((c) => {
              const isSelected = c.id === corridor.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  className={`safe-corridor-tab ${isSelected ? 'active' : ''}`}
                  onClick={() => setSelectedCorridorId(c.id)}
                >
                  <span className="tab-name">{c.name.split(' (')[0]}</span>
                  <span className={`tab-badge ${c.badgeColor}`}>{c.badge}</span>
                </button>
              );
            })}
          </div>

          {/* Origin & Destination Bar */}
          <div className="safe-route-endpoints">
            <div className="endpoint-node">
              <MapPin size={13} className="endpoint-pin origin" />
              <div className="endpoint-info">
                <span className="endpoint-type">ORIGIN</span>
                <span className="endpoint-location">{corridor.originName}</span>
              </div>
            </div>
            <div className="endpoint-divider">
              <ArrowRight size={13} />
            </div>
            <div className="endpoint-node">
              <MapPin size={13} className="endpoint-pin destination" />
              <div className="endpoint-info">
                <span className="endpoint-type">DESTINATION</span>
                <span className="endpoint-location">{corridor.destinationName}</span>
              </div>
            </div>
          </div>

          {/* Clinical Side-by-Side Comparison Matrix */}
          <div className="safe-comparison-matrix">
            {/* Option 1: Baseline Route */}
            <div
              className={`safe-route-column ${selectedOption === 'fastest' ? 'selected' : ''}`}
              onClick={() => setSelectedOption('fastest')}
            >
              <div className="column-top-strip">
                <span className="route-type-badge baseline">STANDARD NAVIGATION</span>
                <div className="route-timing-tag">
                  <Clock size={12} />
                  <span>{corridor.fastest.travelTimeMinutes} min • {corridor.fastest.distanceMiles} mi</span>
                </div>
              </div>

              <h3 className="column-route-title">{corridor.fastest.label}</h3>
              <p className="column-route-desc">{corridor.fastest.summary}</p>

              {/* Metric Breakdown Table */}
              <div className="column-metrics-grid">
                <div className="column-metric-row">
                  <span className="metric-label">Pavement Condition</span>
                  <span className="metric-value warn">{corridor.fastest.pciScore} PCI</span>
                </div>
                <div className="column-metric-row">
                  <span className="metric-label">Flood Vulnerability</span>
                  <span className="metric-value danger">{corridor.fastest.floodRiskPercent}% Inundation</span>
                </div>
                <div className="column-metric-row">
                  <span className="metric-label">Pothole Density</span>
                  <span className="metric-value danger">{corridor.fastest.severePotholesCount} Clusters</span>
                </div>
              </div>

              {/* Roadway Vulnerabilities */}
              <div className="column-hazards-box">
                <span className="hazards-title">Active Highway Hazards:</span>
                <ul className="hazards-list">
                  {corridor.fastest.criticalHazards.map((h, i) => (
                    <li key={i} className="hazard-item danger">
                      <AlertCircle size={12} className="hazard-icon" />
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <button
                type="button"
                className={`column-select-btn ${selectedOption === 'fastest' ? 'active' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedOption('fastest');
                }}
              >
                {selectedOption === 'fastest' && <Check size={14} />}
                <span>{selectedOption === 'fastest' ? 'Baseline Selected' : 'Select Baseline Route'}</span>
              </button>
            </div>

            {/* Option 2: RoadSense Safety Alternative */}
            <div
              className={`safe-route-column safety-opt ${selectedOption === 'safest' ? 'selected' : ''}`}
              onClick={() => setSelectedOption('safest')}
            >
              <div className="column-top-strip">
                <span className="route-type-badge safety">
                  <Shield size={11} /> ROADSENSE SAFETY ALTERNATIVE
                </span>
                <div className="route-timing-tag safe">
                  <Clock size={12} />
                  <span>{corridor.safest.travelTimeMinutes} min (+{timeDelta}m) • {corridor.safest.distanceMiles} mi</span>
                </div>
              </div>

              <h3 className="column-route-title">{corridor.safest.label}</h3>
              <p className="column-route-desc">{corridor.safest.summary}</p>

              {/* Metric Breakdown Table */}
              <div className="column-metrics-grid">
                <div className="column-metric-row">
                  <span className="metric-label">Pavement Condition</span>
                  <span className="metric-value good">{corridor.safest.pciScore} PCI (Satisfactory)</span>
                </div>
                <div className="column-metric-row">
                  <span className="metric-label">Flood Vulnerability</span>
                  <span className="metric-value good">{corridor.safest.floodRiskPercent}% (Bypassed)</span>
                </div>
                <div className="column-metric-row">
                  <span className="metric-label">Pothole Density</span>
                  <span className="metric-value good">0 ({corridor.hazardsAvoidedCount.potholes} Bypassed)</span>
                </div>
              </div>

              {/* Safety Highlights */}
              <div className="column-hazards-box safe">
                <span className="hazards-title safe">Hazard Avoidance Verification:</span>
                <ul className="hazards-list">
                  <li className="hazard-item safe">
                    <Check size={12} className="hazard-icon" />
                    <span>Eliminates flood inundation corridor by following elevated state ridge routes</span>
                  </li>
                  <li className="hazard-item safe">
                    <Check size={12} className="hazard-icon" />
                    <span>Bypasses {corridor.hazardsAvoidedCount.potholes} severe pothole clusters for only +{timeDelta} min (+{distDelta} mi) delta</span>
                  </li>
                </ul>
              </div>

              <button
                type="button"
                className={`column-select-btn primary ${selectedOption === 'safest' ? 'active' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedOption('safest');
                }}
              >
                {selectedOption === 'safest' && <Check size={14} />}
                <span>{selectedOption === 'safest' ? 'Safety Alternative Selected' : 'Select Safety Alternative'}</span>
              </button>
            </div>
          </div>

          {/* Technical Dijkstra Pathfinding Rationale */}
          <div className="safe-routing-note">
            <span className="note-label">Pathfinding Objective:</span>
            <span className="note-text">
              Penalty model: <code>Cost = Distance + (10.0 × FloodRisk) + (4.0 × Potholes)</code>. Dynamic routing reroutes transit away from compromised riverbanks onto reinforced ridge lines.
            </span>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="safe-modal-footer">
          <div className="footer-corridor-indicator">
            <span className="indicator-dot" />
            <span>Corridor: {corridor.name}</span>
          </div>

          <div className="footer-actions">
            <button
              type="button"
              className="safe-btn-ghost"
              onClick={onClose}
            >
              Dismiss
            </button>
            <button
              type="button"
              className="safe-btn-primary"
              onClick={handleHighlight}
            >
              <Navigation size={13} />
              <span>Preview on Map</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
