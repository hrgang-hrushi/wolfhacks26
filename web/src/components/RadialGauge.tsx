import type { FC } from 'react';

interface RadialGaugeProps {
  percentage: number;
  label: string;
  subValue: string;
  colorType: 'green' | 'yellow' | 'lime' | 'red';
}

export const RadialGauge: FC<RadialGaugeProps> = ({
  percentage,
  label,
  subValue,
  colorType
}) => {
  // Arc calculation: 220 degree arc from -200 deg to 20 deg
  const radius = 38;
  const strokeWidth = 5;
  const circumference = 2 * Math.PI * radius;
  // Arc spans 220 degrees out of 360 = 220/360 * circumference
  const arcLength = (220 / 360) * circumference;
  const strokeDashoffset = arcLength - (percentage / 100) * arcLength;

  const colorMap = {
    green: {
      gradientStart: '#84CC16',
      gradientEnd: '#22C55E',
      glow: 'rgba(34, 197, 94, 0.25)',
      tickColor: '#86EFAC'
    },
    yellow: {
      gradientStart: '#FDE047',
      gradientEnd: '#EAB308',
      glow: 'rgba(234, 179, 8, 0.25)',
      tickColor: '#FDE68A'
    },
    lime: {
      gradientStart: '#A3E635',
      gradientEnd: '#84CC16',
      glow: 'rgba(132, 204, 22, 0.25)',
      tickColor: '#BEF264'
    },
    red: {
      gradientStart: '#FCA5A5',
      gradientEnd: '#EF4444',
      glow: 'rgba(239, 68, 68, 0.25)',
      tickColor: '#FECACA'
    }
  };

  const config = colorMap[colorType];
  const gradientId = `gauge-gradient-${colorType}-${percentage}`;

  return (
    <div className="radial-gauge-item">
      <div className="radial-gauge-svg-wrap">
        <svg viewBox="0 0 100 85" className="radial-gauge-svg">
          <defs>
            <linearGradient id={gradientId} x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={config.gradientStart} />
              <stop offset="100%" stopColor={config.gradientEnd} />
            </linearGradient>
          </defs>

          {/* Background track arc */}
          <circle
            cx="50"
            cy="52"
            r={radius}
            fill="none"
            stroke="#F1F3F5"
            strokeWidth={strokeWidth}
            strokeDasharray={`${arcLength} ${circumference}`}
            strokeDashoffset="0"
            strokeLinecap="round"
            transform="rotate(160 50 52)"
          />

          {/* Dotted tick marks simulation */}
          <circle
            cx="50"
            cy="52"
            r={radius}
            fill="none"
            stroke="url(#tick-pattern)"
            strokeWidth={strokeWidth}
            opacity="0.3"
            transform="rotate(160 50 52)"
          />

          {/* Foreground active arc */}
          <circle
            cx="50"
            cy="52"
            r={radius}
            fill="none"
            stroke={`url(#${gradientId})`}
            strokeWidth={strokeWidth}
            strokeDasharray={`${arcLength} ${circumference}`}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            transform="rotate(160 50 52)"
            style={{ transition: 'stroke-dashoffset 0.8s ease' }}
          />

          {/* Centered percentage */}
          <text
            x="50"
            y="54"
            textAnchor="middle"
            dominantBaseline="middle"
            className="radial-gauge-number"
          >
            {percentage}%
          </text>
        </svg>
      </div>

      <div className="radial-gauge-labels">
        <span className="radial-gauge-title">{label}</span>
        <span className="radial-gauge-val">{subValue}</span>
      </div>
    </div>
  );
};
