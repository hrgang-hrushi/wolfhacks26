import { PRIORITY, TIERS, fmtInt, rgbCss, type Stats } from '../lib/data';
import { SCOPE_NOTE } from '../lib/readme';
import { CannotClaim, MetricsTable, Sources } from '../lib/ui';

export function AboutSheet({
  stats,
  engine,
  fallbackReason,
}: {
  stats: Stats | null;
  engine: 'google' | 'maplibre';
  fallbackReason: string | null;
}) {
  if (!stats) return <p className="m-hint">Loading…</p>;
  const m = stats.readme_metrics;
  return (
    <div className="m-about-body">
      <p>
        We learn from the roads the state inspects what age, traffic and the shape of the land do to pavement, then score every state road.{' '}
        {SCOPE_NOTE}
      </p>

      <div className="m-headlines">
        <div>
          <strong>{m.wear_mae.with_terrain}</strong>
          <span>typical miss in wear, rating points a year, vs {m.wear_mae.no_model} with no model</span>
        </div>
        <div>
          <strong>{m.crack_aucpr.with_terrain}</strong>
          <span>cracking ranking score, vs {m.crack_aucpr.no_model} by chance</span>
        </div>
        <div>
          <strong>
            {m.helene_top50.with_terrain} of 50
          </strong>
          <span>riskiest Helene-zone roads were damaged, vs about {m.helene_top50.no_model} by chance</span>
        </div>
      </div>

      <h3>The full table</h3>
      <MetricsTable stats={stats} />

      <h3>What we cannot claim</h3>
      <CannotClaim />

      <h3>Repair tiers</h3>
      <ul className="m-tiers">
        {TIERS.map((t) => (
          <li key={t.key}>
            <span className="m-dot" style={{ background: rgbCss(t.rgb) }} />
            <span>
              <strong>{t.label}</strong> ({fmtInt(stats.tiers[t.key])} roads). {t.rule}.
            </span>
          </li>
        ))}
      </ul>
      <p className="fine">
        The tiers are our own thresholds, not NCDOT policy. Poor means a rating below {PRIORITY.poor_rating}.
      </p>

      <h3>Data</h3>
      <Sources stats={stats} />
      <p className="fine">
        Basemap: {engine === 'google' ? 'Google Maps' : `MapLibre with a Carto basemap${fallbackReason ? ` (${fallbackReason})` : ''}`}.
      </p>

      <h3>Other views</h3>
      <p style={{ display: 'flex', gap: '16px', marginTop: '6px' }}>
        <a href="/gov" style={{ color: '#2563eb', fontWeight: 600 }}>Agency Dashboard (/gov) &rarr;</a>
        <a href="/dashboard" style={{ color: '#2563eb', fontWeight: 600 }}>Executive View (/dashboard) &rarr;</a>
      </p>
    </div>
  );
}
