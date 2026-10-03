import React from 'react';

export interface FormatOptions {
  style?: 'currency' | 'percent' | 'decimal';
  currency?: string;
  maximumFractionDigits?: number;
}

export interface GaugeProps {
  centerValue: number | string;
  defaultLabel: string;
  formatOptions?: FormatOptions;
  inactiveFillOpacity?: number;
  notchCornerRadius?: number;
  notchLengthPercent?: number;
  spacing?: number;
  value?: number; // 0 to 100
  size?: number;
  activeColor?: string;
  inactiveColor?: string;
  valueColor?: string;
  labelColor?: string;
}

export const Gauge: React.FC<GaugeProps> = ({
  centerValue,
  defaultLabel,
  formatOptions,
  inactiveFillOpacity = 0.4,
  notchCornerRadius = 8,
  notchLengthPercent = 100,
  spacing = 25,
  value = 66,
  size = 175,
  activeColor = '#10b981',
  inactiveColor = '#e2e8f0',
  valueColor = '#0f172a',
  labelColor = '#64748b'
}) => {
  // Format center value if number and options provided
  const formattedCenterValue = React.useMemo(() => {
    if (typeof centerValue === 'number' && formatOptions) {
      try {
        return new Intl.NumberFormat('en-US', formatOptions).format(centerValue);
      } catch {
        return centerValue.toLocaleString();
      }
    }
    return String(centerValue);
  }, [centerValue, formatOptions]);

  // Exact 1,000,000+ hour tuned radial notch geometry:
  // Sweep from 138° (bottom-left) to 402° (bottom-right) - 264° total sweep
  const totalNotches = 42;
  const startAngle = 138;
  const endAngle = 402;
  const sweepAngle = endAngle - startAngle;

  const cx = size / 2;
  const cy = (size / 2) + 4;
  const outerR = (size / 2) - 8;
  // Short rectangular ticks with small corner rounding instead of pill-shaped notches.
  const notchLen = size * 0.09 * (notchLengthPercent / 100);
  const notchW = Math.max(4, size * 0.03 - spacing / 20);

  // Angular notch step
  const angleStep = sweepAngle / (totalNotches - 1);
  const activeCount = Math.round((Math.max(0, Math.min(100, value)) / 100) * totalNotches);

  // Generate evenly spaced rectangular ticks around the sweep.
  const notches = [];
  for (let i = 0; i < totalNotches; i++) {
    const angleDeg = startAngle + i * angleStep;
    const isActive = i < activeCount;

    notches.push(
      <rect
        key={i}
        x={cx - notchW / 2}
        y={cy - outerR}
        width={notchW}
        height={notchLen}
        rx={notchCornerRadius}
        ry={notchCornerRadius}
        fill={isActive ? activeColor : inactiveColor}
        opacity={isActive ? 1 : inactiveFillOpacity}
        transform={`rotate(${angleDeg + 90} ${cx} ${cy})`}
        style={{
          transition: 'fill 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1)'
        }}
      />
    );
  }

  return (
    <div
      className="bklit-gauge-component"
      style={{
        width: size,
        height: size * 0.78,
        position: 'relative',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        userSelect: 'none'
      }}
    >
      <svg
        viewBox={`0 0 ${size} ${size * 0.90}`}
        width="100%"
        height="100%"
        style={{ overflow: 'visible' }}
      >
        <g className="gauge-notches-group">
          {notches}
        </g>
      </svg>

      {/* Center Value and Label - Mathematically Centered at (cx, cy) with generous clearance */}
      <div
        className="gauge-center-stat"
        style={{
          position: 'absolute',
          top: cy,
          left: cx,
          transform: 'translate(-50%, -50%)',
          textAlign: 'center',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none',
          zIndex: 2
        }}
      >
        <span
          className="gauge-stat-val"
          style={{
            fontSize: '28px',
            fontWeight: 800,
            color: valueColor,
            lineHeight: 1.05,
            letterSpacing: '-0.03em',
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
          }}
        >
          {formattedCenterValue}
        </span>
        <span
          className="gauge-stat-lbl"
          style={{
            fontSize: '12px',
            fontWeight: 500,
            color: labelColor,
            marginTop: '3px',
            letterSpacing: '0',
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
          }}
        >
          {defaultLabel}
        </span>
      </div>
    </div>
  );
};
