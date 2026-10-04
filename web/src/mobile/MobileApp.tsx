/**
 * Dashboard B: the judge dashboard (/m). Phone first, one hand, bad wifi.
 *
 * Google Maps when a key and Map ID are configured, MapLibre otherwise or on any
 * failure. Both draw the same deck.gl layers.
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Layer } from '@deck.gl/core';
import { Building2, Info, LocateFixed, Moon, Sun, X } from 'lucide-react';
import {
  cellsForBounds,
  distanceToSeg,
  findSeg,
  loadBacktest,
  loadShard,
  rowToSeg,
  type Backtest,
  type Mode,
  type RGBA,
  type Row,
  type Seg,
} from '../lib/data';
import { pinLayer, roadLayers, selectionLayers, widthScaleForZoom, type Pin } from '../lib/layers';
import { boundsFor, googleConfigured, NC_BOUNDS, PLACES, type MapHandle, type MapView } from '../lib/mapTypes';
import { useDetail, useMediaQuery } from '../lib/hooks';
import { useTheme } from '../lib/prefs';
import { Legend } from '../lib/ui';
import { useRoadData, useStats } from '../lib/useRoadData';
import { AboutSheet } from './AboutSheet';
import { BacktestPanel } from './BacktestPanel';
import { BottomSheet, type Snap } from './BottomSheet';
import { FeaturedCard, SegCard } from './SegCard';
import { DEMO, PHONE_MAX_SHARDS, START } from './start';
import './mobile.css';

const MapLibreDeck = lazy(() => import('../lib/MapLibreDeck'));
const GoogleDeck = lazy(() => import('../lib/GoogleDeck'));

type Tab = 'condition' | 'flood' | 'action';
type ActionMode = 'backtest' | 'near';

interface NearState {
  status: 'idle' | 'locating' | 'ok' | 'outside' | 'denied';
  items: { seg: Seg; metres: number }[];
}

const TABS: { key: Tab; label: string }[] = [
  { key: 'condition', label: 'Condition' },
  { key: 'flood', label: 'Flood' },
  { key: 'action', label: 'Model in action' },
];

const REVEAL_STEP_MS = 70;
const PIN_WAITING: RGBA = [245, 158, 11, 255];
const PIN_DAMAGED: RGBA = [220, 38, 38, 255];
const PIN_OK: RGBA = [148, 163, 184, 235];
const PIN_ME: RGBA = [37, 99, 235, 255];

function inNC(lng: number, lat: number): boolean {
  return lng >= NC_BOUNDS[0] && lng <= NC_BOUNDS[2] && lat >= NC_BOUNDS[1] && lat <= NC_BOUNDS[3];
}

export default function MobileApp() {
  const { stats, error } = useStats();
  // Light unless the visitor switches; the choice is shared with /gov and kept in this browser.
  const { dark, toggle: toggleTheme } = useTheme();
  const narrow = useMediaQuery('(max-width: 600px)');
  const mapRef = useRef<MapHandle>(null);

  const [engine, setEngine] = useState<'google' | 'maplibre'>(googleConfigured ? 'google' : 'maplibre');
  const [fallbackReason, setFallbackReason] = useState<string | null>(
    googleConfigured ? null : 'no Google Maps key configured',
  );
  const [mapError, setMapError] = useState<string | null>(null);

  const [tab, setTab] = useState<Tab>(DEMO ? 'action' : 'condition');
  const [action, setAction] = useState<ActionMode>('backtest');
  const [snap, setSnap] = useState<Snap>(DEMO ? 'half' : 'peek');
  const [aboutOpen, setAboutOpen] = useState(false);

  const [view, setView] = useState<MapView>(() => ({
    bounds: boundsFor(START.lng, START.lat, START.zoom, window.innerWidth, window.innerHeight),
    zoom: START.zoom,
  }));
  const road = useRoadData(stats, view, narrow ? PHONE_MAX_SHARDS : 30);

  const [selected, setSelected] = useState<Seg | null>(null);
  const [featuredOpen, setFeaturedOpen] = useState(false);
  const detail = useDetail(selected, stats);

  const [bt, setBt] = useState<Backtest | null>(null);
  const [revealed, setRevealed] = useState(0);
  const [revealing, setRevealing] = useState(false);

  const [loc, setLoc] = useState<[number, number] | null>(null);
  const [locNote, setLocNote] = useState<string | null>(null);
  const [near, setNear] = useState<NearState>({ status: 'idle', items: [] });

  const mode: Mode = tab === 'condition' ? 'ytp' : 'flood';
  const showBacktest = tab === 'action' && action === 'backtest';

  // ---- map callbacks -------------------------------------------------------
  const pick = useCallback((seg: Seg) => {
    setSelected(seg);
    setFeaturedOpen(false);
    setSnap((s) => (s === 'peek' ? 'half' : s));
  }, []);

  const onFail = useCallback((reason: string) => {
    setEngine((e) => {
      if (e === 'google') {
        setFallbackReason(reason);
        return 'maplibre';
      }
      setMapError(reason);
      return e;
    });
  }, []);

  // ---- backtest ------------------------------------------------------------
  useEffect(() => {
    if (tab !== 'action' || bt || !stats?.backtest) return;
    let live = true;
    loadBacktest()
      .then((b) => live && setBt(b))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [tab, bt, stats]);

  const fitBacktest = useCallback(() => {
    if (!bt) return;
    let w = 180;
    let s = 90;
    let e = -180;
    let n = -90;
    for (const r of bt.rows) {
      w = Math.min(w, r.c[0]);
      e = Math.max(e, r.c[0]);
      s = Math.min(s, r.c[1]);
      n = Math.max(n, r.c[1]);
    }
    mapRef.current?.fitBounds([w, s, e, n], { top: 96, left: 28, right: 28, bottom: Math.round(window.innerHeight * 0.5) + 16 });
  }, [bt]);

  useEffect(() => {
    if (showBacktest && bt) {
      const t = window.setTimeout(fitBacktest, 250); // let the map finish mounting
      return () => window.clearTimeout(t);
    }
  }, [showBacktest, bt, fitBacktest]);

  const running = revealing && bt != null && revealed < bt.rows.length;
  useEffect(() => {
    if (!running) return;
    const t = window.setTimeout(() => setRevealed((r) => r + 1), REVEAL_STEP_MS);
    return () => window.clearTimeout(t);
  }, [running, revealed]);

  const btPins = useMemo<(Pin & { row: Row })[]>(() => {
    if (!bt) return [];
    return bt.rows.map((row, i) => {
      const shown = i < revealed;
      return {
        id: row.id,
        c: row.c,
        row,
        color: !shown ? PIN_WAITING : row.failed ? PIN_DAMAGED : PIN_OK,
        radius: shown && row.failed ? 11 : 8,
      };
    });
  }, [bt, revealed]);

  const pickRow = useCallback((row: Row) => {
    const seg = rowToSeg(row);
    if (!seg) return;
    setSelected(seg);
    setFeaturedOpen(false);
    setSnap('half');
    mapRef.current?.flyTo(row.c[0], row.c[1], 12.5);
  }, []);

  // ---- tabs ------------------------------------------------------------------
  const changeTab = useCallback(
    (next: Tab) => {
      setTab(next);
      setFeaturedOpen(false);
      if (next === 'action') setSnap('half');
      if (next === 'flood') {
        // Flood is scored only in the Helene zone; go there if none of it is on screen.
        const anyZone = road.shards.some((sh) => sh.segs.some((s) => s.hz === 1));
        if (!anyZone) mapRef.current?.flyTo(PLACES.Asheville.lng, PLACES.Asheville.lat, PLACES.Asheville.zoom);
      }
    },
    [road.shards],
  );

  // ---- location ----------------------------------------------------------------
  const locate = useCallback(
    (thenRank: boolean) => {
      if (!('geolocation' in navigator)) {
        setNear({ status: 'denied', items: [] });
        if (!thenRank) setLocNote('This browser does not share a location.');
        return;
      }
      setLocNote(null);
      if (thenRank) setNear({ status: 'locating', items: [] });
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const lng = pos.coords.longitude;
          const lat = pos.coords.latitude;
          setLoc([lng, lat]);
          if (!inNC(lng, lat) || !stats) {
            if (thenRank) setNear({ status: 'outside', items: [] });
            else if (stats) setLocNote('You are outside North Carolina, so there are no scored roads near you.');
            return;
          }
          mapRef.current?.flyTo(lng, lat, 12.5);
          if (!thenRank) return;
          const cells = cellsForBounds([lng - 0.04, lat - 0.04, lng + 0.04, lat + 0.04], stats, 0);
          const shards = await Promise.all(cells.map((c) => loadShard(c).catch(() => null)));
          const items = shards
            .flatMap((sh) => sh?.segs ?? [])
            .map((seg) => ({ seg, metres: distanceToSeg(lng, lat, seg) }))
            .sort((a, b) => a.metres - b.metres)
            .slice(0, 5)
            .sort((a, b) => (a.seg.ytp ?? Infinity) - (b.seg.ytp ?? Infinity));
          setNear(items.length ? { status: 'ok', items } : { status: 'outside', items: [] });
        },
        () => {
          if (thenRank) setNear({ status: 'denied', items: [] });
          else setLocNote('Location is off or took too long. Allow it in the browser to use this button.');
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 60_000 },
      );
    },
    [stats],
  );

  useEffect(() => {
    if (!locNote) return;
    const t = window.setTimeout(() => setLocNote(null), 7000);
    return () => window.clearTimeout(t);
  }, [locNote]);

  const jump = useCallback((name: keyof typeof PLACES) => {
    const p = PLACES[name];
    mapRef.current?.flyTo(p.lng, p.lat, p.zoom);
    setTab('condition');
    setSnap('peek');
  }, []);

  // ---- featured example ----------------------------------------------------------
  const openFeatured = useCallback(async () => {
    const f = stats?.featured;
    if (!f || !stats) return;
    setTab('condition');
    setFeaturedOpen(true);
    setSnap('half');
    mapRef.current?.flyTo(f.c[0], f.c[1], 12.8);
    const seg = await findSeg(f.id, f.c, stats).catch(() => null);
    if (seg) setSelected(seg);
  }, [stats]);

  // ---- layers ------------------------------------------------------------------
  const widthScale = widthScaleForZoom(view.zoom) * 1.15; // a touch thicker for fingers
  const layers = useMemo<Layer[]>(() => {
    const out: Layer[] = roadLayers({ shards: road.shards, mode, onPick: pick, dim: showBacktest, widthScale });
    if (selected) out.push(...selectionLayers('sel', [selected], mode, dark));
    if (showBacktest && btPins.length) out.push(pinLayer('bt', btPins, (p) => pickRow(p.row), dark));
    if (loc) out.push(pinLayer('me', [{ id: 'me', c: loc, color: PIN_ME, radius: 7 }], undefined, dark));
    return out;
    // `engine` is listed on purpose: a deck.gl layer cannot move to another map, so a fallback needs fresh ones.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [road.shards, mode, pick, showBacktest, selected, dark, btPins, pickRow, loc, engine, widthScale]);

  const mapProps = {
    layers,
    initial: START,
    dark,
    pickingRadius: 14,
    onView: setView,
    onBackgroundClick: () => setSelected(null),
    onFail,
  };

  const sheetHeader = (
    <div className="m-seg" role="tablist" aria-label="Map view">
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={tab === t.key}
          className={tab === t.key ? 'on' : ''}
          onClick={() => changeTab(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );

  const selectedRow = selected && bt ? bt.rows.findIndex((r) => r.id === selected.id) : -1;

  return (
    <div className={`m-root ${dark ? 'dark' : ''}`}>
      <div className="m-map">
        <Suspense fallback={null}>
          {engine === 'google' ? <GoogleDeck ref={mapRef} {...mapProps} /> : <MapLibreDeck ref={mapRef} {...mapProps} />}
        </Suspense>
      </div>

      <header className="m-top">
        <div className="m-top-brand">
          <img src="/assets/reference/logo.webp" alt="RoadSense AI" className="m-brand-logo-img" />
          <div className="m-top-text">
            <div className="m-title-row">
              <h1 className="m-brand-title">RoadSense AI</h1>
              <span className="m-scope-badge">NCDOT Statewide</span>
            </div>
            <p className="m-brand-subtitle">State Highway Pavement &amp; Flood Intelligence</p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
          <a
            href={`${import.meta.env.BASE_URL}gov`}
            className="m-icon-btn"
            title="Desktop agency dashboard (/gov)"
            aria-label="Agency dashboard"
          >
            <Building2 size={18} />
          </a>
          <button type="button" className="m-icon-btn" aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} title={dark ? 'Light mode' : 'Dark mode'} onClick={toggleTheme}>
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button type="button" className="m-icon-btn" aria-label="About this model" onClick={() => setAboutOpen(true)}>
            <Info size={18} />
          </button>
        </div>
      </header>

      {(error || mapError) && (
        <div className="m-toast m-toast-error" role="alert">
          {error ? `Road data did not load (${error}). Retrying…` : `The map did not start (${mapError}).`}
        </div>
      )}
      {!error && !mapError && locNote && (
        <div className="m-toast m-toast-error" role="alert" onClick={() => setLocNote(null)}>
          {locNote}
        </div>
      )}
      {!error && !locNote && road.pending > 0 && <div className="m-toast">Loading roads…</div>}
      {!error && !locNote && road.pending === 0 && road.level === 'overview' && !showBacktest && (
        <div className="m-toast">Showing the {stats ? stats.files.overview_n.toLocaleString() : ''} highest-priority roads. Zoom in for every road.</div>
      )}

      <button type="button" className="m-fab" aria-label="Go to my location" onClick={() => locate(false)}>
        <LocateFixed size={20} />
      </button>

      <BottomSheet snap={snap} onSnap={setSnap} header={sheetHeader}>
        {tab === 'condition' && (
          <>
            <Legend mode="ytp" />
            {stats?.featured && !featuredOpen && (
              <button type="button" className="m-chip" onClick={openFeatured}>
                Featured example: SR 2748, Wake County
              </button>
            )}
            {featuredOpen && stats?.featured && <FeaturedCard featured={stats.featured} onClose={() => setFeaturedOpen(false)} />}
            {selected && !featuredOpen && <SegCard seg={selected} detail={detail} stats={stats} />}
            {!selected && !featuredOpen && <p className="m-hint">Tap a road to see when it is predicted to reach Poor.</p>}
          </>
        )}

        {tab === 'flood' && (
          <>
            <Legend mode="flood" />
            <p className="m-hint">
              Flood risk is scored only where Hurricane Helene hit (western NC). Everywhere else it is{' '}
              <strong>not assessed</strong>, which is not the same as low risk.
            </p>
            <button type="button" className="m-chip" onClick={() => mapRef.current?.flyTo(PLACES.Asheville.lng, PLACES.Asheville.lat, PLACES.Asheville.zoom)}>
              Go to the Helene zone
            </button>
            {selected && <SegCard seg={selected} detail={detail} stats={stats} />}
          </>
        )}

        {tab === 'action' && (
          <>
            <div className="m-subseg" role="tablist" aria-label="Demo">
              <button type="button" role="tab" aria-selected={action === 'backtest'} className={action === 'backtest' ? 'on' : ''} onClick={() => setAction('backtest')}>
                Helene backtest
              </button>
              <button type="button" role="tab" aria-selected={action === 'near'} className={action === 'near' ? 'on' : ''} onClick={() => setAction('near')}>
                Near me
              </button>
            </div>

            {action === 'backtest' &&
              (stats && !stats.backtest ? (
                <p className="m-hint">The Helene outcome file was not available when this site was built, so the backtest is not shown.</p>
              ) : (
                <BacktestPanel
                  bt={bt}
                  stats={stats}
                  revealed={revealed}
                  running={running}
                  onReveal={() => {
                    setSelected(null);
                    fitBacktest();
                    setRevealed(0);
                    setRevealing(true);
                  }}
                  onReset={() => {
                    setRevealing(false);
                    setRevealed(0);
                  }}
                  onPickRow={pickRow}
                />
              ))}
            {action === 'backtest' && selected && selectedRow >= 0 && (
              <SegCard
                seg={selected}
                detail={detail}
                stats={stats}
                outcome={selectedRow < revealed ? (bt?.rows[selectedRow].failed ? 'damaged' : 'not damaged') : 'hidden'}
              />
            )}

            {action === 'near' && (
              <div className="m-near">
                <p className="m-hint">Finds the five scored state roads closest to you and lists them soonest-to-Poor first. Your location stays on this phone.</p>
                <button type="button" className="m-primary" onClick={() => locate(true)} disabled={near.status === 'locating'}>
                  {near.status === 'locating' ? 'Finding you…' : 'Rank the roads near me'}
                </button>
                {(near.status === 'outside' || near.status === 'denied') && (
                  <>
                    <p className="m-hint">
                      {near.status === 'outside'
                        ? 'You are outside North Carolina, or no scored road is close by.'
                        : 'Location is off or was not allowed.'}{' '}
                      Jump to a city instead:
                    </p>
                    <div className="m-row">
                      {(['Raleigh', 'Asheville', 'Wilmington'] as const).map((p) => (
                        <button key={p} type="button" className="m-chip" onClick={() => jump(p)}>
                          {p}
                        </button>
                      ))}
                    </div>
                  </>
                )}
                {near.status === 'ok' && (
                  <ol className="m-list">
                    {near.items.map(({ seg, metres }) => (
                      <li key={seg.id}>
                        <button type="button" onClick={() => pick(seg)}>
                          <SegCard seg={seg} detail={null} stats={stats} compact distance={metres} />
                        </button>
                      </li>
                    ))}
                  </ol>
                )}
                {selected && near.status === 'ok' && <SegCard seg={selected} detail={detail} stats={stats} />}
              </div>
            )}
          </>
        )}
      </BottomSheet>

      {aboutOpen && (
        <div className="m-about" role="dialog" aria-modal="true" aria-label="About this model">
          <div className="m-about-head">
            <h2>About this model</h2>
            <button type="button" className="m-icon-btn" aria-label="Close" onClick={() => setAboutOpen(false)}>
              <X size={20} />
            </button>
          </div>
          <AboutSheet stats={stats} engine={engine} fallbackReason={fallbackReason} />
        </div>
      )}
    </div>
  );
}
