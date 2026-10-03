import type { FC } from 'react';
import { Layers, Database, Mountain, Landmark, ListFilter, HelpCircle } from 'lucide-react';
import type { ViewFilter } from '../types/roadSegment';

interface HeaderProps {
  viewFilter: ViewFilter;
  onToggleFilter: (filter: ViewFilter) => void;
  onZoomCity: (city: 'Asheville' | 'Raleigh') => void;
  activeCity: 'Asheville' | 'Raleigh' | null;
  totalSegmentsCount: number;
  visibleSegmentsCount: number;
  onOpenArchitectureModal: () => void;
  isDrawerOpen: boolean;
  onToggleDrawer: () => void;
  onOpenAboutModal: () => void;
}

export const Header: FC<HeaderProps> = ({
  viewFilter,
  onToggleFilter,
  onZoomCity,
  activeCity,
  totalSegmentsCount,
  visibleSegmentsCount,
  onOpenArchitectureModal,
  isDrawerOpen,
  onToggleDrawer,
  onOpenAboutModal
}) => {
  return (
    <header className="app-header">
      {/* Brand Identity */}
      <div className="header-brand">
        <div className="brand-logo-container">
          <Layers className="brand-icon" size={20} />
          <div className="status-ping" />
        </div>
        <div className="brand-text">
          <div className="brand-title-row">
            <h1 className="brand-name">RoadSense AI</h1>
            <span className="hackathon-tag">WolfHacks '26</span>
          </div>
          <span className="brand-subtitle">North Carolina Infrastructure Predictor</span>
        </div>
      </div>

      {/* Main Controls: Mode Toggle & City Zoom */}
      <div className="header-controls">
        {/* Toggle: "What the state surveys" vs "What we predict" */}
        <div className="toggle-group" role="radiogroup" aria-label="Road Survey Coverage Mode">
          <button
            type="button"
            className={`toggle-option ${viewFilter === 'ncdot' ? 'active' : ''}`}
            onClick={() => onToggleFilter('ncdot')}
            title="Show state surveyed roads only (NCDOT highways & primary arterials)"
          >
            <span className="toggle-dot dot-state" />
            <span className="toggle-label">What the State Surveys</span>
            <span className="toggle-badge">State Roads</span>
          </button>
          
          <button
            type="button"
            className={`toggle-option ${viewFilter === 'all' ? 'active' : ''}`}
            onClick={() => onToggleFilter('all')}
            title="Show AI predictions across every street (State + City Municipal)"
          >
            <span className="toggle-dot dot-predict" />
            <span className="toggle-label">What We Predict</span>
            <span className="toggle-badge badge-all">Every Street</span>
          </button>
        </div>

        {/* Two Zoom Buttons: Asheville and Raleigh */}
        <div className="city-buttons-group">
          <button
            type="button"
            className={`city-button ${activeCity === 'Asheville' ? 'active-city' : ''}`}
            onClick={() => onZoomCity('Asheville')}
            title="Fly to Asheville, NC (Mountain Region)"
          >
            <Mountain size={14} className="city-btn-icon" />
            <span>Asheville</span>
          </button>

          <button
            type="button"
            className={`city-button ${activeCity === 'Raleigh' ? 'active-city' : ''}`}
            onClick={() => onZoomCity('Raleigh')}
            title="Fly to Raleigh, NC (Piedmont / Capital)"
          >
            <Landmark size={14} className="city-btn-icon" />
            <span>Raleigh</span>
          </button>
        </div>
      </div>

      {/* Secondary Tools: Road Directory, About & PMTiles Roadmap */}
      <div className="header-right">
        <button
          type="button"
          onClick={onToggleDrawer}
          className={`drawer-toggle-btn ${isDrawerOpen ? 'active' : ''}`}
          title="Browse and search all 100 road segments"
        >
          <ListFilter size={14} />
          <span>Roads List ({visibleSegmentsCount} / {totalSegmentsCount})</span>
        </button>

        <button
          onClick={onOpenAboutModal}
          className="about-btn"
          title="What is this project?"
        >
          <HelpCircle size={14} />
          <span>About Project</span>
        </button>

        <button
          onClick={onOpenArchitectureModal}
          className="arch-button"
          title="View 112k+ Segment PMTiles Scaling Architecture"
        >
          <Database size={14} />
          <span>PMTiles Roadmap</span>
        </button>
      </div>
    </header>
  );
};
