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

  const [viewFilter, setViewFilter] = useState<ViewFilter>('all');
  const [activeCity, setActiveCity] = useState<'Asheville' | 'Raleigh' | null>('Raleigh');
  const [selectedSegment, setSelectedSegment] = useState<RoadSegment | null>(
    MOCK_ROAD_SEGMENTS[0] || null
  );

  const [isArchModalOpen, setIsArchModalOpen] = useState(false);
  const [isAboutModalOpen, setIsAboutModalOpen] = useState(false);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);

  const filteredSegments = useMemo(() => {
    if (viewFilter === 'ncdot') {
      return MOCK_ROAD_SEGMENTS.filter((s) => s.source === 'ncdot');
    }
    return MOCK_ROAD_SEGMENTS;
  }, [viewFilter]);

  const handleZoomCity = useCallback((city: 'Asheville' | 'Raleigh') => {
    setActiveCity(city);
    mapCardRef.current?.flyToCity(city);
  }, []);

  const handleSelectSegment = useCallback((segment: RoadSegment) => {
    setSelectedSegment(segment);
    setActiveCity(segment.city);
    mapCardRef.current?.flyToSegment(segment);
  }, []);

  const handleFlyToSegment = useCallback((segment: RoadSegment) => {
    mapCardRef.current?.flyToSegment(segment);
  }, []);

  return (
    <div className="canvas-frame-container">
      {/* 110% Pixel-Accurate Master Reference Backdrop */}
      <img
        src="/assets/reference/dashboard_master_reference.webp"
        alt="Dashboard Master Reference"
        className="master-backdrop-image"
      />

      {/* 110% Pixel-Accurate Main Window Card */}
      <div className="pixel-app-card">
        {/* Left Vertical Navigation Rail (183px width) */}
        <CleanSidebar
          onHomeClick={() => handleZoomCity('Raleigh')}
          onPlusClick={() => setIsDetailModalOpen(true)}
          onDocsClick={() => setIsAboutModalOpen(true)}
          onChatClick={() => setIsArchModalOpen(true)}
          onTagClick={() => setIsDetailModalOpen(true)}
          onSettingsClick={() => setIsArchModalOpen(true)}
        />

        {/* Main Workspace (1597px width) */}
        <main className="pixel-main-pane">
          {/* Top Map Card (1597px x 752px) */}
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

          {/* Bottom Row (1597px x 460px) */}
          <div className="pixel-bottom-row">
            {/* Card 1: Location (717px x 460px) */}
            <CleanLocationCard selectedSegment={selectedSegment} />

            {/* Card 2: Modern Architecture (433px x 460px) */}
            <CleanPhotoCard selectedSegment={selectedSegment} />

            {/* Card 3: Tenants & Donut Gauge (420px x 460px) */}
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

      {/* Architecture & PMTiles Modal */}
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
