import { useState, useImperativeHandle, forwardRef } from 'react';
import type { RoadSegment, ViewFilter } from '../types/roadSegment';

export interface CleanMapCardHandle {
  flyToCity: (city: 'Asheville' | 'Raleigh') => void;
  flyToSegment: (segment: RoadSegment) => void;
}

interface CleanMapCardProps {
  segments: RoadSegment[];
  selectedSegment: RoadSegment | null;
  onSelectSegment: (segment: RoadSegment) => void;
  viewFilter: ViewFilter;
  onToggleFilter: (filter: ViewFilter) => void;
  activeCity: 'Asheville' | 'Raleigh' | null;
  onZoomCity: (city: 'Asheville' | 'Raleigh') => void;
  onOpenHelp: () => void;
}

export const CleanMapCard = forwardRef<CleanMapCardHandle, CleanMapCardProps>(({
  segments,
  onSelectSegment,
  viewFilter: _viewFilter,
  onToggleFilter,
  activeCity: _activeCity,
  onZoomCity,
  onOpenHelp
}, ref) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isInsuranceOpen, setIsInsuranceOpen] = useState(false);
  const [isCityOpen, setIsCityOpen] = useState(false);
  const [isStateOpen, setIsStateOpen] = useState(false);
  const [isDistrictOpen, setIsDistrictOpen] = useState(false);

  useImperativeHandle(ref, () => ({
    flyToCity: (_city: 'Asheville' | 'Raleigh') => {},
    flyToSegment: (_segment: RoadSegment) => {}
  }));

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    const match = segments.find(
      s => s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
           s.seg_id.toLowerCase().includes(searchQuery.toLowerCase())
    );
    if (match) {
      onSelectSegment(match);
    }
  };

  return (
    <div className="pixel-map-card">
      {/* 100% Authentic High-Resolution Map Background */}
      <img
        src="/assets/reference/map_bg.webp"
        alt="Costa Mesa / Orange County Map"
        className="map-backdrop-img"
      />

      {/* Top Floating Controls Bar */}
      <div className="pixel-map-top-bar">
        {/* Interactive Search Input Form */}
        <form onSubmit={handleSearchSubmit} className="pixel-search-form">
          <input
            type="text"
            className="pixel-search-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search"
          />
        </form>

        {/* Filter Hotspots */}
        <div className="pixel-filters-cluster">
          {/* Insurance Type Dropdown */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className="pixel-filter-btn"
              onClick={() => setIsInsuranceOpen(!isInsuranceOpen)}
              title="Insurance Type"
              aria-label="Insurance Type"
            />
            {isInsuranceOpen && (
              <div className="pixel-dropdown-menu">
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    onToggleFilter('all');
                    setIsInsuranceOpen(false);
                  }}
                >
                  All Street Types (Prediction)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    onToggleFilter('ncdot');
                    setIsInsuranceOpen(false);
                  }}
                >
                  State Surveys (NCDOT Only)
                </button>
              </div>
            )}
          </div>

          {/* State Dropdown */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className="pixel-filter-btn"
              onClick={() => setIsStateOpen(!isStateOpen)}
              title="State"
              aria-label="State"
            />
            {isStateOpen && (
              <div className="pixel-dropdown-menu">
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => setIsStateOpen(false)}
                >
                  California
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => setIsStateOpen(false)}
                >
                  North Carolina
                </button>
              </div>
            )}
          </div>

          {/* City Dropdown */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className="pixel-filter-btn"
              onClick={() => setIsCityOpen(!isCityOpen)}
              title="City"
              aria-label="City"
            />
            {isCityOpen && (
              <div className="pixel-dropdown-menu">
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    onZoomCity('Raleigh');
                    setIsCityOpen(false);
                  }}
                >
                  Costa Mesa / Raleigh
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    onZoomCity('Asheville');
                    setIsCityOpen(false);
                  }}
                >
                  Huntington Beach / Asheville
                </button>
              </div>
            )}
          </div>

          {/* District Dropdown */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className="pixel-filter-btn"
              onClick={() => setIsDistrictOpen(!isDistrictOpen)}
              title="District"
              aria-label="District"
            />
            {isDistrictOpen && (
              <div className="pixel-dropdown-menu">
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => setIsDistrictOpen(false)}
                >
                  District 1
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => setIsDistrictOpen(false)}
                >
                  District 2
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Floating 3 Black Cards Hotspot Group */}
      <div className="pixel-black-cards-group">
        <button
          type="button"
          className="pixel-black-card-hotspot"
          onClick={() => {}}
          title="15 House Number"
        />
        <button
          type="button"
          className="pixel-black-card-hotspot hotspot-wide"
          onClick={() => {}}
          title="$4,954.380 Estimate House Price"
        />
        <button
          type="button"
          className="pixel-black-card-hotspot"
          onClick={() => {}}
          title="5Y Average Age"
        />
      </div>

      {/* Amber Glowing Pin Hotspots on Map */}
      <button
        type="button"
        className="pin-hotspot pin-costa-mesa"
        onClick={() => onSelectSegment(segments[0])}
        title="Costa Mesa (Active Road Segment)"
      />
      <button
        type="button"
        className="pin-hotspot pin-oak-view"
        onClick={() => onSelectSegment(segments[1] || segments[0])}
        title="Oak View (Active Road Segment)"
      />
      <button
        type="button"
        className="pin-hotspot pin-quail-hill"
        onClick={() => onSelectSegment(segments[2] || segments[0])}
        title="Quail Hill (Active Road Segment)"
      />
      <button
        type="button"
        className="pin-hotspot pin-northwood"
        onClick={() => onSelectSegment(segments[3] || segments[0])}
        title="Northwood (Active Road Segment)"
      />

      {/* Bottom Right Floating Question Button */}
      <button
        type="button"
        className="pixel-help-btn-hotspot"
        onClick={onOpenHelp}
        title="Help & Info"
        aria-label="Help & Info"
      />
    </div>
  );
});

CleanMapCard.displayName = 'CleanMapCard';
