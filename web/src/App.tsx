import { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import { REAL_NC_ROAD_SEGMENTS } from './data/realRoads';
import type { RoadSegment, ViewFilter } from './types/roadSegment';
import { CleanSidebar } from './components/CleanSidebar';
import { CleanMapCard, type CleanMapCardHandle } from './components/CleanMapCard';
import { CleanLocationCard } from './components/CleanLocationCard';
import { GovAnalyticsCard } from './components/GovAnalyticsCard';
import { CleanTenantsCard } from './components/CleanTenantsCard';
import { PMTilesArchitectureModal } from './components/PMTilesArchitectureModal';
import { AboutProjectModal } from './components/AboutProjectModal';
import { SegmentDetailModal } from './components/SegmentDetailModal';
import './App.css';

export function App() {
  const mapCardRef = useRef<CleanMapCardHandle>(null);

  const [segments, setSegments] = useState<RoadSegment[]>(REAL_NC_ROAD_SEGMENTS);
  const [viewFilter, setViewFilter] = useState<ViewFilter>('all');
  const [activeCity, setActiveCity] = useState<'Asheville' | 'Raleigh' | null>('Raleigh');
  const [selectedSegment, setSelectedSegment] = useState<RoadSegment | null>(
    REAL_NC_ROAD_SEGMENTS.find(s => s.city === 'Raleigh') || REAL_NC_ROAD_SEGMENTS[0] || null
  );

  const [isArchModalOpen, setIsArchModalOpen] = useState(false);
  const [isAboutModalOpen, setIsAboutModalOpen] = useState(false);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);

  // Background sync with live API (relative /api in Vercel or dev proxy, or VITE_API_BASE_URL)
  useEffect(() => {
    let isMounted = true;
    const apiBase = import.meta.env.VITE_API_BASE_URL ?? '';
    fetch(`${apiBase}/api/segments?limit=2500`)
      .then(res => res.json())
      .then(data => {
        if (isMounted && data && Array.isArray(data.segments) && data.segments.length > 0) {
          console.log(`Live API connected! Loaded ${data.segments.length} real-time statewide NC segments.`);
          setSegments(data.segments);
          const firstInCity = data.segments.find((s: RoadSegment) => s.city === 'Raleigh') || data.segments[0];
          if (firstInCity) {
            setSelectedSegment(firstInCity);
          }
        }
      })
      .catch(() => {
        console.log('Using pre-bundled real NC segments dataset (2,171 statewide segments).');
      });
    return () => { isMounted = false; };
  }, []);

  const filteredSegments = useMemo(() => {
    if (viewFilter === 'ncdot') {
      return segments.filter((s) => s.source === 'ncdot');
    }
    return segments;
  }, [segments, viewFilter]);

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
    <div className="fullscreen-dashboard-root">
      {/* Left Vertical Navigation Rail */}
      <CleanSidebar
        onHomeClick={() => handleZoomCity('Raleigh')}
        onPlusClick={() => setIsDetailModalOpen(true)}
        onDocsClick={() => setIsAboutModalOpen(true)}
        onChatClick={() => setIsArchModalOpen(true)}
        onTagClick={() => setIsDetailModalOpen(true)}
        onSettingsClick={() => setIsArchModalOpen(true)}
      />

      {/* Main Workspace (Full Screen) */}
      <main className="fullscreen-main-pane">
        {/* Top Map Card */}
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

        {/* Bottom Row */}
        <div className="fullscreen-bottom-row">
          {/* Card 1: Location */}
          <CleanLocationCard
            selectedSegment={selectedSegment}
            onOpenDetails={() => setIsDetailModalOpen(true)}
          />

          {/* Card 2: Government DOT Analytics & Infrastructure Forecast */}
          <GovAnalyticsCard
            selectedSegment={selectedSegment}
            onOpenDetails={() => setIsDetailModalOpen(true)}
          />

          {/* Card 3: Agency Operations & Readiness */}
          <CleanTenantsCard
            selectedSegment={selectedSegment}
            onOpenNetworkStats={() => setIsArchModalOpen(true)}
          />
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
