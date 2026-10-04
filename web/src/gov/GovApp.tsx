/**
 * Dashboard A: the agency dashboard (/gov). Desktop, dense, calm.
 *
 * See road condition across the state, rank what to fix, and dispatch crews.
 * Every number is read from the static files in /data; work orders and crews
 * are a demo of the workflow and live in this browser only.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Layer, PickingInfo } from '@deck.gl/core';
import {
  Bell,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  CloudRain,
  Home,
  LayoutDashboard,
  ListOrdered,
  Maximize2,
  Minimize2,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  ShieldCheck,
  Smartphone,
  Sun,
  X,
} from 'lucide-react';
import {
  TIERS,
  countyName,
  detailOf,
  findSeg,
  fmtInt,
  fmtPct,
  fmtYtp,
  loadCounty,
  loadDetail,
  loadRanked,
  loadRoutes,
  loadStorm,
  midOf,
  roadLabel,
  rowToSeg,
  segInBox,
  type Bounds,
  type Mode,
  type PathItem,
  type RGBA,
  type Row,
  type Seg,
} from '../lib/data';
import { casedLayers, pinLayer, roadLayers, selectionLayers, visibleSegs, widthScaleForZoom, type Pin } from '../lib/layers';
import MapLibreDeck from '../lib/MapLibreDeck';
import { NC_VIEW, type MapHandle, type MapView } from '../lib/mapTypes';
import { pinLabelLayer } from '../lib/pinLabels';
import { MODES, useGovPrefs, useTheme, type KpiKey } from '../lib/prefs';
import { useDetail } from '../lib/hooks';
import { Legend } from '../lib/ui';
import { useRoadData, useStats } from '../lib/useRoadData';
import { orderSegToSeg, orders as orderStore, toOrderSeg, useWorkOrders, type OrderSeg, type WorkOrder } from '../lib/workOrders';
import { AlertsPanel } from './AlertsPanel';
import { DEFAULT_FILTERS, mapFilter, parseRouteQuery, type Filters } from './filters';
import { DisplayMenu, Splitter } from './Layout';
import { CountySelect, FilterButton, FilterChips, LayerSwitch, SearchBox } from './MapControls';
import { SegmentPanel } from './SegmentPanel';
import { PrintStorm, StormPanel } from './StormPanel';
import { TransparencyPanel } from './TransparencyPanel';
import { OrderPanel, PrintOrder, WorkOrdersTable } from './WorkOrders';
import { WorkQueue } from './WorkQueue';
import './gov.css';

type Side = 'road' | 'order' | 'storm' | 'model';
type Bottom = 'queue' | 'orders' | 'alerts';
type PrintJob = { kind: 'order'; order: WorkOrder } | { kind: 'storm'; rows: Row[] };

const MAX_SHARDS = 40;
const MAX_BOX_SELECT = 500;
/** The map never gets narrower or shorter than this while a divider is dragged. */
const MIN_MAP_W = 340;
const MIN_MAP_H = 190;
const MIN_SIDE_W = 280;
const MIN_BOTTOM_H = 120;
const DISPATCH_CASING: RGBA = [29, 78, 216, 255];
const ORDER_CASING: RGBA = [124, 58, 237, 255];
const STORM_PIN: RGBA = [153, 27, 27, 255];

function isPathItem(o: unknown): o is PathItem {
  return typeof o === 'object' && o !== null && 'seg' in o;
}

export default function GovApp() {
  const { stats, error } = useStats();
  const wo = useWorkOrders();
  const theme = useTheme();
  const { prefs, setPrefs, resetPrefs } = useGovPrefs();
  const mapRef = useRef<MapHandle>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const topRef = useRef<HTMLElement>(null);
  const midRef = useRef<HTMLDivElement>(null);
  const sideRef = useRef<HTMLElement>(null);
  const bottomRef = useRef<HTMLElement>(null);

  const [view, setView] = useState<MapView | null>(null);
  const road = useRoadData(stats, view, MAX_SHARDS);
  const mode = prefs.mode;
  const setMode = useCallback((m: Mode) => setPrefs({ mode: m }), [setPrefs]);
  const searchRef = useRef<HTMLInputElement>(null);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selection, setSelection] = useState<Seg[]>([]);
  const detail = useDetail(selection.length === 1 ? selection[0] : null, stats);

  const [side, setSideTab] = useState<Side>('road');
  const [bottom, setBottomTab] = useState<Bottom>('queue');
  // Choosing a tab, or anything that fills a panel, brings a hidden panel back.
  const setSide = useCallback(
    (s: Side) => {
      setSideTab(s);
      setPrefs({ sideOpen: true });
    },
    [setPrefs],
  );
  const setBottom = useCallback(
    (b: Bottom) => {
      setBottomTab(b);
      setPrefs({ bottomOpen: true });
    },
    [setPrefs],
  );
  const [activeOrderId, setActiveOrderId] = useState<string | null>(null);
  const [target, setTarget] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const [queueData, setQueueData] = useState<{ county: string; rows: Row[]; perTier: number | null } | null>(null);
  const [storm, setStorm] = useState<{ rows: Row[]; min: number } | null>(null);
  const [stormN, setStormN] = useState(50);
  const [print, setPrint] = useState<PrintJob | null>(null);
  const [box, setBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [search, setSearch] = useState<{ message: string | null; choices: { code: string; name: string }[] | null; pending: string | null }>({
    message: null,
    choices: null,
    pending: null,
  });

  const activeOrder = wo.orders.find((o) => o.id === activeOrderId) ?? null;

  // ---- data that follows the county filter ----------------------------------
  useEffect(() => {
    let live = true;
    const code = filters.county;
    const p = code ? loadCounty(code).then((c) => ({ rows: c.rows, perTier: null as number | null })) : loadRanked().then((r) => ({ rows: r.rows, perTier: r.per_tier }));
    p.then((r) => live && setQueueData({ county: code, ...r })).catch(() => live && setQueueData({ county: code, rows: [], perTier: null }));
    return () => {
      live = false;
    };
  }, [filters.county]);
  // Until the file for the chosen county arrives, the queue shows "Loading" rather than the previous county's rows.
  const queue = useMemo(
    () =>
      queueData && queueData.county === filters.county
        ? { rows: queueData.rows as Row[] | null, county: filters.county || null, perTier: queueData.perTier }
        : { rows: null, county: filters.county || null, perTier: null },
    [queueData, filters.county],
  );

  useEffect(() => {
    if (storm || (side !== 'storm' && bottom !== 'alerts')) return;
    let live = true;
    loadStorm()
      .then((s) => live && setStorm({ rows: s.rows, min: s.min_flood }))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [side, bottom, storm]);

  // ---- selection ---------------------------------------------------------------
  const pickSeg = useCallback(
    (seg: Seg) => {
      setSelection([seg]);
      setSide('road');
    },
    [setSide],
  );

  const zoomTo = useCallback((seg: { paths: number[][] }) => {
    const [lng, lat] = midOf(seg.paths);
    mapRef.current?.flyTo(lng, lat, 13);
  }, []);

  // Rows without their own line need a download to find it. Only the latest click may land.
  const pickSeq = useRef(0);
  const pickRow = useCallback(
    async (row: Row, keepSide = false) => {
      if (!stats) return;
      const n = ++pickSeq.current;
      mapRef.current?.flyTo(row.c[0], row.c[1], 13);
      const seg = rowToSeg(row) ?? (await findSeg(row.id, row.c, stats).catch(() => null));
      if (n !== pickSeq.current) return;
      if (!seg) {
        setNotice('That road’s line did not load. Check the connection and try again.');
        return;
      }
      setNotice(null);
      setSelection([seg]);
      if (!keepSide) setSide('road');
    },
    [stats, setSide],
  );

  // ---- work orders ---------------------------------------------------------------
  const openOrder = useCallback(
    (id: string) => {
      setActiveOrderId(id);
      setTarget(id);
      setSide('order');
      setBottom('orders');
    },
    [setSide, setBottom],
  );

  // The chosen order can be marked Done (or deleted) after it was picked; a finished order takes no more roads.
  const openTarget = wo.orders.some((o) => o.id === target && o.status !== 'Done') ? target : null;

  const addSegs = useCallback(
    async (segs: Seg[]) => {
      if (!stats || segs.length === 0) return;
      setBusy(true);
      try {
        const details = await Promise.all(segs.map((s) => loadDetail(s, stats).catch(() => null)));
        openOrder(orderStore.addSegs(openTarget, segs.map((s, i) => toOrderSeg(s, details[i], stats))));
      } finally {
        setBusy(false);
      }
    },
    [stats, openTarget, openOrder],
  );

  const addRows = useCallback(
    async (rows: Row[]) => {
      if (!stats || rows.length === 0) return;
      setBusy(true);
      try {
        const segs = await Promise.all(rows.map((r) => rowToSeg(r) ?? findSeg(r.id, r.c, stats).catch(() => null)));
        const out: OrderSeg[] = [];
        segs.forEach((seg, i) => {
          if (seg) out.push(toOrderSeg(seg, detailOf(rows[i]), stats));
        });
        if (out.length) openOrder(orderStore.addSegs(openTarget, out));
        if (out.length < rows.length) setNotice(`${rows.length - out.length} road${rows.length - out.length === 1 ? '' : 's'} could not be added: the line did not load.`);
      } finally {
        setBusy(false);
      }
    },
    [stats, openTarget, openOrder],
  );

  // ---- map layers ------------------------------------------------------------------
  const filter = useMemo(() => mapFilter(filters, mode), [filters, mode]);
  const widthScale = widthScaleForZoom(view?.zoom ?? NC_VIEW.zoom);
  const stormMode = side === 'storm';

  const dispatched = useMemo(
    () => wo.orders.filter((o) => o.status === 'Dispatched' || o.status === 'In progress').flatMap((o) => o.segs.map(orderSegToSeg)),
    [wo.orders],
  );
  const openOrderSegs = useMemo(() => (side === 'order' && activeOrder ? activeOrder.segs.map(orderSegToSeg) : []), [side, activeOrder]);

  const stormPins = useMemo<(Pin & { row: Row })[]>(
    () =>
      stormMode && storm
        ? storm.rows.slice(0, stormN).map((row) => ({ id: row.id, c: row.c, row, color: STORM_PIN, radius: 9, label: stormN <= 100 ? String(row.rank) : undefined }))
        : [],
    [stormMode, storm, stormN],
  );

  const layers = useMemo<Layer[]>(() => {
    const out: Layer[] = roadLayers({ shards: road.shards, mode, filter, onPick: pickSeg, widthScale, dim: stormMode });
    out.push(...casedLayers('dispatched', dispatched, mode, DISPATCH_CASING, 10, 4, pickSeg));
    out.push(...casedLayers('open-order', openOrderSegs, mode, ORDER_CASING, 10, 4, pickSeg));
    out.push(...selectionLayers('sel', selection, mode, theme.dark));
    if (stormPins.length) {
      out.push(pinLayer('storm', stormPins, (p) => void pickRow(p.row, true)));
      if (stormPins[0].label) out.push(pinLabelLayer('storm', stormPins));
    }
    return out;
  }, [road.shards, mode, filter, pickSeg, widthScale, stormMode, dispatched, openOrderSegs, selection, stormPins, pickRow, theme.dark]);

  const getTooltip = useCallback(
    (info: PickingInfo) => {
      const o: unknown = info.object;
      if (!isPathItem(o)) return null;
      const s = o.seg;
      const county = countyName(s.id, stats);
      return {
        html: `<b>${roadLabel(s.id)}</b>${county ? ` · ${county}` : ''}<br>${TIERS[s.tier].label}<br>Poor: ${fmtYtp(s.ytp)} · cracking ${fmtPct(s.crack)}${
          s.hz && s.flood != null ? ` · flood ${s.flood.toFixed(2)}` : ''
        }`,
      };
    },
    [stats],
  );

  // ---- box select (shift-drag) ------------------------------------------------------
  const onMouseDownCapture = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!e.shiftKey || e.button !== 0 || !wrapRef.current) return;
    e.preventDefault();
    e.stopPropagation();
    const rect = wrapRef.current.getBoundingClientRect();
    const x0 = e.clientX - rect.left;
    const y0 = e.clientY - rect.top;
    let last = { x0, y0, x1: x0, y1: y0 };
    setBox(last);
    mapRef.current?.setDragPan(false);
    const move = (ev: MouseEvent) => {
      last = { x0, y0, x1: ev.clientX - rect.left, y1: ev.clientY - rect.top };
      setBox(last);
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      mapRef.current?.setDragPan(true);
      setBox(null);
      const a = mapRef.current?.unproject(Math.min(last.x0, last.x1), Math.max(last.y0, last.y1));
      const b = mapRef.current?.unproject(Math.max(last.x0, last.x1), Math.min(last.y0, last.y1));
      if (!a || !b || Math.abs(last.x1 - last.x0) < 4 || Math.abs(last.y1 - last.y0) < 4) return;
      const bounds: Bounds = [a[0], a[1], b[0], b[1]];
      const hits = visibleSegs(road.shards, filter)
        .filter((s) => segInBox(s, bounds))
        .sort((p, q) => q.score - p.score)
        .slice(0, MAX_BOX_SELECT);
      setSelection(hits);
      setSide('road');
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };

  // ---- search and county ---------------------------------------------------------------
  const setCounty = useCallback(
    (code: string, fit = true) => {
      setFilters((f) => ({ ...f, county: code }));
      const c = stats?.counties[code];
      if (fit && c) mapRef.current?.fitBounds(c.b, 40);
      if (fit && !code) mapRef.current?.flyTo(NC_VIEW.lng, NC_VIEW.lat, NC_VIEW.zoom);
    },
    [stats],
  );

  const goSr = useCallback(
    async (num: number, code: string) => {
      const file = await loadCounty(code).catch(() => null);
      if (!file) {
        setSearch({ message: 'That county’s road list did not load. Check the connection and try again.', choices: null, pending: null });
        return;
      }
      const b = file.sr[String(num)];
      if (!b) {
        setSearch({ message: `SR ${num} is not in ${file.name} County.`, choices: null, pending: null });
        return;
      }
      setFilters((f) => ({ ...f, county: code, route: `SR ${num}` }));
      mapRef.current?.fitBounds(b, 80);
      setSearch({ message: null, choices: null, pending: null });
    },
    [],
  );

  const onSearch = useCallback(
    async (q: string) => {
      if (!stats) return;
      const text = q.trim();
      if (!text) {
        setSearch({ message: null, choices: null, pending: null });
        setFilters((f) => ({ ...f, route: '' }));
        return;
      }
      const r = parseRouteQuery(text);
      if (!r) {
        const hit = Object.entries(stats.counties).find(([, c]) => c.name.toLowerCase() === text.toLowerCase().replace(/\s+county$/, ''));
        if (hit) {
          setCounty(hit[0]);
          setSearch({ message: null, choices: null, pending: null });
        } else setSearch({ message: 'Type a route such as “NC 12”, “I-40” or “SR 2748”, or a county name.', choices: null, pending: null });
        return;
      }
      try {
        const routes = await loadRoutes();
        if (r.cls !== 'SR') {
          const hit = routes.primary[r.label];
          if (!hit) {
            setSearch({ message: `No ${r.label} among the scored state roads.`, choices: null, pending: null });
            return;
          }
          setFilters((f) => ({ ...f, county: '', route: r.label }));
          mapRef.current?.fitBounds(hit.b, 60);
          setSearch({ message: null, choices: null, pending: null });
          return;
        }
        const codes = (routes.sr[String(r.num)] ?? '').split(' ').filter(Boolean);
        if (codes.length === 0) setSearch({ message: `No SR ${r.num} among the scored state roads.`, choices: null, pending: null });
        else if (filters.county && codes.includes(filters.county)) await goSr(r.num, filters.county);
        else if (codes.length === 1) await goSr(r.num, codes[0]);
        else
          setSearch({
            message: `SR ${r.num} exists in ${codes.length} counties (secondary road numbers repeat). Which one?`,
            choices: codes.map((code) => ({ code, name: stats.counties[code]?.name ?? code })).sort((a, b) => a.name.localeCompare(b.name)),
            pending: String(r.num),
          });
      } catch {
        setSearch({ message: 'The route index did not load.', choices: null, pending: null });
      }
    },
    [stats, filters.county, setCounty, goSr],
  );

  // ---- a link to the selected road ---------------------------------------------------
  // ?seg=<id>&at=<lng>,<lat> reopens a road; the point says which data file holds it.
  const linkRead = useRef(false);
  useEffect(() => {
    if (!stats || linkRead.current) return;
    linkRead.current = true;
    const q = new URLSearchParams(window.location.search);
    const id = q.get('seg');
    const at = (q.get('at') ?? '').split(',').map(Number);
    if (!id || at.length !== 2 || !at.every(Number.isFinite)) return;
    void pickRow({ id, c: [at[0], at[1]] } as Row);
  }, [stats, pickRow]);

  useEffect(() => {
    if (!stats) return; // the link has not been read yet
    const url = new URL(window.location.href);
    if (selection.length === 1) {
      const [lng, lat] = midOf(selection[0].paths);
      url.searchParams.set('seg', selection[0].id);
      url.searchParams.set('at', `${lng.toFixed(5)},${lat.toFixed(5)}`);
    } else {
      url.searchParams.delete('seg');
      url.searchParams.delete('at');
    }
    window.history.replaceState(null, '', url);
  }, [selection, stats]);

  // ---- keyboard: / search, 1-4 map colouring, Escape clears the selection ---------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable)) return;
      if (e.key === '/') {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === 'Escape') {
        if (!document.querySelector('.g-pop')) setSelection([]);
      } else if (e.key >= '1' && e.key <= '4') setMode(MODES[Number(e.key) - 1]);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setMode]);

  // ---- printing ------------------------------------------------------------------------
  useEffect(() => {
    if (!print) return;
    const done = () => setPrint(null);
    window.addEventListener('afterprint', done);
    const t = window.setTimeout(() => window.print(), 150);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener('afterprint', done);
    };
  }, [print]);

  const enterStorm = () => {
    setSide('storm');
    setMode('flood');
    mapRef.current?.fitBounds([-84.3, 34.95, -80.4, 36.6], 30);
  };

  const rail: { key: string; label: string; icon: React.ReactNode; on: boolean; go: () => void }[] = [
    { key: 'home', label: 'Statewide view', icon: <Home size={20} />, on: false, go: () => mapRef.current?.flyTo(NC_VIEW.lng, NC_VIEW.lat, NC_VIEW.zoom) },
    { key: 'queue', label: 'Work queue', icon: <ListOrdered size={20} />, on: bottom === 'queue', go: () => setBottom('queue') },
    { key: 'orders', label: 'Work orders', icon: <ClipboardList size={20} />, on: bottom === 'orders', go: () => { setBottom('orders'); setSide('order'); } },
    { key: 'storm', label: 'Storm readiness', icon: <CloudRain size={20} />, on: side === 'storm', go: enterStorm },
    { key: 'alerts', label: 'Alerts', icon: <Bell size={20} />, on: bottom === 'alerts', go: () => setBottom('alerts') },
    { key: 'model', label: 'Model transparency', icon: <ShieldCheck size={20} />, on: side === 'model', go: () => setSide('model') },
  ];

  const share = (n: number) => (stats ? `${fmtPct(n / stats.total, 1)} of roads` : '');
  const kpiDefs: Record<KpiKey, { label: string; value: string; note: string; tone?: string }> | null = stats
    ? {
        total: { label: 'State roads', value: fmtInt(stats.total), note: 'stretches scored' },
        fix_now: { label: 'Fix now', value: fmtInt(stats.tiers.fix_now), note: share(stats.tiers.fix_now), tone: 'red' },
        within_year: { label: 'Fix within a year', value: fmtInt(stats.tiers.within_year), note: share(stats.tiers.within_year), tone: 'orange' },
        within_five: { label: 'Plan within five years', value: fmtInt(stats.tiers.within_five), note: share(stats.tiers.within_five), tone: 'amber' },
        high_flood: { label: 'High flood score', value: fmtInt(stats.helene.high_flood), note: `of ${fmtInt(stats.helene.zone)} in Helene zone` },
        heldout: { label: 'Held-out', value: fmtPct(stats.heldout.rate / stats.total), note: 'of wear predictions' },
        no_ytp: { label: 'No estimate', value: fmtInt(stats.no_ytp), note: 'rating out of date' },
      }
    : null;
  const kpis = kpiDefs && prefs.showKpis ? prefs.kpis.map((k) => kpiDefs[k]) : [];

  // ---- panel sizes -------------------------------------------------------------------------
  // Dragging writes the size straight onto the frame; the choice is saved when the drag ends.
  const sizeVars = {
    ...(prefs.sideW != null ? { '--g-side-w': `${prefs.sideW}px` } : {}),
    ...(prefs.bottomH != null ? { '--g-bottom-h': `${prefs.bottomH}px` } : {}),
  } as React.CSSProperties;
  const sideLimits = (): [number, number] => [MIN_SIDE_W, (midRef.current?.clientWidth ?? 0) - MIN_MAP_W];
  const bottomLimits = (): [number, number] => [
    MIN_BOTTOM_H,
    (mainRef.current?.clientHeight ?? 0) - (topRef.current?.offsetHeight ?? 0) - MIN_MAP_H,
  ];
  // The tallest the bottom panel can go, kept in state so the maximise button knows which way it points.
  const [bottomMax, setBottomMax] = useState(0);
  useEffect(() => {
    const main = mainRef.current;
    const top = topRef.current;
    if (!main || !top) return;
    const measure = () => setBottomMax(main.clientHeight - top.offsetHeight - MIN_MAP_H);
    const ro = new ResizeObserver(measure);
    ro.observe(main);
    ro.observe(top);
    measure();
    return () => ro.disconnect();
  }, []);
  const bottomMaxed = prefs.bottomH != null && bottomMax > 0 && prefs.bottomH >= bottomMax - 4;

  return (
    <div className={`g-root ${prefs.density === 'compact' ? 'g-compact' : ''}`}>
      <nav className="g-rail" aria-label="Sections">
        <div className="g-logo" title="Unwatched Roads">
          UR
        </div>
        {rail.map((r) => (
          <button key={r.key} type="button" className={r.on ? 'on' : ''} title={r.label} aria-label={r.label} onClick={r.go}>
            {r.icon}
          </button>
        ))}
        <span className="g-rail-gap" />
        <button type="button" title={theme.dark ? 'Switch to light mode' : 'Switch to dark mode'} aria-label={theme.dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={theme.toggle}>
          {theme.dark ? <Sun size={20} /> : <Moon size={20} />}
        </button>
        <DisplayMenu prefs={prefs} onPrefs={setPrefs} onReset={resetPrefs} theme={theme.pref} onTheme={theme.setPref} />
        <a href={`${import.meta.env.BASE_URL}dashboard`} title="Executive view (/dashboard)" aria-label="Executive view (/dashboard)">
          <LayoutDashboard size={20} />
        </a>
        <a href={`${import.meta.env.BASE_URL}m`} title="Phone view for judges (/m)" aria-label="Phone view for judges (/m)">
          <Smartphone size={20} />
        </a>
      </nav>

      <main className="g-main" ref={mainRef} style={sizeVars}>
        <header className="g-top" ref={topRef}>
          <div className="g-title">
            <h1>Unwatched Roads</h1>
            <p>Agency dashboard · state-maintained roads only · model predictions, not inspections</p>
          </div>
          <div className="g-kpis">
            {kpis.map((k) => (
              <div key={k.label} className={`g-kpi ${k.tone ?? ''}`}>
                <span className="g-kpi-v">{k.value}</span>
                <span className="g-kpi-l">{k.label}</span>
                <span className="g-kpi-n">{k.note}</span>
              </div>
            ))}
          </div>
        </header>

        <div className="g-mid" ref={midRef}>
          <section className="g-card g-mapcard">
            <div className="g-map" ref={wrapRef} onMouseDownCapture={onMouseDownCapture}>
              <MapLibreDeck ref={mapRef} layers={layers} initial={NC_VIEW} dark={theme.dark} onView={setView} getTooltip={getTooltip} onBackgroundClick={() => setSelection([])} pickingRadius={5} />
              {box && (
                <div
                  className="g-box"
                  style={{ left: Math.min(box.x0, box.x1), top: Math.min(box.y0, box.y1), width: Math.abs(box.x1 - box.x0), height: Math.abs(box.y1 - box.y0) }}
                />
              )}
            </div>

            <div className="g-map-top">
              <SearchBox
                inputRef={searchRef}
                routeActive={filters.route !== ''}
                onSearch={(q) => void onSearch(q)}
                message={search.message}
                choices={search.choices}
                onChoose={(code) => search.pending && void goSr(Number(search.pending), code)}
              />
              <CountySelect stats={stats} value={filters.county} onChange={(c) => setCounty(c)} />
              <FilterButton filters={filters} onChange={setFilters} mode={mode} />
              <LayerSwitch mode={mode} onMode={setMode} />
              <div className="g-map-chips">
                <FilterChips filters={filters} onChange={setFilters} stats={stats} />
              </div>
            </div>

            {prefs.showLegend && (
              <div className="g-map-legend">
                <Legend mode={mode} />
                <div className="legend-note">
                  <span className="g-swatch" style={{ background: 'rgb(29,78,216)' }} /> Blue outline: dispatched work order (demo)
                </div>
              </div>
            )}

            <div className="g-map-status">
              {error && <span className="g-status-err">Road data did not load ({error}). Retrying…</span>}
              {notice && !error && (
                <button type="button" className="g-chip g-chip-warn" onClick={() => setNotice(null)}>
                  {notice} <X size={12} />
                </button>
              )}
              {!error && road.pending > 0 && <span>Loading roads…</span>}
              {!error && road.pending === 0 && road.level === 'overview' && stats && (
                <span>Zoomed out: showing the {fmtInt(stats.files.overview_n)} highest-priority roads. Zoom in to load every road.</span>
              )}
              {selection.length > 1 && (
                <button type="button" className="g-chip" onClick={() => setSelection([])}>
                  {selection.length} selected <X size={12} />
                </button>
              )}
              {prefs.showHints && <span className="g-hint">Shift-drag to select several roads</span>}
            </div>

            {!prefs.sideOpen && (
              <button type="button" className="g-reopen-side" title="Show the side panel" aria-label="Show the side panel" onClick={() => setPrefs({ sideOpen: true })}>
                <PanelRightOpen size={16} />
              </button>
            )}
          </section>

          {prefs.sideOpen && (
            <Splitter
              axis="x"
              label="Resize the side panel"
              size={() => sideRef.current?.offsetWidth ?? 0}
              limits={sideLimits}
              onDrag={(px) => mainRef.current?.style.setProperty('--g-side-w', `${px}px`)}
              onCommit={(px) => setPrefs({ sideW: px })}
              onReset={() => setPrefs({ sideW: null })}
            />
          )}

          {prefs.sideOpen && (
          <aside className="g-card g-side" ref={sideRef}>
            <div className="g-side-tabs" role="tablist">
              {(
                [
                  ['road', 'Road'],
                  ['order', 'Work order'],
                  ['storm', 'Storm readiness'],
                  ['model', 'Model'],
                ] as [Side, string][]
              ).map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={side === k} className={side === k ? 'on' : ''} onClick={() => (k === 'storm' ? enterStorm() : setSide(k))}>
                  {label}
                </button>
              ))}
              <span className="g-tabs-gap" />
              <button type="button" className="g-tab-tool" title="Hide the side panel" aria-label="Hide the side panel" onClick={() => setPrefs({ sideOpen: false })}>
                <PanelRightClose size={15} />
              </button>
            </div>
            <div className="g-side-scroll">
              {side === 'road' && (
                <SegmentPanel
                  selection={selection}
                  detail={detail}
                  stats={stats}
                  orders={wo.orders}
                  target={openTarget ?? ''}
                  onTarget={setTarget}
                  onAdd={() => void addSegs(selection)}
                  onZoom={zoomTo}
                  busy={busy}
                />
              )}
              {side === 'order' && (
                <OrderPanel
                  order={activeOrder}
                  crews={wo.crews}
                  onZoomSeg={zoomTo}
                  onZoomOrder={(o) => {
                    const segs = o.segs.map(orderSegToSeg);
                    if (!segs.length) return;
                    const b = segs.reduce<Bounds>((acc, s) => [Math.min(acc[0], s.bbox[0]), Math.min(acc[1], s.bbox[1]), Math.max(acc[2], s.bbox[2]), Math.max(acc[3], s.bbox[3])], [180, 90, -180, -90]);
                    mapRef.current?.fitBounds(b, 80);
                  }}
                  onPrint={(o) => setPrint({ kind: 'order', order: o })}
                  onClose={() => {
                    setActiveOrderId(null);
                    setTarget('');
                  }}
                />
              )}
              {side === 'storm' && (
                <StormPanel
                  rows={storm?.rows ?? null}
                  n={stormN}
                  onN={setStormN}
                  stats={stats}
                  onPick={(r) => void pickRow(r, true)}
                  onAdd={(rows) => void addRows(rows)}
                  onPrint={(rows) => setPrint({ kind: 'storm', rows })}
                  busy={busy}
                />
              )}
              {side === 'model' && <TransparencyPanel stats={stats} />}
            </div>
          </aside>
          )}
        </div>

        {prefs.bottomOpen ? (
          <Splitter
            axis="y"
            label="Resize the bottom panel"
            size={() => bottomRef.current?.offsetHeight ?? 0}
            limits={bottomLimits}
            onDrag={(px) => mainRef.current?.style.setProperty('--g-bottom-h', `${px}px`)}
            onCommit={(px) => setPrefs({ bottomH: px })}
            onReset={() => setPrefs({ bottomH: null })}
          />
        ) : (
          <div className="g-split-gap" />
        )}

        <section className={`g-card g-bottom ${prefs.bottomOpen ? '' : 'g-bottom-closed'}`} ref={bottomRef}>
          <div className="g-bottom-tabs" role="tablist">
            {(
              [
                ['queue', 'Work queue'],
                ['orders', `Work orders (${wo.orders.length})`],
                ['alerts', 'Alerts'],
              ] as [Bottom, string][]
            ).map(([k, label]) => (
              <button key={k} type="button" role="tab" aria-selected={bottom === k} className={bottom === k ? 'on' : ''} onClick={() => setBottom(k)}>
                {label}
              </button>
            ))}
            <span className="g-tabs-gap" />
            {prefs.bottomOpen && (
              <button
                type="button"
                className="g-tab-tool"
                title={bottomMaxed ? 'Restore the bottom panel' : 'Make the bottom panel as tall as it goes'}
                aria-label={bottomMaxed ? 'Restore the bottom panel' : 'Make the bottom panel as tall as it goes'}
                onClick={() => setPrefs({ bottomH: bottomMaxed ? null : Math.max(MIN_BOTTOM_H, bottomMax) })}
              >
                {bottomMaxed ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              </button>
            )}
            <button
              type="button"
              className="g-tab-tool"
              title={prefs.bottomOpen ? 'Hide the bottom panel' : 'Show the bottom panel'}
              aria-label={prefs.bottomOpen ? 'Hide the bottom panel' : 'Show the bottom panel'}
              aria-expanded={prefs.bottomOpen}
              onClick={() => setPrefs({ bottomOpen: !prefs.bottomOpen })}
            >
              {prefs.bottomOpen ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
            </button>
          </div>
          {prefs.bottomOpen && (
          <div className="g-bottom-body">
            {bottom === 'queue' && (
              <WorkQueue
                rows={queue.rows}
                scope={{ county: queue.county, perTier: queue.perTier }}
                stats={stats}
                filters={filters}
                mode={mode}
                selectedId={selection.length === 1 ? selection[0].id : null}
                hiddenCols={prefs.hiddenCols}
                onPick={(r) => void pickRow(r)}
                onAdd={(rows) => void addRows(rows)}
                busy={busy}
              />
            )}
            {bottom === 'orders' && <WorkOrdersTable orders={wo.orders} crews={wo.crews} activeId={activeOrderId} onOpen={openOrder} />}
            {bottom === 'alerts' && (
              <AlertsPanel stats={stats} queueRows={queue.rows} stormRows={storm?.rows ?? null} stormMin={storm?.min ?? 0.5} county={filters.county} onPick={(r) => void pickRow(r)} />
            )}
          </div>
          )}
        </section>
      </main>

      {print?.kind === 'order' && <PrintOrder order={print.order} />}
      {print?.kind === 'storm' && <PrintStorm rows={print.rows} stats={stats} />}
    </div>
  );
}
