import type { FC } from 'react';
import { Plus, Calendar, MessageSquare, Ticket, Settings, Navigation } from 'lucide-react';

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
          title="Add Filter / Road Layer"
          aria-label="Add"
        >
          <Plus size={22} className="nav-svg-icon" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-tasks"
          onClick={onDocsClick}
          title="Schedule & Tasks"
          aria-label="Tasks"
        >
          <Calendar size={22} className="nav-svg-icon" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-chat"
          onClick={onChatClick}
          title="AI Chat Insights"
          aria-label="Chat"
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
          title="Saved Segments / Tickets"
          aria-label="Tickets"
        >
          <Ticket size={22} className="nav-svg-icon" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn svg-nav-btn hotspot-settings"
          onClick={onSettingsClick}
          title="Settings & PMTiles Architecture"
          aria-label="Settings"
        >
          <Settings size={22} className="nav-svg-icon" />
        </button>

        <button
          type="button"
          className="sidebar-icon-btn profile-btn hotspot-nbadge"
          onClick={onSettingsClick}
          title="Network Profile"
          aria-label="Profile"
        >
          <img src="/assets/reference/n_badge.webp" alt="Profile" className="sidebar-icon-img profile-badge-img" />
        </button>
      </div>
    </aside>
  );
};
