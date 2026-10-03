import type { FC } from 'react';
import {
  Home,
  FileText,
  Globe,
  Percent,
  ShoppingCart,
  Wallet,
  Users,
  HelpCircle,
  Settings
} from 'lucide-react';

interface SidebarRailProps {
  onOpenAbout: () => void;
  onOpenArchRoadmap: () => void;
  activeItem?: string;
}

export const SidebarRail: FC<SidebarRailProps> = ({
  onOpenAbout,
  onOpenArchRoadmap,
  activeItem = 'home'
}) => {
  return (
    <aside className="sidebar-rail" aria-label="Primary Navigation">
      {/* Brand Logo at top */}
      <div className="sidebar-logo-container">
        <div className="sidebar-logo-mark">
          {/* Stylized geometric G / Hexagon logo from frame 7 */}
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
            <path
              d="M12 2L3 7V17L12 22L21 17V7L12 2Z"
              stroke="#EA580C"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M12 12H17V17L12 19.5L7 17V12"
              stroke="#EA580C"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </div>

      {/* Main Nav Items Stack */}
      <nav className="sidebar-nav-group">
        <button
          type="button"
          className={`sidebar-nav-btn ${activeItem === 'home' ? 'active-rail-btn' : ''}`}
          title="Dashboard Overview"
        >
          <Home size={19} />
        </button>

        <button
          type="button"
          className="sidebar-nav-btn"
          title="Survey Reports & Logs"
        >
          <FileText size={19} />
        </button>

        <button
          type="button"
          className="sidebar-nav-btn"
          title="Geospatial Coverage"
        >
          <Globe size={19} />
        </button>

        <button
          type="button"
          className="sidebar-nav-btn"
          title="Condition Metrics"
        >
          <Percent size={19} />
        </button>

        <button
          type="button"
          className="sidebar-nav-btn"
          title="Road Asset Management"
        >
          <ShoppingCart size={19} />
        </button>

        <button
          type="button"
          className="sidebar-nav-btn"
          title="Maintenance Budgeting"
        >
          <Wallet size={19} />
        </button>

        <button
          type="button"
          className="sidebar-nav-btn"
          title="Field Teams & Survey Crews"
        >
          <Users size={19} />
        </button>
      </nav>

      {/* Bottom Nav Items */}
      <div className="sidebar-bottom-group">
        <button
          type="button"
          className="sidebar-nav-btn"
          onClick={onOpenAbout}
          title="About RoadSense AI"
        >
          <HelpCircle size={19} />
        </button>

        <button
          type="button"
          className="sidebar-nav-btn"
          onClick={onOpenArchRoadmap}
          title="PMTiles 112k+ Architecture & Settings"
        >
          <Settings size={19} />
        </button>
      </div>
    </aside>
  );
};
