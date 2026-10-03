import { useState, useMemo, useRef, useCallback } from 'react';
import { MOCK_ROAD_SEGMENTS } from './data/mockRoads';
import type { RoadSegment, ViewFilter } from './types/roadSegment';
import { MapView, type MapViewHandle } from './components/MapView';
import { Header } from './components/Header';
import { DetailPanel } from './components/DetailPanel';
import { Legend } from './components/Legend';
import { StatsOverlay } from './components/StatsOverlay';
import { PMTilesArchitectureModal } from './components/PMTilesArchitectureModal';
import './App.css';

export function App() {
  const mapViewRef = useRef<MapViewHandle>(null);

  // Filter mode: 'ncdot' (state roads only) vs 'all' (every street)
  const [viewFilter, setViewFilter] = useState<ViewFilter>('all');

  // Currently focused city: Raleigh (default) or Asheville
  const [activeCity, setActiveCity] = useState<'Asheville' | 'Raleigh' | null>('Raleigh');

  // Currently selected segment for deep inspection panel
  const [selectedSegment, setSelectedSegment] = useState<RoadSegment | null>(null);

  // Architecture modal state
  const [isArchModalOpen, setIsArchModalOpen] = useState(false);

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
    mapViewRef.current?.flyToCity(city);
  }, []);

  // Handle segment selection
  const handleSelectSegment = useCallback((segment: RoadSegment) => {
    setSelectedSegment(segment);
    setActiveCity(segment.city);
  }, []);

  // Handle fly to segment
  const handleFlyToSegment = useCallback((segment: RoadSegment) => {
    mapViewRef.current?.flyToSegment(segment);
  }, []);

  // Handle close detail panel
  const handleClosePanel = useCallback(() => {
    setSelectedSegment(null);
  }, []);

  return (
    <div className="app-container">
      {/* Top Application Header */}
      <Header
        viewFilter={viewFilter}
        onToggleFilter={setViewFilter}
        onZoomCity={handleZoomCity}
        activeCity={activeCity}
        totalSegmentsCount={MOCK_ROAD_SEGMENTS.length}
        visibleSegmentsCount={filteredSegments.length}
        onOpenArchitectureModal={() => setIsArchModalOpen(true)}
      />

      {/* Main Map Canvas Area */}
      <main className="main-content">
        <MapView
          ref={mapViewRef}
          segments={filteredSegments}
          selectedSegment={selectedSegment}
          onSelectSegment={handleSelectSegment}
        />

        {/* Aggregate Network Metrics Overlay */}
        <StatsOverlay segments={filteredSegments} />

        {/* Continuous Color Scale Legend */}
        <Legend />

        {/* Selected Road Segment Detail Panel */}
        {selectedSegment && (
          <DetailPanel
            segment={selectedSegment}
            onClose={handleClosePanel}
            onFlyTo={handleFlyToSegment}
          />
        )}
      </main>

      {/* 112k+ PMTiles Scalability Blueprint Modal */}
      <PMTilesArchitectureModal
        isOpen={isArchModalOpen}
        onClose={() => setIsArchModalOpen(false)}
      />
    </div>
  );
}

export default App;
