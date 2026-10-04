import { useState, useMemo, type FC } from 'react';
import {
  X,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Navigation,
  MapPin,
  ArrowRight,
  Shield,
  Activity,
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

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="safe-route-title">
      <div className="modal-card clean-safe-route-card" onClick={(e) => e.stopPropagation()}>
        {/* Clean Modal Header matching dashboard specification */}
        <div className="modal-header">
          <div className="modal-header-title">
            <div className="clean-modal-icon-chip green">
              <ShieldCheck size={22} color="#059669" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 id="safe-route-title" className="clean-modal-heading">
                  Safe Route Navigator
                </h3>
                <span className="condition-badge green">Pillar 1: Driver</span>
              </div>
              <span className="modal-subtitle">
                Hazard-penalized pathfinding: Google Maps baseline vs. RoadSense AI alternative
              </span>
            </div>
          </div>
          <button onClick={onClose} className="modal-close-btn" aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body clean-safe-route-body">
          {/* Corridor Selection Segmented Control */}
          <div className="clean-corridor-segmented-row">
            {NC_SAFE_ROUTE_CORRIDORS.map((c) => {
              const isSelected = c.id === corridor.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  className={`clean-corridor-tab-item ${isSelected ? 'active' : ''}`}
                  onClick={() => setSelectedCorridorId(c.id)}
                >
                  <span className="tab-title">{c.name.split(' (')[0]}</span>
                  <span className={`condition-badge ${c.badgeColor}`}>{c.badge}</span>
                </button>
              );
            })}
          </div>

          {/* Origin & Destination Bar */}
          <div className="clean-endpoint-strip">
            <div className="endpoint-point">
              <MapPin size={14} className="text-emerald-600" />
              <div className="endpoint-text-wrap">
                <span className="endpoint-tag">ORIGIN</span>
                <span className="endpoint-name">{corridor.originName}</span>
              </div>
            </div>
            <ArrowRight size={14} className="text-slate-400 shrink-0 mx-2" />
            <div className="endpoint-point">
              <MapPin size={14} className="text-blue-600" />
              <div className="endpoint-text-wrap">
                <span className="endpoint-tag">DESTINATION</span>
                <span className="endpoint-name">{corridor.destinationName}</span>
              </div>
            </div>
          </div>

          {/* Side-by-Side Comparison Cards */}
          <div className="clean-comparison-grid">
            {/* 1. Fastest Route (Google Maps Baseline) */}
            <div
              className={`clean-route-card fastest ${selectedOption === 'fastest' ? 'selected' : ''}`}
              onClick={() => setSelectedOption('fastest')}
            >
              <div className="route-card-header">
                <span className="condition-badge yellow flex items-center gap-1">
                  <AlertTriangle size={11} /> Google Maps Default
                </span>
                <span className="route-timing">{corridor.fastest.tag}</span>
              </div>

              <h4 className="route-name">{corridor.fastest.label}</h4>
              <p className="route-summary">{corridor.fastest.summary}</p>

              {/* 3 Telemetry Pods matching CleanLocationCard */}
              <div className="clean-pods-row">
                <div className="clean-pod-box" title="Pavement Condition Index (0-100)">
                  <span className="pod-box-label">Pavement Health</span>
                  <span className="pod-box-value danger">{corridor.fastest.pciScore} PCI</span>
                </div>
                <div className="clean-pod-box" title="Flood Inundation Hazard">
                  <span className="pod-box-label">Flood Risk</span>
                  <span className="pod-box-value danger">{corridor.fastest.floodRiskPercent}%</span>
                </div>
                <div className="clean-pod-box" title="Severe Pothole Clusters">
                  <span className="pod-box-label">Potholes</span>
                  <span className="pod-box-value danger">{corridor.fastest.severePotholesCount} Detected</span>
                </div>
              </div>

              {/* Hazard Bullets */}
              <div className="clean-hazards-section">
                <span className="hazards-header-text">Active Roadway Vulnerabilities:</span>
                <ul className="clean-bullets-list">
                  {corridor.fastest.criticalHazards.map((h, i) => (
                    <li key={i} className="bullet-row danger">
                      <AlertCircle size={13} className="shrink-0 text-red-500 mt-0.5" />
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <button
                type="button"
                className={`clean-radio-action-btn ${selectedOption === 'fastest' ? 'checked' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedOption('fastest');
                }}
              >
                {selectedOption === 'fastest' ? <CheckCircle2 size={16} /> : <div className="clean-radio-ring" />}
                <span>Select Baseline Route</span>
              </button>
            </div>

            {/* 2. Safest Route (RoadSense AI Hazard-Penalized) */}
            <div
              className={`clean-route-card safest ${selectedOption === 'safest' ? 'selected' : ''}`}
              onClick={() => setSelectedOption('safest')}
            >
              <div className="route-card-header">
                <span className="condition-badge green flex items-center gap-1">
                  <Shield size={11} /> RoadSense AI Recommended
                </span>
                <span className="route-timing text-emerald-600">{corridor.safest.tag}</span>
              </div>

              <h4 className="route-name text-emerald-900">{corridor.safest.label}</h4>
              <p className="route-summary">{corridor.safest.summary}</p>

              {/* 3 Telemetry Pods matching CleanLocationCard */}
              <div className="clean-pods-row">
                <div className="clean-pod-box" title="Pavement Condition Index (0-100)">
                  <span className="pod-box-label">Pavement Health</span>
                  <span className="pod-box-value success">{corridor.safest.pciScore} PCI</span>
                </div>
                <div className="clean-pod-box" title="Flood Inundation Hazard">
                  <span className="pod-box-label">Flood Risk</span>
                  <span className="pod-box-value success">{corridor.safest.floodRiskPercent}%</span>
                </div>
                <div className="clean-pod-box" title="Severe Pothole Clusters">
                  <span className="pod-box-label">Potholes</span>
                  <span className="pod-box-value success">0 (None)</span>
                </div>
              </div>

              {/* Hazard Avoidance Highlights */}
              <div className="clean-avoidance-section">
                <span className="hazards-header-text text-emerald-800">Safety Improvements:</span>
                <ul className="clean-bullets-list">
                  <li className="bullet-row success">
                    <CheckCircle2 size={13} className="shrink-0 text-emerald-600 mt-0.5" />
                    <span><strong>100% Flood Hazard Avoided:</strong> Routes along high-ground ridge flyovers</span>
                  </li>
                  <li className="bullet-row success">
                    <CheckCircle2 size={13} className="shrink-0 text-emerald-600 mt-0.5" />
                    <span><strong>{corridor.hazardsAvoidedCount.potholes} Potholes Bypassed:</strong> Eliminates rim damage risk (+{corridor.safest.travelTimeMinutes - corridor.fastest.travelTimeMinutes} min delta)</span>
                  </li>
                </ul>
              </div>

              <button
                type="button"
                className={`clean-radio-action-btn success ${selectedOption === 'safest' ? 'checked' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedOption('safest');
                }}
              >
                {selectedOption === 'safest' ? <CheckCircle2 size={16} /> : <div className="clean-radio-ring" />}
                <span>Select Safest Alternative</span>
              </button>
            </div>
          </div>

          {/* Explainable AI Decision Callout */}
          <div className="arch-callout clean-ai-callout">
            <Activity size={18} className="text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <strong>RoadSense AI Pathfinding Rationale</strong>
              <p>{corridor.aiRationale}</p>
            </div>
          </div>
        </div>

        {/* Clean Modal Footer */}
        <div className="modal-footer">
          <div className="footer-status">
            <ShieldCheck size={16} className="text-emerald-600" />
            <span>Sub-millisecond WebGL path rendering &amp; telemetry</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="clean-text-btn"
              onClick={onClose}
            >
              Dismiss
            </button>
            <button
              type="button"
              className="btn-primary flex items-center gap-2"
              onClick={handleHighlight}
            >
              <Navigation size={14} />
              <span>Highlight on Map</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
