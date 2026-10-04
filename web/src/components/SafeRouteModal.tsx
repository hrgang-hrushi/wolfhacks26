import { useState, useMemo, type FC } from 'react';
import {
  X,
  ShieldCheck,
  AlertTriangle,
  Compass,
  CheckCircle2,
  Navigation,
  Copy,
  Check,
  MapPin,
  TrendingUp,
  Droplets
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
  const [isCopied, setIsCopied] = useState<boolean>(false);

  const corridor = useMemo(() => {
    return NC_SAFE_ROUTE_CORRIDORS.find(c => c.id === selectedCorridorId) || NC_SAFE_ROUTE_CORRIDORS[0];
  }, [selectedCorridorId]);

  if (!isOpen) return null;

  const handleCopy = () => {
    const data = {
      corridor: corridor.name,
      origin: corridor.originName,
      destination: corridor.destinationName,
      fastest: corridor.fastest,
      safest: corridor.safest,
      hazardsAvoided: corridor.hazardsAvoidedCount,
      rationale: corridor.aiRationale
    };
    navigator.clipboard?.writeText(JSON.stringify(data, null, 2));
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const handleViewOnMap = () => {
    onPreviewOnMap(corridor, selectedOption);
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="safe-route-title">
      <div className="modal-card safe-route-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-header-title">
            <div className="safe-route-header-icon-wrap">
              <ShieldCheck className="text-emerald-400" size={24} />
            </div>
            <div>
              <h3 id="safe-route-title" className="text-lg font-bold text-white tracking-wide flex items-center gap-2">
                Safe Route Navigator
                <span className="safe-route-badge-ai">Pillar 1: Driver AI</span>
              </h3>
              <span className="modal-subtitle">
                Hazard-Penalized Pathfinding: Fastest Baseline (Google Maps) vs. Safest Alternative (RoadSense AI)
              </span>
            </div>
          </div>
          <button onClick={onClose} className="modal-close-btn" aria-label="Close modal">
            <X size={20} />
          </button>
        </div>

        <div className="modal-body safe-route-modal-body">
          {/* Corridor Selector Pills */}
          <div className="safe-route-corridor-tabs">
            {NC_SAFE_ROUTE_CORRIDORS.map((c) => {
              const isSelected = c.id === corridor.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  className={`corridor-tab-btn ${isSelected ? 'active' : ''}`}
                  onClick={() => setSelectedCorridorId(c.id)}
                >
                  <div className="corridor-tab-header">
                    <span className="corridor-tab-name">{c.name.split(' (')[0]}</span>
                    <span className={`corridor-tab-badge badge-${c.badgeColor}`}>{c.badge}</span>
                  </div>
                  <span className="corridor-tab-sub">{c.region}</span>
                </button>
              );
            })}
          </div>

          {/* Route Origin & Destination Bar */}
          <div className="safe-route-endpoint-bar">
            <div className="endpoint-item">
              <MapPin size={16} className="text-emerald-400 shrink-0" />
              <div className="endpoint-text">
                <span className="endpoint-label">ORIGIN</span>
                <span className="endpoint-val">{corridor.originName}</span>
              </div>
            </div>
            <div className="endpoint-divider">
              <Navigation size={14} className="text-slate-400 rotate-90" />
            </div>
            <div className="endpoint-item">
              <MapPin size={16} className="text-cyan-400 shrink-0" />
              <div className="endpoint-text">
                <span className="endpoint-label">DESTINATION</span>
                <span className="endpoint-val">{corridor.destinationName}</span>
              </div>
            </div>
          </div>

          {/* Side-by-Side Comparison Cards */}
          <div className="safe-route-comparison-grid">
            {/* 1. Fastest Route (Google Maps Baseline) */}
            <div className={`route-option-card fastest-card ${selectedOption === 'fastest' ? 'selected' : ''}`} onClick={() => setSelectedOption('fastest')}>
              <div className="route-card-top">
                <div className="route-pill-tag tag-warning">
                  <AlertTriangle size={13} />
                  <span>Google Maps Default</span>
                </div>
                <span className="route-timing-stat">{corridor.fastest.tag}</span>
              </div>

              <h4 className="route-card-title">{corridor.fastest.label}</h4>
              <p className="route-card-desc">{corridor.fastest.summary}</p>

              {/* Key Telemetry Badges */}
              <div className="route-metrics-row">
                <div className="route-metric-pill metric-danger">
                  <span className="metric-num">{corridor.fastest.pciScore}</span>
                  <span className="metric-lbl">PCI Health</span>
                </div>
                <div className="route-metric-pill metric-danger">
                  <span className="metric-num">{corridor.fastest.floodRiskPercent}%</span>
                  <span className="metric-lbl">Flood Hazard</span>
                </div>
                <div className="route-metric-pill metric-danger">
                  <span className="metric-num">{corridor.fastest.severePotholesCount}</span>
                  <span className="metric-lbl">Severe Potholes</span>
                </div>
              </div>

              {/* Critical Hazards List */}
              <div className="route-hazards-block">
                <span className="hazards-title">Active Segment Vulnerabilities:</span>
                <ul className="hazards-list">
                  {corridor.fastest.criticalHazards.map((h, i) => (
                    <li key={i} className="hazard-item-bullet">
                      <span className="bullet-dot red" />
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <button
                type="button"
                className={`route-select-radio-btn ${selectedOption === 'fastest' ? 'checked' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedOption('fastest');
                }}
              >
                {selectedOption === 'fastest' ? <CheckCircle2 size={16} /> : <div className="radio-circle" />}
                <span>Select Fastest Baseline</span>
              </button>
            </div>

            {/* 2. Safest Route (RoadSense AI Hazard-Penalized) */}
            <div className={`route-option-card safest-card ${selectedOption === 'safest' ? 'selected' : ''}`} onClick={() => setSelectedOption('safest')}>
              <div className="route-card-top">
                <div className="route-pill-tag tag-success">
                  <ShieldCheck size={13} />
                  <span>RoadSense AI Recommended</span>
                </div>
                <span className="route-timing-stat text-emerald-400">{corridor.safest.tag}</span>
              </div>

              <h4 className="route-card-title text-emerald-300">{corridor.safest.label}</h4>
              <p className="route-card-desc">{corridor.safest.summary}</p>

              {/* Key Telemetry Badges */}
              <div className="route-metrics-row">
                <div className="route-metric-pill metric-success">
                  <span className="metric-num">{corridor.safest.pciScore}</span>
                  <span className="metric-lbl">PCI Health</span>
                </div>
                <div className="route-metric-pill metric-success">
                  <span className="metric-num">{corridor.safest.floodRiskPercent}%</span>
                  <span className="metric-lbl">Flood Hazard</span>
                </div>
                <div className="route-metric-pill metric-success">
                  <span className="metric-num">0</span>
                  <span className="metric-lbl">Potholes</span>
                </div>
              </div>

              {/* Hazard Avoidance Callout */}
              <div className="route-avoidance-box">
                <div className="avoidance-stat-item">
                  <span className="avoidance-count text-emerald-400">-{corridor.hazardsAvoidedCount.potholes}</span>
                  <span className="avoidance-text">Severe Potholes Bypassed</span>
                </div>
                <div className="avoidance-stat-item">
                  <span className="avoidance-count text-cyan-400">-{corridor.hazardsAvoidedCount.floodZones}</span>
                  <span className="avoidance-text">Floodways Avoided</span>
                </div>
                <div className="avoidance-stat-item">
                  <span className="avoidance-count text-amber-300">+{corridor.safest.travelTimeMinutes - corridor.fastest.travelTimeMinutes} min</span>
                  <span className="avoidance-text">Time Trade-off</span>
                </div>
              </div>

              <button
                type="button"
                className={`route-select-radio-btn active-success ${selectedOption === 'safest' ? 'checked' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedOption('safest');
                }}
              >
                {selectedOption === 'safest' ? <CheckCircle2 size={16} /> : <div className="radio-circle" />}
                <span>Select Safest Alternative</span>
              </button>
            </div>
          </div>

          {/* Explainable AI Decision Box */}
          <div className="safe-route-rationale-box">
            <div className="rationale-header">
              <TrendingUp size={16} className="text-emerald-400" />
              <span className="font-semibold text-slate-200">RoadSense AI Routing Rationale</span>
            </div>
            <p className="rationale-body">{corridor.aiRationale}</p>
          </div>

          {/* Detailed Hazard Waypoints Along Corridor */}
          <div className="safe-route-waypoints-section">
            <h5 className="waypoints-section-title">
              <Droplets size={14} className="text-cyan-400" />
              Detected Geospatial Hazards Along Unmonitored Segments
            </h5>
            <div className="waypoints-grid">
              {corridor.hazards.map((h, idx) => (
                <div key={idx} className="waypoint-card">
                  <div className="waypoint-card-top">
                    <span className="waypoint-name">{h.name}</span>
                    <span className={`waypoint-severity ${h.severity}`}>{h.severity.toUpperCase()}</span>
                  </div>
                  <p className="waypoint-desc">{h.description}</p>
                  <span className="waypoint-coords">Coords: [{h.coordinate[0].toFixed(4)}, {h.coordinate[1].toFixed(4)}]</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Modal Footer Controls */}
        <div className="modal-footer safe-route-modal-footer">
          <div className="footer-left-actions">
            <button
              type="button"
              className="safe-route-btn-secondary"
              onClick={handleCopy}
              title="Copy route comparison JSON telemetry"
            >
              {isCopied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
              <span>{isCopied ? 'Copied JSON' : 'Export Route Data'}</span>
            </button>
            <button
              type="button"
              className={`safe-route-btn-secondary ${selectedOption === 'both' ? 'active-both' : ''}`}
              onClick={() => setSelectedOption(selectedOption === 'both' ? 'safest' : 'both')}
              title="Show both routes on map simultaneously for comparison"
            >
              <Compass size={14} />
              <span>{selectedOption === 'both' ? 'Comparing Both Routes' : 'Compare Both On Map'}</span>
            </button>
          </div>

          <div className="footer-right-actions">
            <button type="button" className="safe-route-btn-cancel" onClick={onClose}>
              Dismiss
            </button>
            <button
              type="button"
              className="safe-route-btn-primary"
              onClick={handleViewOnMap}
            >
              <Navigation size={16} />
              <span>Highlight &amp; Preview On Map</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
