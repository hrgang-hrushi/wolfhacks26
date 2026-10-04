import { useMemo, useState } from 'react';
import { PRIORITY, countyName, fmtInt, fmtPct, fmtYtpShort, parseId, routeName, type Row, type Stats } from '../lib/data';
import { countAtLeast, countAtMost } from './filters';

type Kind = 'ytp' | 'crack' | 'flood';

/**
 * Alerts = roads currently over a threshold. There is one inspection per road and no
 * history, so nothing here says a road "crossed" a line this week, and there are no trends.
 */
export function AlertsPanel({
  stats,
  queueRows,
  stormRows,
  stormMin,
  county,
  onPick,
}: {
  stats: Stats | null;
  queueRows: Row[] | null;
  stormRows: Row[] | null;
  stormMin: number;
  county: string;
  onPick: (row: Row) => void;
}) {
  const T = PRIORITY.tiers;
  const [ytpMax, setYtpMax] = useState(T.fix_now.ytp_max);
  const [crackMin, setCrackMin] = useState(T.fix_now.crack_min);
  const [floodMin, setFloodMin] = useState(T.fix_now.flood_min);
  const [kind, setKind] = useState<Kind>('ytp');
  const floodFloor = Math.ceil(stormMin * 100) / 100;

  const lists = useMemo(() => {
    const q = queueRows ?? [];
    const inCounty = (r: Row) => !county || parseId(r.id).cty === county;
    return {
      ytp: q.filter((r) => r.ytp != null && r.ytp <= ytpMax).sort((a, b) => (a.ytp ?? 0) - (b.ytp ?? 0)),
      crack: q.filter((r) => r.crack >= crackMin).sort((a, b) => b.crack - a.crack),
      flood: (stormRows ?? []).filter((r) => (r.flood ?? 0) >= floodMin && inCounty(r)),
    };
  }, [queueRows, stormRows, ytpMax, crackMin, floodMin, county]);

  if (!stats) return <div className="g-empty">Loading…</div>;
  const counts = {
    ytp: countAtMost(stats.hist.ytp, ytpMax),
    crack: countAtLeast(stats.hist.crack, crackMin),
    flood: countAtLeast(stats.hist.flood_zone, floodMin),
  };
  const list = lists[kind];
  const cards: { kind: Kind; title: string; value: string; slider: React.ReactNode }[] = [
    {
      kind: 'ytp',
      title: 'Reaches Poor within',
      value: `${ytpMax} year${ytpMax === 1 ? '' : 's'}`,
      slider: <input type="range" min={0} max={T.within_five.ytp_max} step={0.5} value={ytpMax} onChange={(e) => setYtpMax(Number(e.target.value))} aria-label="Years to Poor threshold" />,
    },
    {
      kind: 'crack',
      title: 'Cracking probability at least',
      value: fmtPct(crackMin),
      slider: <input type="range" min={T.within_year.crack_min} max={0.9} step={0.05} value={crackMin} onChange={(e) => setCrackMin(Number(e.target.value))} aria-label="Cracking threshold" />,
    },
    {
      kind: 'flood',
      title: 'Flood score at least (Helene zone)',
      value: floodMin.toFixed(2),
      slider: <input type="range" min={floodFloor} max={0.9} step={0.01} value={floodMin} onChange={(e) => setFloodMin(Number(e.target.value))} aria-label="Flood score threshold" />,
    },
  ];

  return (
    <div className="g-alerts">
      <div className="g-alert-cards">
        {cards.map((c) => (
          <div key={c.kind} className={`g-alert-card ${kind === c.kind ? 'on' : ''}`} onClick={() => setKind(c.kind)} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && setKind(c.kind)}>
            <span className="g-k">
              {c.title} <strong>{c.value}</strong>
            </span>
            <span className="g-alert-n">{fmtInt(counts[c.kind])}</span>
            <span className="g-n">roads statewide, in the current data</span>
            <span onClick={(e) => e.stopPropagation()}>{c.slider}</span>
          </div>
        ))}
      </div>
      <div className="g-table-wrap">
        <table className="g-table">
          <thead>
            <tr>
              <th>Road</th>
              <th>County</th>
              <th>Milepost</th>
              <th className="g-num">Years to Poor</th>
              <th className="g-num">Cracking</th>
              <th className="g-num">Flood</th>
            </tr>
          </thead>
          <tbody>
            {list.slice(0, 200).map((r) => (
              <tr key={r.id} tabIndex={0} onClick={() => onPick(r)} onKeyDown={(e) => e.key === 'Enter' && onPick(r)}>
                <td>
                  <strong>{routeName(r.id)}</strong>
                </td>
                <td>{countyName(r.id, stats) ?? ''}</td>
                <td>{(r.bmp ?? parseId(r.id).mp).toFixed(2)}</td>
                <td className="g-num">{fmtYtpShort(r.ytp)}</td>
                <td className="g-num">{fmtPct(r.crack)}</td>
                <td className="g-num">{r.hz && r.flood != null ? r.flood.toFixed(2) : <span className="g-na">not assessed</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="g-empty-row">
          An alert means “over the threshold in the current data”. There is one inspection per road and no history, so nothing here says a
          road crossed a line this week, and there are no trend charts.{' '}
          {kind === 'flood'
            ? `Listing ${fmtInt(Math.min(list.length, 200))} from the ${fmtInt(stormRows?.length ?? 0)} highest flood scores${county ? ' in this county' : ''}.`
            : county
              ? `Listing ${fmtInt(Math.min(list.length, 200))} of ${fmtInt(list.length)} in ${stats.counties[county]?.name ?? ''} County. The big number above is statewide.`
              : `Listing ${fmtInt(Math.min(list.length, 200))} from the statewide work queue (the top ${fmtInt(stats.files.ranked_per_tier)} roads per tier). Pick a county for its full list.`}
        </p>
      </div>
    </div>
  );
}
