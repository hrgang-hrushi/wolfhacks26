import { useState, useMemo, useRef, useCallback } from 'react';
import { MOCK_ROAD_SEGMENTS } from './data/mockRoads';
import type { RoadSegment, ViewFilter } from './types/roadSegment';
import { SidebarRail } from './components/SidebarRail';
import { TopNavbar } from './components/TopNavbar';
import { SubHeaderRow } from './components/SubHeaderRow';
import { KpiMetricsRow } from './components/KpiMetricsRow';
import { MainMapCard, type MainMapCardHandle } from './components/MainMapCard';
import { RevenueBarChartCard } from './components/RevenueBarChartCard';
import { DonutChartCard } from './components/DonutChartCard';
import { RegionCapsuleBarsCard } from './components/RegionCapsuleBarsCard';
import { SegmentDetailModal } from './components/SegmentDetailModal';
import { PMTilesArchitectureModal } from './components/PMTilesArchitectureModal';
import { AboutProjectModal } from './components/AboutProjectModal';
import './App.css';

export function App() {
  const mapCardRef = useRef<MainMapCardHandle>(null);

  // Filter mode: 'ncdot' (state roads only) vs 'all' (every street)
  const [viewFilter, setViewFilter] = useState<ViewFilter>('all');

  // Currently focused city: Raleigh (default) or Asheville
  const [activeCity, setActiveCity] = useState<'Asheville' | 'Raleigh' | null>('Raleigh');

  // Currently selected segment for deep inspection panel
  const [selectedSegment, setSelectedSegment] = useState<RoadSegment | null>(null);

  // Modals visibility
  const [isArchModalOpen, setIsArchModalOpen] = useState(false);
  const [isAboutModalOpen, setIsAboutModalOpen] = useState(false);

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

  // Handle export data
  const handleExportData = useCallback(() => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(filteredSegments, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `nc_road_predictions_${viewFilter}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  }, [filteredSegments, viewFilter]);

  return (
    <div className="canvas-frame-container">
      {/* Outer Studio Backdrop Grid matching frame 7 */}
      <div className="studio-canvas-backdrop" />

      {/* Main White App Window (1404px x 936px canvas matching frame 7) */}
      <div className="app-window-card">
        {/* Left Vertical Navigation Rail */}
        <SidebarRail
          onOpenAbout={() => setIsAboutModalOpen(true)}
          onOpenArchRoadmap={() => setIsArchModalOpen(true)}
        />

        {/* Main Content Pane */}
        <div className="app-main-pane">
          {/* Top Navbar */}
          <TopNavbar
            onSearchClick={() => {
              if (filteredSegments[0]) handleSelectSegment(filteredSegments[0]);
            }}
          />

          {/* Scrollable Dashboard Body */}
          <div className="dashboard-content-scroll">
            {/* Sub-Header Greeting & Action Controls */}
            <SubHeaderRow
              viewFilter={viewFilter}
              onToggleFilter={setViewFilter}
              activeCity={activeCity}
              onZoomCity={handleZoomCity}
              onExportData={handleExportData}
            />

            {/* Top 4 KPI Metrics Row */}
            <KpiMetricsRow segments={filteredSegments} />

            {/* Main 2-Column Analytics Grid */}
            <div className="main-analytics-grid">
              {/* Left Column: Underperforming Areas Map & 4 Radial Gauges */}
              <div className="analytics-left-col">
                <MainMapCard
                  ref={mapCardRef}
                  segments={filteredSegments}
                  selectedSegment={selectedSegment}
                  onSelectSegment={handleSelectSegment}
                />
              </div>

              {/* Right Column: Charts Stack */}
              <div className="analytics-right-col">
                {/* CY Revenue vs PY Revenue Bar Chart */}
                <RevenueBarChartCard />

                {/* Bottom Row: Donut Chart & Capsule Bars */}
                <div className="bottom-charts-row">
                  <DonutChartCard />
                  <RegionCapsuleBarsCard />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Road Segment Detail Inspection Slide-Over */}
        {selectedSegment && (
          <SegmentDetailModal
            segment={selectedSegment}
            onClose={() => setSelectedSegment(null)}
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
