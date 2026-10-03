import { useState, useImperativeHandle, forwardRef, useRef } from 'react';
import { Search, ChevronDown, HelpCircle, Navigation } from 'lucide-react';
import type { RoadSegment, ViewFilter } from '../types/roadSegment';
import { MapView, type MapViewHandle } from './MapView';

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
  selectedSegment,
  onSelectSegment,
  viewFilter,
  onToggleFilter,
  activeCity,
  onZoomCity,
  onOpenHelp
}, ref) => {
  const mapViewRef = useRef<MapViewHandle>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isFilterDropdownOpen, setIsFilterDropdownOpen] = useState(false);
  const [isCityDropdownOpen, setIsCityDropdownOpen] = useState(false);
  const [showMockLabels, setShowMockLabels] = useState(true);

  useImperativeHandle(ref, () => ({
    flyToCity: (city: 'Asheville' | 'Raleigh') => {
      mapViewRef.current?.flyToCity(city);
    },
    flyToSegment: (segment: RoadSegment) => {
      mapViewRef.current?.flyToSegment(segment);
    }
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
      mapViewRef.current?.flyToSegment(match);
    }
  };

  return (
    <div className="clean-map-card">
      {/* Top Floating Control Bar matching reference border-radius 12px */}
      <div className="map-top-bar">
        {/* Search Input Bar */}
        <form onSubmit={handleSearchSubmit} className="map-search-bar">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            className="search-input"
            placeholder="Search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </form>

        {/* Filter Buttons Group */}
        <div className="map-filters-row">
          {/* Pill 1: Survey vs Prediction Toggle (Insurance Type) */}
          <div className="filter-item-container">
            <button
              type="button"
              className={`filter-btn ${viewFilter === 'ncdot' ? 'filter-active' : ''}`}
              onClick={() => setIsFilterDropdownOpen(!isFilterDropdownOpen)}
            >
              <span>{viewFilter === 'ncdot' ? 'State Surveys' : 'Insurance Type'}</span>
              <ChevronDown size={14} className="chevron-icon" />
            </button>

            {isFilterDropdownOpen && (
              <div className="filter-dropdown-menu">
                <button
                  type="button"
                  className={`filter-dropdown-item ${viewFilter === 'all' ? 'item-selected' : ''}`}
                  onClick={() => {
                    onToggleFilter('all');
                    setIsFilterDropdownOpen(false);
                  }}
                >
                  <span className="item-title">What We Predict (All 100 Streets)</span>
                  <span className="item-subtitle">Combines State NCDOT + City Municipal streets</span>
                </button>
                <button
                  type="button"
                  className={`filter-dropdown-item ${viewFilter === 'ncdot' ? 'item-selected' : ''}`}
                  onClick={() => {
                    onToggleFilter('ncdot');
                    setIsFilterDropdownOpen(false);
                  }}
                >
                  <span className="item-title">What the State Surveys (NCDOT Only)</span>
                  <span className="item-subtitle">Official state-maintained road corridors</span>
                </button>
              </div>
            )}
          </div>

          {/* Pill 2: State Filter */}
          <button type="button" className="filter-btn">
            <span>State</span>
            <ChevronDown size={14} className="chevron-icon" />
          </button>

          {/* Pill 3: City Switcher */}
          <div className="filter-item-container">
            <button
              type="button"
              className="filter-btn"
              onClick={() => setIsCityDropdownOpen(!isCityDropdownOpen)}
            >
              <span>{activeCity || 'City'}</span>
              <ChevronDown size={14} className="chevron-icon" />
            </button>

            {isCityDropdownOpen && (
              <div className="filter-dropdown-menu">
                <button
                  type="button"
                  className={`filter-dropdown-item ${activeCity === 'Raleigh' ? 'item-selected' : ''}`}
                  onClick={() => {
                    onZoomCity('Raleigh');
                    setIsCityDropdownOpen(false);
                  }}
                >
                  <span className="item-title">Raleigh</span>
                  <span className="item-subtitle">Capital Blvd, Hillsborough St, Western Blvd</span>
                </button>
                <button
                  type="button"
                  className={`filter-dropdown-item ${activeCity === 'Asheville' ? 'item-selected' : ''}`}
                  onClick={() => {
                    onZoomCity('Asheville');
                    setIsCityDropdownOpen(false);
                  }}
                >
                  <span className="item-title">Asheville</span>
                  <span className="item-subtitle">Biltmore Ave, Blue Ridge, Patton Ave</span>
                </button>
              </div>
            )}
          </div>

          {/* Pill 4: District */}
          <button type="button" className="filter-btn">
            <span>District</span>
            <ChevronDown size={14} className="chevron-icon" />
          </button>

          {/* Quick Zoom Buttons: Asheville and Raleigh */}
          <div className="city-shortcuts-group">
            <button
              type="button"
              className={`city-quick-btn ${activeCity === 'Asheville' ? 'city-btn-active' : ''}`}
              onClick={() => onZoomCity('Asheville')}
              title="Zoom to Asheville"
            >
              <Navigation size={12} className="inline mr-1" />
              Asheville
            </button>
            <button
              type="button"
              className={`city-quick-btn ${activeCity === 'Raleigh' ? 'city-btn-active' : ''}`}
              onClick={() => onZoomCity('Raleigh')}
              title="Zoom to Raleigh"
            >
              <Navigation size={12} className="inline mr-1" />
              Raleigh
            </button>
          </div>
        </div>
      </div>

      {/* Floating 3-Card Black Cluster matching reference exactly */}
      <div
        className="floating-black-cluster"
        onClick={() => setShowMockLabels(!showMockLabels)}
        title="Click to toggle between Reference mockup values and Segment telemetry"
      >
        {/* Card 1: 15 House Number */}
        <div className="black-stat-card">
          <div className="black-stat-val">
            {showMockLabels ? '15' : (selectedSegment ? selectedSegment.seg_id.slice(-2) : '100')}
          </div>
          <div className="black-stat-lbl">
            {showMockLabels ? 'House Number' : 'Road Segments'}
          </div>
        </div>

        {/* Card 2: $4,954.380 Estimate House Price */}
        <div className="black-stat-card black-stat-card-wide">
          <div className="black-stat-val">
            {showMockLabels ? '$4,954.380' : '$4.95M'}
          </div>
          <div className="black-stat-lbl">
            {showMockLabels ? 'Estimate House Price' : 'Est. Repair Budget'}
          </div>
        </div>

        {/* Card 3: 5Y Average Age */}
        <div className="black-stat-card">
          <div className="black-stat-val">
            {showMockLabels ? '5Y' : (selectedSegment ? `${selectedSegment.pv_age}Y` : '5.3Y')}
          </div>
          <div className="black-stat-lbl">
            {showMockLabels ? 'Average Age' : 'Pavement Age'}
          </div>
        </div>
      </div>

      {/* Interactive Map Canvas (MapLibre + DeckGL / Vector Fallback) */}
      <div className="map-canvas-wrapper">
        <MapView
          ref={mapViewRef}
          segments={segments}
          selectedSegment={selectedSegment}
          onSelectSegment={onSelectSegment}
        />
      </div>

      {/* Floating Black Circle Help Button at bottom right */}
      <button
        type="button"
        className="floating-help-btn"
        onClick={onOpenHelp}
        title="Architecture & PMTiles Documentation"
        aria-label="Help & Documentation"
      >
        <HelpCircle size={22} color="#ffffff" strokeWidth={2.2} />
      </button>
    </div>
  );
});

CleanMapCard.displayName = 'CleanMapCard';
