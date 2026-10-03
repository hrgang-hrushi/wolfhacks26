import type { FC } from 'react';

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
    <aside className="pixel-sidebar-container" aria-label="Main Navigation">
      {/* 100% Authentic Full Sidebar Strip Image */}
      <img
        src="/assets/reference/sidebar_bg.webp"
        alt="Sidebar Navigation"
        className="sidebar-backdrop-img"
      />

      {/* Interactive Clickable Hotspots overlayed at exact pixel coordinates */}
      <button
        type="button"
        className="sidebar-hotspot hotspot-logo"
        onClick={onHomeClick}
        title="RoadSense AI"
        aria-label="Logo"
      />

      <button
        type="button"
        className="sidebar-hotspot hotspot-home"
        onClick={onHomeClick}
        title="Home Dashboard"
        aria-label="Home"
      />

      <button
        type="button"
        className="sidebar-hotspot hotspot-plus"
        onClick={onPlusClick}
        title="Add Filter / Layer"
        aria-label="Add"
      />

      <button
        type="button"
        className="sidebar-hotspot hotspot-tasks"
        onClick={onDocsClick}
        title="Schedule / Tasks"
        aria-label="Tasks"
      />

      <button
        type="button"
        className="sidebar-hotspot hotspot-chat"
        onClick={onChatClick}
        title="AI Chat Insights"
        aria-label="Chat"
      />

      <button
        type="button"
        className="sidebar-hotspot hotspot-ticket"
        onClick={onTagClick}
        title="Saved Segments / Tickets"
        aria-label="Tickets"
      />

      <button
        type="button"
        className="sidebar-hotspot hotspot-settings"
        onClick={onSettingsClick}
        title="Settings & PMTiles Architecture"
        aria-label="Settings"
      />

      <button
        type="button"
        className="sidebar-hotspot hotspot-nbadge"
        onClick={onSettingsClick}
        title="Network / Profile"
        aria-label="Network Profile"
      />
    </aside>
  );
};
