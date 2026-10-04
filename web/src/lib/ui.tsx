/** Small pieces both dashboards share, so the honesty labels read the same everywhere. */
import { useState } from 'react';
import { fmtInt, legendFor, rgbCss, type Mode, type Stats } from './data';
import { CANNOT_CLAIM, DATA_SOURCES, HELDOUT_EXPLAIN, INSAMPLE_EXPLAIN } from './readme';

/** Held-out vs in-sample, for one prediction. Tappable: the explanation is not hover-only. */
export function HeldoutBadge({ heldout }: { heldout: boolean }) {
  const [open, setOpen] = useState(false);
  const text = heldout ? HELDOUT_EXPLAIN : INSAMPLE_EXPLAIN;
  return (
    <span className="ho-wrap">
      <button
        type="button"
        className={`badge ${heldout ? 'badge-ho' : 'badge-in'}`}
        title={text}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
      >
        {heldout ? 'Held-out' : 'In-sample'}
      </button>
      {open && <span className="ho-explain">{text}</span>}
    </span>
  );
}

export function Legend({ mode }: { mode: Mode }) {
  const spec = legendFor(mode);
  return (
    <div className="legend" aria-label={`Legend: ${spec.title}`}>
      <div className="legend-title">{spec.title}</div>
      <div className="legend-stops">
        {spec.stops.map((s) => (
          <div key={s.label} className="legend-stop">
            <span className="legend-swatch" style={{ background: rgbCss(s.rgb) }} />
            <span>{s.label}</span>
          </div>
        ))}
      </div>
      {spec.note && <div className="legend-note">{spec.note}</div>}
    </div>
  );
}

/** The README's three headline results, straight from stats.json. */
export function MetricsTable({ stats }: { stats: Stats }) {
  const m = stats.readme_metrics;
  const rows = [m.wear_mae, m.crack_aucpr, m.helene_top50];
  return (
    <div className="metrics">
      <table>
        <thead>
          <tr>
            <th>Measure</th>
            <th>No model</th>
            <th>Record + traffic</th>
            <th>+ shape of the land</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              <td>{i === 2 ? `about ${r.no_model}` : r.no_model}</td>
              <td>{r.baseline}</td>
              <td>
                <strong>{r.with_terrain}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="fine">
        Every number is measured on roads the model had not seen. “No model” means giving every road the same guess, or
        picking roads at random. Source: {m.source}.
      </p>
    </div>
  );
}

export function CannotClaim() {
  return (
    <ul className="cannot">
      {CANNOT_CLAIM.map((c) => (
        <li key={c.head}>
          <strong>{c.head}</strong> {c.body}
        </li>
      ))}
    </ul>
  );
}

export function Sources({ stats }: { stats: Stats }) {
  return (
    <>
      <ul className="sources">
        {DATA_SOURCES.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
      <p className="fine">
        {fmtInt(stats.total)} state road stretches. Held-out predictions: wear {fmtInt(stats.heldout.rate)}, cracking{' '}
        {fmtInt(stats.heldout.crack)}, flood {fmtInt(stats.heldout.flood)} (every road in the Helene zone). Data built{' '}
        {stats.generated.slice(0, 10)} from {stats.source}.
      </p>
    </>
  );
}
