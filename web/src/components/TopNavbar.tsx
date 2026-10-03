import { useState } from 'react';
import type { FC } from 'react';
import { Search, Moon, Sun, Bell } from 'lucide-react';

interface TopNavbarProps {
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  onSearchClick?: () => void;
  onThemeToggle?: () => void;
  isDarkTheme?: boolean;
}

export const TopNavbar: FC<TopNavbarProps> = ({
  activeTab = 'Overview',
  onTabChange,
  onSearchClick,
  onThemeToggle,
  isDarkTheme = false
}) => {
  const [currentTab, setCurrentTab] = useState(activeTab);

  const handleTabClick = (tab: string) => {
    setCurrentTab(tab);
    onTabChange?.(tab);
  };

  return (
    <header className="top-navbar-container">
      {/* Left Brand Platform Title */}
      <div className="navbar-left-brand">
        <h2 className="navbar-platform-title">GeoSales platform</h2>
        <span className="navbar-app-tag">RoadSense AI</span>
      </div>

      {/* Center Tabs */}
      <nav className="navbar-center-tabs">
        {['Overview', 'Monitoring', 'Predictive AI'].map((tab) => (
          <button
            key={tab}
            type="button"
            className={`navbar-tab-btn ${currentTab === tab ? 'active-tab' : ''}`}
            onClick={() => handleTabClick(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>

      {/* Right Controls & Profile */}
      <div className="navbar-right-profile">
        <button
          type="button"
          className="navbar-icon-btn"
          onClick={onSearchClick}
          title="Search dashboard"
        >
          <Search size={18} />
        </button>

        <button
          type="button"
          className="navbar-icon-btn"
          onClick={onThemeToggle}
          title={isDarkTheme ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {isDarkTheme ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        <button
          type="button"
          className="navbar-icon-btn bell-btn"
          title="Notifications"
        >
          <Bell size={18} />
          <span className="notification-dot" />
        </button>

        <div className="navbar-vertical-divider" />

        {/* User Profile */}
        <div className="navbar-user-card">
          <img
            src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80"
            alt="Alex Fox"
            className="navbar-avatar-img"
          />
          <div className="navbar-user-meta">
            <span className="navbar-user-name">Alex Fox</span>
            <span className="navbar-user-role">CEO, admin</span>
          </div>
        </div>
      </div>
    </header>
  );
};
