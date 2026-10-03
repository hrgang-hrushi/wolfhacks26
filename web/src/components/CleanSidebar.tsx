import type { FC } from 'react';
import { Home, Plus, FileText, MessageSquare, Tag, Sliders } from 'lucide-react';

interface CleanSidebarProps {
  onHomeClick?: () => void;
  onPlusClick?: () => void;
  onDocsClick?: () => void;
  onChatClick?: () => void;
  onTagClick?: () => void;
  onSettingsClick?: () => void;
}

export const CleanSidebar: FC<CleanSidebarProps> = ({
  onHomeClick,
  onPlusClick,
  onDocsClick,
  onChatClick,
  onTagClick,
  onSettingsClick
}) => {
  return (
    <aside className="clean-sidebar" aria-label="Main Navigation">
      {/* Top Section */}
      <div className="sidebar-top-group">
        {/* Geometric 4-Petal Brand Logo */}
        <div className="sidebar-brand-mark" title="RoadSense AI">
          <svg width="34" height="34" viewBox="0 0 34 34" fill="none" xmlns="http://www.w3.org/2000/svg">
            {/* Top Circle */}
            <circle cx="17" cy="8" r="4.5" fill="#000000" />
            {/* Bottom Ellipse */}
            <ellipse cx="17" cy="26" rx="6.5" ry="4" fill="#000000" />
            {/* Left Vertical Ellipse */}
            <ellipse cx="8" cy="17" rx="4" ry="6.5" fill="#000000" />
            {/* Right Vertical Ellipse */}
            <ellipse cx="26" cy="17" rx="4" ry="6.5" fill="#000000" />
          </svg>
        </div>

        {/* Top Nav Buttons Group */}
        <div className="sidebar-nav-cluster">
          {/* Active Home Pill Button (Black Circle) */}
          <button
            type="button"
            className="sidebar-btn-home active"
            onClick={onHomeClick}
            title="Overview Dashboard"
          >
            <Home size={20} strokeWidth={2.2} />
          </button>

          {/* Plus Add Button */}
          <button
            type="button"
            className="sidebar-btn-pill"
            onClick={onPlusClick}
            title="Add Scenario / Filter"
          >
            <Plus size={18} strokeWidth={2} />
          </button>

          {/* Document / Layers Button */}
          <button
            type="button"
            className="sidebar-btn-pill"
            onClick={onDocsClick}
            title="Data & Methodology"
          >
            <FileText size={18} strokeWidth={2} />
          </button>

          {/* Chat / Assistant Button */}
          <button
            type="button"
            className="sidebar-btn-pill"
            onClick={onChatClick}
            title="AI Insights"
          >
            <MessageSquare size={18} strokeWidth={2} />
          </button>
        </div>
      </div>

      {/* Bottom Section */}
      <div className="sidebar-bottom-group">
        {/* Ticket / Bookmark Button */}
        <button
          type="button"
          className="sidebar-btn-pill"
          onClick={onTagClick}
          title="Saved Segments"
        >
          <Tag size={18} strokeWidth={2} />
        </button>

        {/* Settings / Config Button */}
        <button
          type="button"
          className="sidebar-btn-pill"
          onClick={onSettingsClick}
          title="Architecture & PMTiles"
        >
          <Sliders size={18} strokeWidth={2} />
        </button>

        {/* Bottom "N" Stylized Badge */}
        <div className="sidebar-bottom-badge" title="NCDOT Infrastructure Network">
          <img
            src="/assets/reference/n_badge.webp"
            alt="NC DOT Network"
            className="sidebar-n-img"
            onError={(e) => {
              // Fallback SVG if image not yet loaded
              (e.target as HTMLElement).style.display = 'none';
            }}
          />
        </div>
      </div>
    </aside>
  );
};
