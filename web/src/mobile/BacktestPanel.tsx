import { countyName, routeName, type Backtest, type Row, type Stats } from '../lib/data';

/** "Model in action": the Helene backtest. Every number comes from backtest.json. */
export function BacktestPanel({
  bt,
  stats,
  revealed,
  running,
  onReveal,
  onReset,
  onPickRow,
}: {
  bt: Backtest | null;
  stats: Stats | null;
  revealed: number;
  running: boolean;
  onReveal: () => void;
  onReset: () => void;
  onPickRow: (row: Row) => void;
}) {
  if (!bt) return <p className="m-hint">Loading the backtest…</p>;
  const n = bt.rows.length;
  const damagedSoFar = bt.rows.slice(0, revealed).reduce((a, r) => a + (r.failed ? 1 : 0), 0);
  const done = revealed >= n;
  const started = revealed > 0 || running;

  return (
    <div className="m-bt">
      <p className="m-bt-pitch">We asked the model to rank roads for flood damage without ever seeing them.</p>

      {!started ? (
        <button type="button" className="m-primary m-reveal" onClick={onReveal}>
          Reveal what happened
        </button>
      ) : (
        <div className="m-counter" aria-live="polite">
          <div className="m-counter-num">
            <span>{damagedSoFar}</span> of {done ? n : revealed} damaged
          </div>
          {done ? (
            <div className="m-counter-sub">
              vs about <strong>{Math.round(bt.expected_by_chance)}</strong> expected by chance
            </div>
          ) : (
            <div className="m-counter-sub">checking each road against the damage records…</div>
          )}
          <div className="m-bar" aria-hidden="true">
            {bt.rows.map((r, i) => (
              <span key={r.id} className={i < revealed ? (r.failed ? 'bad' : 'ok') : ''} />
            ))}
          </div>
        </div>
      )}

      <p className="m-hint">
        The {n} pins are the roads it ranked riskiest out of {bt.zone_roads.toLocaleString()} in the Helene zone. Each score came from a model
        trained without that road or its neighbours.
      </p>

      {done && (
        <>
          <p className="m-hint">
            Red pins are roads the Helene damage records mark as damaged; grey pins are not. In the whole zone {bt.zone_damaged.toLocaleString()} of{' '}
            {bt.zone_roads.toLocaleString()} roads were damaged, which is why picking {n} at random would find about{' '}
            {Math.round(bt.expected_by_chance)}. One storm; another could behave differently.
          </p>
          <button type="button" className="m-chip" onClick={onReset}>
            Reset
          </button>
          <ol className="m-list m-bt-list">
            {bt.rows.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => onPickRow(r)}>
                  <span className={`m-dot ${r.failed ? 'bad' : 'ok'}`} />
                  <span className="m-card-compact-main">
                    <strong>#{r.rank}</strong> {routeName(r.id)}
                    <em> · {countyName(r.id, stats) ?? ''} · score {r.flood?.toFixed(2)}</em>
                  </span>
                  <span className="m-card-compact-val">{r.failed ? 'damaged' : 'not damaged'}</span>
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
