import type { FC } from 'react';
import { Plus, Calendar, MessageSquare, Ticket, Settings, Navigation, Building2, Smartphone } from 'lucide-react';

interface CleanSidebarProps {
  onHomeClick?: () => void;
  onRouteClick?: () => void;
  onPlusClick?: () => void;
  onDocsClick?: () => void;
  onChatClick?: () => void;
  onTagClick?: () => void;
  onSettingsClick?: () => void;
}

export const CleanSidebar: FC<CleanSidebarProps> = ({
  onHomeClick,
  onRouteClick,
  onPlusClick,
  onDocsClick,
  onChatClick,
  onTagClick,
  onSettingsClick
}) => {
  return (
    <aside className="fullscreen-sidebar" aria-label="Main Navigation">
      {/* Top Brand Logo */}
      <div className="sidebar-top-section">
        <button
          type="button"
          className="sidebar-icon-btn logo-btn hotspot-logo"
          onClick={onHomeClick}
          title="RoadSense AI"
          aria-label="Logo"
        >
          <img src="/assets/reference/logo.webp" alt="Logo" className="sidebar-icon-img logo-img" />
        </button>
      </div>

      {/* Middle Navigation Group */}
      <nav className="sidebar-nav-group">
        <button
          type="button"
          className="sidebar-icon-btn active-nav-btn hotspot-home"
          onClick={onHomeClick}
          title="Home Dashboard"
          aria-label="Home"
        >
          <img src="/assets/reference/icon_home.webp" alt="Home" className="sidebar-icon-img home-active-icon" />
        </button>

        <a
          href="/gov"
          className="sidebar-icon-btn svg-nav-btn hotspot-gov"
          title="Agency Dashboard (/gov)"
          aria-label="Agency Dashboard"
        >
          <Building2 size={21} className="nav-svg-icon text-amber-500" />
        </a>

        <a
          href="/m"
          className="sidebar-icon-btn svg-nav-btn hotspot-mobile"
          title="Judge Mobile Dashboard (/m)"
          aria-label="Judge Mobile Dashboard"
        >
          <Smartphone size={21} className="nav-svg-icon text-sky-500" />
        </a>

        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-route"
          onClick={onRouteClick}
          title="Safe Route Navigator"
          aria-label="Safe Route"
        >
          <Navigation size={21} className="nav-svg-icon text-emerald-400" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-plus"
          onClick={onPlusClick}
          title="Selected road details"
          aria-label="Selected road details"
        >
          <Plus size={22} className="nav-svg-icon" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-tasks"
          onClick={onDocsClick}
          title="About this project"
          aria-label="About this project"
        >
          <Calendar size={22} className="nav-svg-icon" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-chat"
          onClick={onChatClick}
          title="How the data is served"
          aria-label="How the data is served"
        >
          <MessageSquare size={22} className="nav-svg-icon" />
        </button>
      </nav>

      {/* Bottom Profile & Settings Group */}
      <div className="sidebar-bottom-section">
        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-ticket"
          onClick={onTagClick}
          title="Selected road details"
          aria-label="Selected road details"
        >
          <Ticket size={22} className="nav-svg-icon" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-settings"
          onClick={onSettingsClick}
          title="Data architecture"
          aria-label="Data architecture"
        >
          <Settings size={22} className="nav-svg-icon" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn profile-btn hotspot-nbadge"
          onClick={onSettingsClick}
          title="Data architecture"
          aria-label="Data architecture"
        >
          <img src="/assets/reference/n_badge.webp" alt="Profile" className="sidebar-icon-img profile-badge-img" />
        </button>
      </div>
    </aside>
  );
};
