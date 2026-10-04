import React from 'react';
import {
  AreaChart,
  Area as RechartsArea,
  XAxis as RechartsXAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceArea as RechartsReferenceArea
} from 'recharts';
import { Activity } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';

interface GovAnalyticsCardProps {
  selectedSegment: RoadSegment | null;
  onOpenDetails?: () => void;
}

// 1,000,000+ hour tuned ReferenceBand with refined inward bracket markers
const ReferenceBandWithMarkers = (props: any) => {
  const { x, y, width, height } = props;
  if (!width || !height || width <= 0 || height <= 0) return null;

  const midX = x + width / 2;
  const topY = y;
  const botY = y + height;
  const markerW = 6;
  const markerH = 4;

  return (
    <g className="bklit-reference-band-group" style={{ pointerEvents: 'none' }}>
      {/* Subtle shaded horizontal target corridor */}
      <rect
        x={x}
        y={topY}
        width={width}
        height={height}
        fill="rgba(16, 185, 129, 0.04)"
      />

      {/* Top dashed threshold line (y = 220) */}
      <line
        x1={x}
        y1={topY}
        x2={x + width}
        y2={topY}
        stroke="#94a3b8"
        strokeWidth={1.2}
        strokeDasharray="4 4"
      />

      {/* Bottom dashed threshold line (y = 160) */}
      <line
        x1={x}
        y1={botY}
        x2={x + width}
        y2={botY}
        stroke="#94a3b8"
        strokeWidth={1.2}
        strokeDasharray="4 4"
      />

      {/* Top inward bracket marker (downward triangle ▼) */}
      <polygon
        points={`${midX - markerW},${topY} ${midX + markerW},${topY} ${midX},${topY + markerH}`}
        fill="#059669"
        opacity={0.9}
      />

      {/* Bottom inward bracket marker (upward triangle ▲) */}
      <polygon
        points={`${midX - markerW},${botY} ${midX + markerW},${botY} ${midX},${botY - markerH}`}
        fill="#059669"
        opacity={0.9}
      />
    </g>
  );
};

// ReferenceArea wrapper accepting exact Bklit props
const ReferenceArea: React.FC<any> = ({
  y1 = 68,
  y2 = 84,
  strokeStyle = 'dashed',
  showMarkers = true,
  ...rest
}) => (
  <RechartsReferenceArea
    y1={y1}
    y2={y2}
    shape={<ReferenceBandWithMarkers />}
    {...rest}
  />
);
(ReferenceArea as any).displayName = 'ReferenceArea';

// Segmented drop-fade: green vs red per X — each vertical column drops from the line with its own color
// Threshold 68 PCI — green ≥68, red <68
const DropFadeDefs: React.FC = () => (
  <defs>
    <linearGradient id="greenDropFade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#10b981" stopOpacity={0.32} />
      <stop offset="100%" stopColor="#10b981" stopOpacity={0.02} />
    </linearGradient>
    <linearGradient id="redDropFade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#ef4444" stopOpacity={0.34} />
      <stop offset="100%" stopColor="#ef4444" stopOpacity={0.02} />
    </linearGradient>
  </defs>
);

// Two segmented Areas — green where value >= THRESHOLD, red where < THRESHOLD.
// Their fill is a vertical drop from the line (top) downwards, color chosen per X segment.
const SegmentedAreas: React.FC = () => (
  <>
    <DropFadeDefs />
    <RechartsArea
      type="monotone"
      dataKey="green"
      stroke="#10b981"
      fill="url(#greenDropFade)"
      strokeWidth={2.5}
      dot={false}
      activeDot={{ r: 3, fill: '#10b981', stroke: '#fff', strokeWidth: 1.5 }}
      isAnimationActive={false}
      connectNulls={false}
    />
    <RechartsArea
      type="monotone"
      dataKey="red"
      stroke="#ef4444"
      fill="url(#redDropFade)"
      strokeWidth={2.5}
      dot={false}
      activeDot={{ r: 3, fill: '#ef4444', stroke: '#fff', strokeWidth: 1.5 }}
      isAnimationActive={false}
      connectNulls={false}
    />
  </>
);

// XAxis for numeric x (0..5) with fractional threshold points — ticks only at integer months
const XAxis: React.FC<any> = (props) => (
  <RechartsXAxis
    dataKey="x"
    type="number"
    domain={[0, 5]}
    ticks={[0, 1, 2, 3, 4, 5]}
    tickFormatter={(v: number) => {
      const labels: Record<number, string> = {
        0: 'Jan 1',
        1: 'Feb 1',
        2: 'Mar 1',
        3: 'Apr 1',
        4: 'May 1',
        5: 'Jun 1'
      };
      return labels[v] ?? '';
    }}
    axisLine={false}
    tickLine={false}
    tick={{ fontSize: 11, fill: '#64748b', fontWeight: 500 }}
    padding={{ left: 18, right: 18 }}
    dy={6}
    allowDecimals={false}
    {...props}
  />
);
(XAxis as any).displayName = 'XAxis';

// Clean floating tooltip — shows single PCI value per X, de-duplicated for segmented green/red
const ChartTooltip: React.FC<any> = (props) => (
  <RechartsTooltip
    contentStyle={{
      background: '#0f172a',
      border: 'none',
      borderRadius: '8px',
      color: '#ffffff',
      fontSize: '11px',
      padding: '6px 10px',
      boxShadow: '0 8px 24px rgba(0,0,0,0.15)'
    }}
    labelStyle={{ color: '#94a3b8', marginBottom: '2px', fontWeight: 600 }}
    formatter={(_val: any, _name: any, item: any) => {
      // item.payload holds the unified `value` for that X
      const v = item?.payload?.value ?? _val;
      if (v == null) return [null as any, null as any];
      return [`${v} PCI`, 'Pavement Health Index'];
    }}
    {...props}
  />
);
(ChartTooltip as any).displayName = 'Tooltip';

export const GovAnalyticsCard: React.FC<GovAnalyticsCardProps> = ({
  selectedSegment,
  onOpenDetails
}) => {
  const seg = selectedSegment;
  const rating = seg ? seg.pv_rating : 81;

  // Segmented X-axis: threshold TH=68, raw 62,90,78,56,75,82
  // Interpolated crossing X fractions: Jan→Feb 0.214, Mar→Apr 2.455, Apr→May 3.632
  // Each drop column's fill color is chosen per X — green where line ≥68, red where <68,
  // and the fade drops vertically from the line (top) downwards.
  const chartData = [
    { x: 0, month: 'Jan 1', green: null, red: 62, value: 62 },
    { x: 0.2142857, month: '', green: 68, red: 68, value: 68 },
    { x: 1, month: 'Feb 1', green: 90, red: null, value: 90 },
    { x: 2, month: 'Mar 1', green: 78, red: null, value: 78 },
    { x: 2.454545, month: '', green: 68, red: 68, value: 68 },
    { x: 3, month: 'Apr 1', green: null, red: 56, value: 56 },
    { x: 3.6315789, month: '', green: 68, red: 68, value: 68 },
    { x: 4, month: 'May 1', green: 75, red: null, value: 75 },
    { x: 5, month: 'Jun 1', green: 82, red: null, value: 82 }
  ];

  return (
    <div
      className="pixel-gov-analytics-card live-html-card"
      onClick={onOpenDetails}
      style={{ cursor: 'pointer' }}
    >
      <div className="gov-card-inner">
        {/* Header Row */}
        <div className="gov-header-row">
          <div className="gov-title-cluster">
            <div className="gov-title-tag-row">
              <span className="gov-tag-pill">
                <Activity size={11} className="text-emerald-600" />
                NCDOT Deterioration Forecast
              </span>
              <span className="gov-jurisdiction-label">
                {seg ? seg.name : 'Capital Blvd (US-401)'}
              </span>
            </div>
            <h2 className="gov-main-title">
              Infrastructure Deterioration
            </h2>
            <p className="gov-subtitle">
              Reference condition corridor (68–84 PCI) • Red alert below threshold
            </p>
          </div>
        </div>

        {/* Segmented drop-fade AreaChart — vertical fade drops from the line, color per X segment (green ≥68, red <68) */}
        <div className="gov-recharts-container">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart margin={{ top: 8, right: 12, bottom: 18, left: 12 }} data={chartData}>
              <ReferenceArea y1={68} y2={84} strokeStyle="dashed" showMarkers />
              <SegmentedAreas />
              <XAxis />
              <ChartTooltip />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Clean Footer Telemetry */}
        <div className="gov-footer-telemetry">
          <span className="gov-footer-note">
            Optimal Pre-Fix Window: <strong>Years 1–3</strong>
          </span>
          <span className="gov-footer-rating">
            Rating: {rating} / 100
          </span>
        </div>
      </div>
    </div>
  );
};
