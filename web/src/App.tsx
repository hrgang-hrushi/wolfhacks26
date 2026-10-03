import { useState, useMemo, useRef, useCallback } from 'react';
import { MOCK_ROAD_SEGMENTS } from './data/mockRoads';
import type { RoadSegment, ViewFilter } from './types/roadSegment';
import { CleanSidebar } from './components/CleanSidebar';
import { CleanMapCard, type CleanMapCardHandle } from './components/CleanMapCard';
import { CleanLocationCard } from './components/CleanLocationCard';
import { CleanPhotoCard } from './components/CleanPhotoCard';
import { CleanTenantsCard } from './components/CleanTenantsCard';
import { PMTilesArchitectureModal } from './components/PMTilesArchitectureModal';
import { AboutProjectModal } from './components/AboutProjectModal';
import { SegmentDetailModal } from './components/SegmentDetailModal';
import './App.css';

export function App() {
  const mapCardRef = useRef<CleanMapCardHandle>(null);

  // Filter mode: 'ncdot' (state roads only) vs 'all' (every street)
  const [viewFilter, setViewFilter] = useState<ViewFilter>('all');

  // Currently focused city: Raleigh (default) or Asheville
  const [activeCity, setActiveCity] = useState<'Asheville' | 'Raleigh' | null>('Raleigh');

  // Currently selected segment for deep inspection (defaults to first segment)
  const [selectedSegment, setSelectedSegment] = useState<RoadSegment | null>(
    MOCK_ROAD_SEGMENTS[0] || null
  );

  // Modals visibility
  const [isArchModalOpen, setIsArchModalOpen] = useState(false);
  const [isAboutModalOpen, setIsAboutModalOpen] = useState(false);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);

  // Filter road segments based on viewFilter toggle
  const filteredSegments = useMemo(() => {
    if (viewFilter === 'ncdot') {
      return MOCK_ROAD_SEGMENTS.filter((s) => s.source === 'ncdot');
    }
    return MOCK_ROAD_SEGMENTS;
  }, [viewFilter]);

  // Handle city zoom
  const handleZoomCity = useCallback((city: 'Asheville' | 'Raleigh') => {
    setActiveCity(city);
    mapCardRef.current?.flyToCity(city);
  }, []);

  // Handle segment selection
  const handleSelectSegment = useCallback((segment: RoadSegment) => {
    setSelectedSegment(segment);
    setActiveCity(segment.city);
    mapCardRef.current?.flyToSegment(segment);
  }, []);

  // Handle fly to segment
  const handleFlyToSegment = useCallback((segment: RoadSegment) => {
    mapCardRef.current?.flyToSegment(segment);
  }, []);

  return (
    <div className="canvas-frame-container">
      {/* Main Rounded App Window Card (matching reference) */}
      <div className="app-window-card">
        {/* Left Vertical Navigation Rail */}
        <CleanSidebar
          onHomeClick={() => handleZoomCity('Raleigh')}
          onPlusClick={() => setIsDetailModalOpen(true)}
          onDocsClick={() => setIsAboutModalOpen(true)}
          onChatClick={() => setIsArchModalOpen(true)}
          onTagClick={() => setIsDetailModalOpen(true)}
          onSettingsClick={() => setIsArchModalOpen(true)}
        />

        {/* Main Content Workspace */}
        <main className="app-main-pane">
          {/* Top Row: The Clean Map Card with DeckGL + Search/Filter Pills + Black Pill */}
          <CleanMapCard
            ref={mapCardRef}
            segments={filteredSegments}
            selectedSegment={selectedSegment}
            onSelectSegment={handleSelectSegment}
            viewFilter={viewFilter}
            onToggleFilter={setViewFilter}
            activeCity={activeCity}
            onZoomCity={handleZoomCity}
            onOpenHelp={() => setIsArchModalOpen(true)}
          />

          {/* Bottom Row: 3 Distinct Cards (Location, Photo, Tenants) */}
          <div className="bottom-cards-grid">
            {/* Card 1: Location & Sub-Metrics */}
            <CleanLocationCard selectedSegment={selectedSegment} />

            {/* Card 2: Modern Architecture / Aerial Satellite Chip Showcase */}
            <CleanPhotoCard selectedSegment={selectedSegment} />

            {/* Card 3: Tenants / Pavement Rating Arc Gauge */}
            <CleanTenantsCard selectedSegment={selectedSegment} />
          </div>
        </main>

        {/* Deep Road Segment Drilldown Modal */}
        {isDetailModalOpen && selectedSegment && (
          <SegmentDetailModal
            segment={selectedSegment}
            onClose={() => setIsDetailModalOpen(false)}
            onFlyTo={handleFlyToSegment}
          />
        )}
      </div>

      {/* PMTiles Architecture Blueprint Modal */}
      <PMTilesArchitectureModal
        isOpen={isArchModalOpen}
        onClose={() => setIsArchModalOpen(false)}
      />

      {/* About Project Mission Modal */}
      <AboutProjectModal
        isOpen={isAboutModalOpen}
        onClose={() => setIsAboutModalOpen(false)}
      />
    </div>
  );
}

export default App;
