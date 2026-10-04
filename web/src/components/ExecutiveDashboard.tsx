import { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import { REAL_NC_ROAD_SEGMENTS } from '../data/realRoads';
import type { RoadSegment, ViewFilter } from '../types/roadSegment';
import { CleanSidebar } from './CleanSidebar';
import { CleanMapCard, type CleanMapCardHandle } from './CleanMapCard';
import type { ConditionColorFilter } from './MapView';
import { CleanLocationCard } from './CleanLocationCard';
import { GovAnalyticsCard } from './GovAnalyticsCard';
import { CleanTenantsCard } from './CleanTenantsCard';
import { PMTilesArchitectureModal } from './PMTilesArchitectureModal';
import { AboutProjectModal } from './AboutProjectModal';
import { SegmentDetailModal } from './SegmentDetailModal';
import { SafeRouteModal } from './SafeRouteModal';
import type { RouteCorridor, RoutePreviewState } from '../types/safeRoute';
import { realRoadName } from '../utils/roadFacts';
import '../App.css';

function resolveCity(rawCity: string | undefined, lng: number, lat: number): string {
  if (rawCity && rawCity !== 'Unknown' && rawCity !== 'Statewide') {
    return rawCity;
  }
  const cities = [
    { name: 'Charlotte', lng: -80.84, lat: 35.22 },
    { name: 'Raleigh', lng: -78.64, lat: 35.78 },
    { name: 'Greensboro', lng: -79.79, lat: 36.07 },
    { name: 'Winston-Salem', lng: -80.24, lat: 36.10 },
    { name: 'Wilmington', lng: -77.94, lat: 34.23 },
    { name: 'Asheville', lng: -82.55, lat: 35.59 },
    { name: 'Fayetteville', lng: -78.88, lat: 35.05 },
    { name: 'Greenville', lng: -77.37, lat: 35.61 },
    { name: 'Boone', lng: -81.67, lat: 36.21 },
    { name: 'Outer Banks', lng: -75.62, lat: 35.95 }
  ];
  let closest = 'Raleigh';
  let minDist = Infinity;
  for (const c of cities) {
    const d = (lng - c.lng) ** 2 + (lat - c.lat) ** 2;
    if (d < minDist) {
      minDist = d;
      closest = c.name;
    }
  }
  return closest;
}

function normalizeLiveSegment(raw: any, index: number): RoadSegment | null {
  if (!raw) return null;
  const path: [number, number][] = (Array.isArray(raw.path) && raw.path.length > 0)
    ? raw.path
    : (Array.isArray(raw.paths) && raw.paths.length > 0 && Array.isArray(raw.paths[0]) ? raw.paths[0] : []);

  if (path.length === 0) return null;

  const firstCoord = path[0];
  const lng = firstCoord[0];
  const lat = firstCoord[1] || 35.78;
  const city = resolveCity(raw.city, lng, lat);
  // The API says whether the road is in the Helene zone; longitude is not a stand-in for it.
  const in_zone = Boolean(raw.in_helene_zone);

  // A road with no forecast (its rating is out of date) is left off this map rather than given a
  // made-up one. /gov lists those roads as "No estimate".
  const years_to_poor = raw.years_to_poor ?? raw.pred_years_to_poor;
  if (typeof years_to_poor !== 'number' || isNaN(years_to_poor)) return null;

  const score = typeof raw.score === 'number' && !isNaN(raw.score)
    ? raw.score
    : Math.max(0.05, Math.min(1.0, years_to_poor / 35.0));
  const pv_rating = raw.pv_rating ?? Math.round(score * 100);
  const seg_id = String(raw.seg_id || `seg-${index}`);
  const pred_flood = in_zone && typeof raw.pred_flood === 'number' ? raw.pred_flood : undefined;

  return {
    seg_id,
    name: realRoadName(seg_id) ?? raw.name ?? 'State road',
    source: raw.source || 'ncdot',
    pv_rating,
    // Surface age is not part of the forecast; the cards read it from the NCDOT record (useRoadRecord).
    pv_age: typeof raw.pv_age === 'number' ? raw.pv_age : 0,
    years_to_poor,
    flood_rank: raw.flood_rank || (!in_zone
      ? 'Not scored (outside the Helene zone)'
      : (pred_flood ?? 0) >= 0.5 ? 'High flood score (Helene zone)' : 'Lower flood score (Helene zone)'),
    drivers: raw.drivers || ['Pavement record (age, last treatment)', 'Traffic volume', 'Shape of the land (slope, drainage)'],
    chip_url: raw.chip_url || '',
    path,
    score,
    city,
    pred_rate: raw.pred_rate,
    pred_crack: typeof raw.pred_crack === 'number' ? raw.pred_crack : undefined,
    pred_flood,
    in_helene_zone: in_zone
  };
}

/** Roads kept in memory as the map is panned. Past this, the oldest are dropped so the map stays quick. */
const MAX_LIVE_SEGMENTS = 9000;

function mergeSegments(prev: RoadSegment[], incoming: RoadSegment[]): RoadSegment[] {
  const map = new Map<string, RoadSegment>();
  for (const s of prev) map.set(s.seg_id, s);
  for (const s of incoming) {
    map.delete(s.seg_id); // re-insert so the newest are last
    map.set(s.seg_id, s);
  }
  const all = Array.from(map.values());
  return all.length > MAX_LIVE_SEGMENTS ? all.slice(all.length - MAX_LIVE_SEGMENTS) : all;
}

export function ExecutiveDashboard() {
  const mapCardRef = useRef<CleanMapCardHandle>(null);

  const [segments, setSegments] = useState<RoadSegment[]>(REAL_NC_ROAD_SEGMENTS);
  const [viewFilter, setViewFilter] = useState<ViewFilter>('all');
  const [conditionColorFilter, setConditionColorFilter] = useState<ConditionColorFilter>('all');
  const [activeCity, setActiveCity] = useState<'Asheville' | 'Raleigh' | 'Statewide' | string | null>('Statewide');
  const [selectedSegment, setSelectedSegment] = useState<RoadSegment | null>(
    REAL_NC_ROAD_SEGMENTS.find(s => s.city === 'Raleigh') || REAL_NC_ROAD_SEGMENTS[0] || null
  );

  // On mount, fly to statewide view for entire NC
  useEffect(() => {
    const t = window.setTimeout(() => mapCardRef.current?.flyToCity('Statewide'), 400);
    return () => window.clearTimeout(t);
  }, []);

  const [isArchModalOpen, setIsArchModalOpen] = useState(false);
  const [isAboutModalOpen, setIsAboutModalOpen] = useState(false);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [isSafeRouteModalOpen, setIsSafeRouteModalOpen] = useState(false);
  const [activeRoutePreview, setActiveRoutePreview] = useState<RoutePreviewState | null>(null);

  // ── Entire NC: stats + statewide bbox streaming ──
  const [, setNcStats] = useState<any>(null);
  const bboxFetchTimeout = useRef<number | null>(null);

  // Fetch statewide stats once (total 112,443)
  useEffect(() => {
    const rawBase = import.meta.env.VITE_API_BASE_URL ?? '';
    const apiBase = (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' && rawBase.includes('127.0.0.1')) ? '' : rawBase;
    fetch(`${apiBase}/api/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) { setNcStats(d); console.log(`NC Stats: ${d.total_segments} total, ${d.helene_zone_segments} Helene zone`); }})
      .catch(() => {});
  }, []);

  // Initial statewide load — stream 3,000 segments across NC and merge into local cache
  useEffect(() => {
    let isMounted = true;
    const rawBase = import.meta.env.VITE_API_BASE_URL ?? '';
    const apiBase = (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' && rawBase.includes('127.0.0.1')) ? '' : rawBase;

    const loadStatewide = async () => {
      try {
        const bboxUrl = `${apiBase}/api/segments/bbox?minx=-84.5&miny=33.7&maxx=-75.2&maxy=36.7&limit=3000`;
        const res = await fetch(bboxUrl);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!isMounted || !data.segments || data.segments.length === 0) return;
        const normalized = (data.segments as any[])
          .map((s: any, idx: number) => normalizeLiveSegment(s, idx))
          .filter((s: RoadSegment | null): s is RoadSegment => s !== null);
        if (normalized.length > 0) {
          console.log(`Live API bbox statewide: ${data.matched} matched, ${normalized.length} loaded`);
          setSegments(prev => mergeSegments(prev, normalized));
          return;
        }
      } catch (e) {
        console.warn('NC bbox load failed, trying list endpoint', e);
      }
      try {
        const res2 = await fetch(`${apiBase}/api/segments?limit=3000`);
        if (!res2.ok) throw new Error(`HTTP ${res2.status}`);
        const data2 = await res2.json();
        if (!isMounted || !data2.segments?.length) return;
        const n = (data2.segments as any[]).map((s:any,i:number)=>normalizeLiveSegment(s,i)).filter((s): s is RoadSegment=>s!==null);
        if (n.length) setSegments(prev => mergeSegments(prev, n));
      } catch (err) {
        console.warn('API sync fallback to pre-bundled dataset:', err);
      }
    };
    loadStatewide();
    return () => { isMounted = false; };
  }, []);

  // Viewport-aware bbox streaming — as user pans/zooms, smoothly merge newly discovered segments
  const handleBboxChange = useCallback((bbox: [number, number, number, number]) => {
    const rawBase = import.meta.env.VITE_API_BASE_URL ?? '';
    const apiBase = (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' && rawBase.includes('127.0.0.1')) ? '' : rawBase;
    if (bboxFetchTimeout.current) window.clearTimeout(bboxFetchTimeout.current);
    bboxFetchTimeout.current = window.setTimeout(async () => {
      try {
        const [minx, miny, maxx, maxy] = bbox;
        const url = `${apiBase}/api/segments/bbox?minx=${minx}&miny=${miny}&maxx=${maxx}&maxy=${maxy}&limit=1500`;
        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.segments || data.segments.length === 0) return;
        const n = (data.segments as any[]).map((s:any,i:number)=>normalizeLiveSegment(s,i)).filter((s): s is RoadSegment=>s!==null);
        if (n.length >= 10) setSegments(prev => mergeSegments(prev, n));
      } catch {}
    }, 450);
  }, []);

  useEffect(() => () => {
    if (bboxFetchTimeout.current) window.clearTimeout(bboxFetchTimeout.current);
  }, []);

  // Escape closes whichever dialog is open (the road detail dialog handles its own).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      setIsSafeRouteModalOpen(false);
      setIsArchModalOpen(false);
      setIsAboutModalOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const filteredSegments = useMemo(() => {
    if (viewFilter === 'ncdot') {
      return segments.filter((s) => s.source === 'ncdot');
    }
    return segments;
  }, [segments, viewFilter]);

  const handleZoomCity = useCallback((city: 'Asheville' | 'Raleigh' | 'Statewide' | string) => {
    setActiveCity(city as any);
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

  const handlePreviewRouteOnMap = useCallback((corridor: RouteCorridor, option: 'fastest' | 'safest' | 'both') => {
    setActiveRoutePreview({ corridor, selectedOption: option });
    mapCardRef.current?.flyToRouteCorridor?.(corridor.center, corridor.zoom);
  }, []);

  const handleClearRoutePreview = useCallback(() => {
    setActiveRoutePreview(null);
  }, []);

  // Compute subtle U-shape ambient glow rating: Green (Safe), Yellow (Caution), Red (Danger), Blue (Flood)
  const ratingStatus: 'safe' | 'caution' | 'danger' | 'blue' = useMemo(() => {
    if (conditionColorFilter === 'green') return 'safe';
    if (conditionColorFilter === 'yellow') return 'caution';
    if (conditionColorFilter === 'red') return 'danger';
    if (conditionColorFilter === 'blue') return 'blue';

    if (selectedSegment) {
      if (selectedSegment.in_helene_zone || (selectedSegment.pred_flood && selectedSegment.pred_flood > 0.15)) {
        return 'blue';
      }
      const score = typeof selectedSegment.score === 'number' && !isNaN(selectedSegment.score)
        ? selectedSegment.score
        : (selectedSegment.pv_rating ? selectedSegment.pv_rating / 100 : 0.75);
      if (score < 0.45 || (selectedSegment.pred_crack && selectedSegment.pred_crack > 0.4)) {
        return 'danger';
      }
      if (score < 0.70) {
        return 'caution';
      }
      return 'safe';
    }

    return 'safe';
  }, [conditionColorFilter, selectedSegment]);

  return (
    <div className={`fullscreen-dashboard-root page-rating-${ratingStatus}`}>
      {/* Left Vertical Navigation Rail */}
      <CleanSidebar
        onHomeClick={() => handleZoomCity('Raleigh')}
        onRouteClick={() => setIsSafeRouteModalOpen(true)}
        onPlusClick={() => setIsDetailModalOpen(true)}
        onDocsClick={() => setIsAboutModalOpen(true)}
        onChatClick={() => setIsArchModalOpen(true)}
        onTagClick={() => setIsDetailModalOpen(true)}
        onSettingsClick={() => setIsArchModalOpen(true)}
      />

      {/* Main Workspace (Full Screen) */}
      <main className="fullscreen-main-pane">
        {/* Page-level Ambient U-Shape Rating Glow (Bottom-Left, Bottom, Bottom-Right) */}
        <div className={`page-u-frame-glow rating-${ratingStatus}`} aria-hidden="true" />

        {/* Main background U glow — soft diffused ambient glow behind all widgets */}
        <div className={`page-u-glow rating-${ratingStatus}`} aria-hidden="true">
          <div className="page-u-glow-blur" />
        </div>
        {/* Top Map Card — entire NC bbox streaming */}
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
          onBboxChange={handleBboxChange}
          conditionColorFilter={conditionColorFilter}
          onConditionColorFilterChange={setConditionColorFilter}
          onOpenSafeRoute={() => setIsSafeRouteModalOpen(true)}
          routePreview={activeRoutePreview}
          onClearRoutePreview={handleClearRoutePreview}
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

      {/* Safe Route Navigator Modal (Pillar 1 Driver Intelligence) */}
      <SafeRouteModal
        isOpen={isSafeRouteModalOpen}
        onClose={() => setIsSafeRouteModalOpen(false)}
        onPreviewOnMap={handlePreviewRouteOnMap}
      />

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
