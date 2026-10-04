/**
 * The two /gov views that read the Tiger Data database: the flood watch (camera flags and
 * water-level alerts, from the database's hourly summaries) and the database panel (what the
 * database is holding and doing). Both appear only when the service exists on this deployment.
 */
import { useEffect, useState } from 'react';
import { Database, Download, RefreshCw } from 'lucide-react';
import { fmtInt, routeName } from '../lib/data';
import { fmtBytes, fmtUtc, tiger, type AlertsReply, type CameraAlert, type PeakHour, type SensorAlert, type TigerState, type TigerStats } from '../lib/tiger';

const REFRESH_MS = 15_000;

function TigerNotReady({ state }: { state: TigerState }) {
  if (state.kind === 'loading')
    return <div className="g-empty">The database is loading new data ({state.status}). This view fills in when the load finishes.</div>;
  if (state.kind === 'down') return <div className="g-empty">The database did not answer ({state.reason}). Trying again shortly.</div>;
  return <div className="g-empty">Connecting to the database…</div>;
}

const pct = (v: number | null) => (v == null ? '' : `${Math.round(v * 100)}%`);
const cm = (v: number | null) => (v == null ? '' : `${v.toFixed(1)} cm`);

/** Camera flags and sensor alerts for one window of time: the latest readings, or a recorded hour. */
export function FloodWatch({
  state,
  onAlerts,
  onPickCamera,
  onPickSensor,
}: {
  state: TigerState;
  /** The alerts on screen, so the map can pin them. null when there are none to show. */
  onAlerts: (reply: AlertsReply | null) => void;
  onPickCamera: (a: CameraAlert) => void;
  onPickSensor: (a: SensorAlert) => void;
}) {
  const ready = state.kind === 'ready';
  /** null follows the newest reading; a time opens that recorded hour. */
  const [asOf, setAsOf] = useState<string | null>(null);
  const [reply, setReply] = useState<AlertsReply | null>(null);
  const [peaks, setPeaks] = useState<PeakHour[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!ready) return;
    const abort = new AbortController();
    tiger
      .peaks(abort.signal)
      .then((p) => setPeaks(p.hours))
      .catch(() => undefined);
    return () => abort.abort();
  }, [ready]);

  useEffect(() => {
    if (!ready) return;
    const abort = new AbortController();
    tiger
      .alerts(asOf, asOf ? 1 : 2, abort.signal)
      .then((r) => {
        setReply(r);
        setError(null);
        onAlerts(r);
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'the request failed');
      });
    // Following the newest reading: ask again every few seconds, so a storm replay shows up as it arrives.
    const timer = asOf ? 0 : window.setTimeout(() => setTick((t) => t + 1), REFRESH_MS);
    return () => {
      abort.abort();
      window.clearTimeout(timer);
    };
  }, [ready, asOf, tick, onAlerts]);

  useEffect(() => () => onAlerts(null), [onAlerts]);

  if (!ready) return <TigerNotReady state={state} />;

  const cams = reply?.camera_alerts ?? [];
  const real = cams.filter((c) => !c.known_dry);
  const dry = cams.filter((c) => c.known_dry);
  const sensors = reply?.sensor_alerts ?? [];
  const anyReplay = cams.some((c) => c.replay) || sensors.some((s) => s.replay);

  return (
    <div className="g-alerts g-watch">
      <div className="g-alert-cards">
        <div className={`g-alert-card ${asOf == null ? 'on' : ''}`} role="button" tabIndex={0} onClick={() => setAsOf(null)} onKeyDown={(e) => e.key === 'Enter' && setAsOf(null)}>
          <span className="g-k">Newest readings</span>
          <span className="g-alert-n">{asOf == null && reply ? real.length + sensors.length : ''}</span>
          <span className="g-n">the last two hours of data, refreshed every {REFRESH_MS / 1000} seconds</span>
        </div>
        {peaks && peaks.length > 0 && <span className="g-k g-watch-head">Busiest recorded hours</span>}
        {(peaks ?? []).map((p) => (
          <div key={p.hour} className={`g-alert-card ${asOf === p.as_of ? 'on' : ''}`} role="button" tabIndex={0} onClick={() => setAsOf(p.as_of)} onKeyDown={(e) => e.key === 'Enter' && setAsOf(p.as_of)}>
            <span className="g-k">{fmtUtc(p.hour)}</span>
            <span className="g-alert-n">{p.camera_flags + p.sensor_alerts}</span>
            <span className="g-n">
              {p.camera_flags} camera flag{p.camera_flags === 1 ? '' : 's'}, {p.sensor_alerts} sensor alert{p.sensor_alerts === 1 ? '' : 's'}
              {p.known_dry_flags > 0 && `, ${p.known_dry_flags} known false alarm${p.known_dry_flags === 1 ? '' : 's'}`}
            </span>
          </div>
        ))}
      </div>

      <div className="g-table-wrap">
        <p className="g-empty-row g-watch-status">
          <span className={`badge ${reply?.live ? 'badge-ho' : 'badge-in'}`}>{reply?.live ? 'Live' : 'Recorded'}</span>
          {anyReplay && <span className="badge badge-demo" title="Rows copied from the recorded storm with their times shifted to now. Each keeps its original time.">Storm replay</span>}
          {reply?.as_of ? (
            <span>
              Readings from {fmtUtc(reply.window_start)} to {fmtUtc(reply.as_of)}.
            </span>
          ) : (
            <span>{error ? `The alerts did not load (${error}).` : 'Loading…'}</span>
          )}
          <button type="button" className="g-btn g-watch-refresh" onClick={() => setTick((t) => t + 1)} title="Ask the database again">
            <RefreshCw size={13} /> Refresh
          </button>
        </p>

        <table className="g-table">
          <thead>
            <tr>
              <th>Camera</th>
              <th className="g-num">Flood probability</th>
              <th className="g-num">Depth, predicted</th>
              <th className="g-num">Depth, measured</th>
              <th>Worst reading</th>
              <th>Nearest state road</th>
            </tr>
          </thead>
          <tbody>
            {[...real, ...dry].map((a) => (
              <tr key={`${a.camera_id}-${a.replay}`} className={a.known_dry ? 'g-row-muted' : ''} tabIndex={0} onClick={() => onPickCamera(a)} onKeyDown={(e) => e.key === 'Enter' && onPickCamera(a)} title={a.note ?? undefined}>
                <td>
                  <strong>{a.name ?? a.camera_id}</strong>
                  {a.known_dry && <span className="badge badge-in g-badge-s">known false alarm</span>}
                  {a.replay && <span className="badge badge-demo g-badge-s">replay</span>}
                </td>
                <td className="g-num">{pct(a.worst.p_flooded)}</td>
                <td className="g-num">{cm(a.worst.depth_pred_cm)}</td>
                <td className="g-num">{a.worst.depth_measured_cm != null ? cm(a.worst.depth_measured_cm) : <span className="g-na">no gauge</span>}</td>
                <td>{fmtUtc(a.replay ? a.replay_of : a.worst.time)}</td>
                <td>{a.road ? `${routeName(a.road.seg_id)}${a.road.county ? `, ${a.road.county} County` : ''}` : <span className="g-na">none matched</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {reply && cams.length === 0 && <p className="g-empty-row">No camera is flagged in this window.</p>}

        {sensors.length > 0 && (
          <table className="g-table g-watch-sensors">
            <thead>
              <tr>
                <th>Water-level station</th>
                <th className="g-num">Depth on the road</th>
                <th className="g-num">Water level</th>
                <th>Worst reading</th>
                <th className="g-num">Latest depth</th>
              </tr>
            </thead>
            <tbody>
              {sensors.map((s) => (
                <tr key={`${s.station}-${s.replay}`} tabIndex={0} onClick={() => onPickSensor(s)} onKeyDown={(e) => e.key === 'Enter' && onPickSensor(s)} title={s.note}>
                  <td>
                    <strong>{s.name ?? s.station}</strong>
                    {s.replay && <span className="badge badge-demo g-badge-s">replay</span>}
                  </td>
                  <td className="g-num">{cm(s.worst.depth_on_road_cm)}</td>
                  <td className="g-num">{s.worst.level_m != null ? `${s.worst.level_m.toFixed(2)} m` : ''}</td>
                  <td>{fmtUtc(s.replay ? s.replay_of : s.worst.time)}</td>
                  <td className="g-num">{cm(s.latest.depth_on_road_cm)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {reply && (
          <p className="g-empty-row">
            {reply.caveat} A camera is flagged at a flood probability of {pct(reply.flag_at)} or more; a station alerts when the water is {reply.flooded_cm} cm or more above the road. Each
            row shows the worst reading of the window, kept by the database as an hourly summary.
          </p>
        )}
      </div>
    </div>
  );
}

const TABLE_LABEL: Record<string, string> = {
  camera_readings: 'Camera flood readings',
  sensor_levels: 'Water-level readings',
  pothole_reports: 'Pothole reports',
  camera_hourly: 'Cameras, by hour',
  sensor_hourly: 'Stations, by hour',
  pothole_monthly: 'Pothole reports, by month',
  roads: 'Roads',
  road_shapes: 'Road shapes',
  cameras: 'Cameras',
};

/** What the database holds and what it is doing: rows, time chunks, compression, running summaries. */
export function DatabasePanel({ state }: { state: TigerState }) {
  const usable = state.kind === 'ready' || state.kind === 'loading';
  const [stats, setStats] = useState<TigerStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!usable) return;
    const abort = new AbortController();
    tiger
      .stats(abort.signal)
      .then((s) => {
        setStats(s);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'the request failed');
      });
    return () => abort.abort();
  }, [usable]);

  if (!usable) return <TigerNotReady state={state} />;
  if (!stats) return <div className="g-empty">{error ? `The database figures did not load (${error}).` : 'Reading the database…'}</div>;

  const hyper = Object.entries(stats.time_partitioned_tables);
  const before = hyper.reduce((a, [, t]) => a + (t.bytes_before ?? 0), 0);
  const after = hyper.reduce((a, [, t]) => a + (t.bytes_after ?? 0), 0);

  return (
    <div className="g-panel-body">
      <h2>
        <Database size={17} /> Database
      </h2>
      <p className="g-sub">
        The road forecasts and the time-stamped readings live in one Tiger Data database
        {stats.timescaledb_version && ` (TimescaleDB ${stats.timescaledb_version}`}
        {stats.postgres_version && ` on PostgreSQL ${stats.postgres_version.split(' ')[0]})`}. {fmtBytes(stats.database_size_bytes)} in all.
        {stats.load?.finished_at && ` Last load finished ${fmtUtc(stats.load.finished_at)}.`}
      </p>

      <div className="g-facts">
        <div>
          <span className="g-k">Roads</span>
          <span className="g-v">{fmtInt(stats.plain_tables.roads ?? 0)}</span>
          <span className="g-n">one row per state road stretch</span>
        </div>
        <div>
          <span className="g-k">Compression</span>
          <span className="g-v">{before && after ? `${(before / after).toFixed(2)}×` : '–'}</span>
          <span className="g-n">{before && after ? `${fmtBytes(before)} down to ${fmtBytes(after)} in the old time chunks` : 'no chunk is old enough to compress yet'}</span>
        </div>
      </div>

      <h3>Time-stamped tables</h3>
      <div className="metrics">
        <table>
          <thead>
            <tr>
              <th>Table</th>
              <th>Rows</th>
              <th>Chunks (compressed)</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody>
            {hyper.map(([name, t]) => (
              <tr key={name}>
                <td>
                  {TABLE_LABEL[name] ?? name}
                  <div className="g-n g-mono">{name}</div>
                </td>
                <td>{fmtInt(t.rows)}</td>
                <td>
                  {t.chunks} ({t.compressed_chunks}), one per {t.chunk_interval.replace(/^1 /, '')}
                </td>
                <td>{t.bytes_before != null && t.bytes_after != null ? `${fmtBytes(t.bytes_before)} → ${fmtBytes(t.bytes_after)}${t.compression_ratio ? ` (${t.compression_ratio}×)` : ''}` : '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="fine">Each table is split into chunks by time, and a chunk is compressed once it is old.</p>
      </div>

      <h3>Running summaries</h3>
      <div className="metrics">
        <table>
          <thead>
            <tr>
              <th>Summary</th>
              <th>Rows</th>
              <th>Kept from</th>
              <th>Newest rows</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(stats.running_summaries).map(([name, s]) => (
              <tr key={name}>
                <td>
                  {TABLE_LABEL[name] ?? name}
                  <div className="g-n g-mono">{name}</div>
                </td>
                <td>{fmtInt(s.rows)}</td>
                <td className="g-mono">{s.over}</td>
                <td>{s.includes_rows_newer_than_last_refresh ? 'included' : 'after the next refresh'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="fine">
          The database keeps these up to date itself (continuous aggregates). The flood watch reads them, so an alert is one small query, not a scan of every reading.
          {stats.background_jobs.length > 0 && ` ${stats.background_jobs.length} background jobs refresh and compress on a schedule.`}
          {stats.replay_rows > 0 && ` ${fmtInt(stats.replay_rows)} rows are a labelled storm replay.`}
        </p>
      </div>

      <h3>Risk file for map companies</h3>
      <p className="g-text">One row per road with its forecast, its held-out flags and where it is. Served straight from the database.</p>
      <div className="g-actions">
        <a className="g-btn" href={tiger.riskCsvUrl}>
          <Download size={14} /> Risk file (CSV, about 20 MB)
        </a>
        <a className="g-btn" href={tiger.dictionaryUrl} target="_blank" rel="noreferrer">
          What each column means
        </a>
      </div>
    </div>
  );
}
