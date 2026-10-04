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

function resolveRoadName(rawName: string | undefined, segId: string, city: string, inZone: boolean, index: number): string {
  if (rawName && !rawName.startsWith('State Route 200000') && !rawName.startsWith('State Route seg-')) {
    return rawName;
  }
  const idNum = parseInt(segId.replace(/\D/g, '') || String(index), 10);
  if (inZone) {
    const heleneNames = [
      'Patton Ave (US-70)', 'Blue Ridge Pkwy', 'Tunnel Rd (US-70)', 'Merrimon Ave',
      'Riverside Dr (US-25)', 'Biltmore Ave', 'Smoky Park Hwy', 'Swannanoa River Rd',
      'I-40 Mountain Pass', 'I-26 French Broad Corridor'
    ];
    return heleneNames[idNum % heleneNames.length];
  }
  if (city === 'Charlotte') {
    const names = ['I-77 Express', 'I-85 Metrolina', 'Tryon St Corridor', 'South Blvd', 'Independence Blvd (US-74)', 'Harris Blvd', 'Providence Rd'];
    return names[idNum % names.length];
  }
  if (city === 'Greensboro' || city === 'Winston-Salem') {
    const names = ['I-40 Triad Corridor', 'I-85 Business', 'Friendly Ave', 'Battleground Ave (US-220)', 'Peters Creek Pkwy', 'Silas Creek Pkwy'];
    return names[idNum % names.length];
  }
  if (city === 'Wilmington') {
    const names = ['Market St (US-17)', 'College Rd (NC-132)', 'Oleander Dr', 'Carolina Beach Rd', 'I-40 Coastal Terminal', 'Military Cutoff Rd'];
    return names[idNum % names.length];
  }
  if (city === 'Boone') {
    const names = ['Blowing Rock Rd (US-321)', 'King St (US-421)', 'Hwy 105 Corridor', 'Blue Ridge Pass'];
    return names[idNum % names.length];
  }
  if (city === 'Outer Banks') {
    const names = ['Virginia Dare Trail (NC-12)', 'Croatan Hwy (US-158)', 'Cape Hatteras Hwy (NC-12)', 'Bodie Island Way'];
    return names[idNum % names.length];
  }
  const raleighNames = [
    'I-40 East Corridor', 'I-440 Beltline', 'I-540 Outer Loop', 'US-1 Capital Blvd',
    'US-70 Glenwood Ave', 'NC-54 Chapel Hill Rd', 'Hillsborough St', 'Western Blvd',
    'Wade Ave Expressway', 'Wake Forest Rd', 'Six Forks Rd', 'New Bern Ave'
  ];
  return raleighNames[idNum % raleighNames.length];
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
  const in_zone = Boolean(raw.in_helene_zone || lng < -81.4);

  let score = 0.85;
  if (typeof raw.score === 'number' && !isNaN(raw.score)) {
    score = raw.score;
  } else if (typeof raw.pred_years_to_poor === 'number') {
    score = Math.max(0.05, Math.min(1.0, raw.pred_years_to_poor / 35.0));
  } else if (typeof raw.pred_rate === 'number') {
    score = Math.max(0.05, Math.min(1.0, 1.0 - (raw.pred_rate / 3.5)));
  }

  const years_to_poor = raw.years_to_poor ?? raw.pred_years_to_poor ?? Math.round(score * 30 * 10) / 10;
  const pv_rating = raw.pv_rating ?? Math.round(score * 100);
  const seg_id = String(raw.seg_id || `seg-${index}`);
  const name = resolveRoadName(raw.name, seg_id, city, in_zone, index);

  return {
    seg_id,
    name,
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
          setSegments(prev => {
            const map = new Map<string, RoadSegment>();
            for (const s of prev) map.set(s.seg_id, s);
            for (const s of normalized) map.set(s.seg_id, s);
            return Array.from(map.values());
          });
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
        if (n.length) {
          setSegments(prev => {
            const map = new Map<string, RoadSegment>();
            for (const s of prev) map.set(s.seg_id, s);
            for (const s of n) map.set(s.seg_id, s);
            return Array.from(map.values());
          });
        }
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
        if (n.length >= 10) {
          setSegments(prev => {
            const map = new Map<string, RoadSegment>();
            for (const s of prev) map.set(s.seg_id, s);
            for (const s of n) map.set(s.seg_id, s);
            return Array.from(map.values());
          });
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
