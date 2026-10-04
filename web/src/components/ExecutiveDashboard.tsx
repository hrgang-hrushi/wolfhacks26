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
  const [conditionColorFilter, setConditionColorFilter] = useState<ConditionColorFilter>('all');
  const [activeCity, setActiveCity] = useState<'Asheville' | 'Raleigh' | 'Statewide' | null>('Statewide');
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

  // Initial statewide load — entire NC via bbox covering state bounds, fallback to first 25k if truncated
  useEffect(() => {
    let isMounted = true;
    const rawBase = import.meta.env.VITE_API_BASE_URL ?? '';
    const apiBase = (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' && rawBase.includes('127.0.0.1')) ? '' : rawBase;

    const loadStatewide = async () => {
      try {
        // Try bbox covering entire NC first (most complete, leverages STRtree - up to 25k segments)
        const bboxUrl = `${apiBase}/api/segments/bbox?minx=-84.5&miny=33.7&maxx=-75.2&maxy=36.7&limit=25000`;
        const res = await fetch(bboxUrl);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!isMounted || !data.segments || data.segments.length === 0) return;
        const normalized = (data.segments as any[])
          .map((s: any, idx: number) => normalizeLiveSegment(s, idx))
          .filter((s: RoadSegment | null): s is RoadSegment => s !== null);
        if (normalized.length > 0) {
          console.log(`Live API bbox statewide: ${data.matched} matched, ${normalized.length} loaded (truncated=${data.truncated})`);
          setSegments(normalized);
          // Keep selected in current city if possible, else first
          const firstInCity = normalized.find((s: RoadSegment) => s.city === activeCity) || normalized[0];
          if (firstInCity) setSelectedSegment(firstInCity);
          // If truncated, also kick off paginated full-state load in background via /api/segments?limit=25000
          if (data.truncated) {
            fetch(`${apiBase}/api/segments?limit=25000`)
              .then(r => r.json())
              .then(d2 => {
                if (!isMounted || !d2.segments?.length) return;
                const n2 = (d2.segments as any[]).map((s: any, i:number)=>normalizeLiveSegment(s,i)).filter((s): s is RoadSegment=>s!==null);
                if (n2.length > normalized.length) {
                  console.log(`Background full-state load: ${n2.length} segments`);
                  setSegments(n2);
                }
              }).catch(()=>{});
          }
          return;
        }
      } catch (e) {
        console.warn('NC bbox load failed, trying list endpoint', e);
      }
      // Fallback: list endpoint (up to 25k segments)
      try {
        const res2 = await fetch(`${apiBase}/api/segments?limit=25000`);
        if (!res2.ok) throw new Error(`HTTP ${res2.status}`);
        const data2 = await res2.json();
        if (!isMounted || !data2.segments?.length) return;
        const n = (data2.segments as any[]).map((s:any,i:number)=>normalizeLiveSegment(s,i)).filter((s): s is RoadSegment=>s!==null);
        if (n.length) {
          console.log(`Live API list load: ${n.length} segments`);
          setSegments(n);
          const f = n.find((s: RoadSegment)=>s.city==='Raleigh')||n[0];
          if (f) setSelectedSegment(f);
        }
      } catch (err) {
        console.warn('API sync fallback to pre-bundled dataset:', err);
      }
    };
    loadStatewide();
    return () => { isMounted = false; };
  }, []);

  // Viewport-aware bbox streaming — as user pans/zooms, fetch visible segments (entire NC capable)
  const handleBboxChange = useCallback((bbox: [number, number, number, number]) => {
    const rawBase = import.meta.env.VITE_API_BASE_URL ?? '';
    const apiBase = (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' && rawBase.includes('127.0.0.1')) ? '' : rawBase;
    if (bboxFetchTimeout.current) window.clearTimeout(bboxFetchTimeout.current);
    bboxFetchTimeout.current = window.setTimeout(async () => {
      try {
        const [minx, miny, maxx, maxy] = bbox;
        const url = `${apiBase}/api/segments/bbox?minx=${minx}&miny=${miny}&maxx=${maxx}&maxy=${maxy}&limit=2500`;
        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.segments || data.segments.length === 0) return;
        // Only switch to bbox data if it yields a meaningfully different viewport and not statewide already
        // Keep statewide data if bbox returns fewer than 80% of current; otherwise update for precision
        const n = (data.segments as any[]).map((s:any,i:number)=>normalizeLiveSegment(s,i)).filter((s): s is RoadSegment=>s!==null);
        if (n.length >= 20) {
          // Preserve selected if still in viewport, else keep
          console.log(`Viewport bbox: ${data.matched} matched → ${n.length} rendered`);
          // We merge: if viewport is small (city zoom), show its 2500; if statewide zoom, keep statewide 5000
          // Heuristic: if map is zoomed in (bbox width < 2 degrees), use viewport data
          const bboxWidth = maxx - minx;
          if (bboxWidth < 2.5) {
            setSegments(n);
          }
        }
      } catch {}
    }, 450);
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
