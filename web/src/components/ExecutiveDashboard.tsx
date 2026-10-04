import { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import { REAL_NC_ROAD_SEGMENTS } from '../data/realRoads';
import type { RoadSegment, ViewFilter } from '../types/roadSegment';
import { CleanSidebar } from './CleanSidebar';
import { CleanMapCard, type CleanMapCardHandle } from './CleanMapCard';
import { CleanLocationCard } from './CleanLocationCard';
import { GovAnalyticsCard } from './GovAnalyticsCard';
import { CleanTenantsCard } from './CleanTenantsCard';
import { PMTilesArchitectureModal } from './PMTilesArchitectureModal';
import { AboutProjectModal } from './AboutProjectModal';
import { SegmentDetailModal } from './SegmentDetailModal';
import '../App.css';

function normalizeLiveSegment(raw: any, index: number): RoadSegment | null {
  if (!raw) return null;
  const path: [number, number][] = (Array.isArray(raw.path) && raw.path.length > 0)
    ? raw.path
    : (Array.isArray(raw.paths) && raw.paths.length > 0 && Array.isArray(raw.paths[0]) ? raw.paths[0] : []);

  if (path.length === 0) return null;

  const firstCoord = path[0];
  const lng = firstCoord[0];
  const city: 'Raleigh' | 'Asheville' = raw.city || (lng < -81.0 ? 'Asheville' : 'Raleigh');

  let score = 0.85;
  if (typeof raw.score === 'number' && !isNaN(raw.score)) {
    score = raw.score;
  } else if (typeof raw.pred_years_to_poor === 'number') {
    score = Math.max(0.05, Math.min(1.0, raw.pred_years_to_poor / 35.0));
  } else if (typeof raw.pred_rate === 'number') {
    score = Math.max(0.05, Math.min(1.0, 1.0 - (raw.pred_rate / 3.5)));
  }

  const in_zone = Boolean(raw.in_helene_zone);
  const years_to_poor = raw.years_to_poor ?? raw.pred_years_to_poor ?? Math.round(score * 30 * 10) / 10;
  const pv_rating = raw.pv_rating ?? Math.round(score * 100);

  return {
    seg_id: String(raw.seg_id || `seg-${index}`),
    name: raw.name || `State Route ${String(raw.seg_id || '').split(':')[1] || raw.seg_id || index}`,
    source: raw.source || 'ncdot',
    pv_rating,
    pv_age: raw.pv_age ?? 12,
    years_to_poor,
    flood_rank: raw.flood_rank || (in_zone ? 'High Risk (Helene Zone)' : 'Low Risk (Zone X)'),
    drivers: raw.drivers || [
      'Traffic Volume (AADT)',
      '3DEP Slope Index',
      in_zone ? 'Helene Storm Surge' : 'Surface Oxidation'
    ],
    chip_url: raw.chip_url || `/assets/reference/chip_${(index % 3) + 1}.webp`,
    path,
    score,
    city,
    pred_rate: raw.pred_rate,
    pred_crack: raw.pred_crack ?? 0.05,
    pred_flood: raw.pred_flood,
    in_helene_zone: in_zone
  };
}

export function ExecutiveDashboard() {
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
    const rawBase = import.meta.env.VITE_API_BASE_URL ?? '';
    // Avoid connecting to localhost in production browser
    const apiBase = (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' && rawBase.includes('127.0.0.1')) ? '' : rawBase;

    fetch(`${apiBase}/api/segments?limit=2500`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (isMounted && data && Array.isArray(data.segments) && data.segments.length > 0) {
          const normalized = data.segments
            .map((s: any, idx: number) => normalizeLiveSegment(s, idx))
            .filter((s: RoadSegment | null): s is RoadSegment => s !== null);

          if (normalized.length > 0) {
            console.log(`Live API connected! Loaded ${normalized.length} real-time statewide NC segments.`);
            setSegments(normalized);
            const firstInCity = normalized.find((s: RoadSegment) => s.city === 'Raleigh') || normalized[0];
            if (firstInCity) {
              setSelectedSegment(firstInCity);
            }
          }
        }
      })
      .catch((err) => {
        console.warn('API sync fallback to pre-bundled dataset:', err);
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

export default ExecutiveDashboard;
