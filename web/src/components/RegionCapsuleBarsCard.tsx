import type { FC } from 'react';
import { ArrowUpRight } from 'lucide-react';

interface RegionData {
  region: string;
  fillCount: number; // 0 to 12 segments filled
}

const REGION_DATA: RegionData[] = [
  { region: 'East', fillCount: 4 },
  { region: 'West', fillCount: 7 },
  { region: 'Central', fillCount: 11 },
  { region: 'South', fillCount: 4 },
  { region: 'North', fillCount: 8 }
];

export const RegionCapsuleBarsCard: FC = () => {
  const totalSegments = 12;

  // Segment colors from bottom to top
  const getSegmentColor = (idx: number) => {
    if (idx < 3) return '#F87171'; // Coral Red
    if (idx < 6) return '#FBBF24'; // Amber Yellow
    if (idx < 9) return '#A3E635'; // Lime
    return '#84CC16'; // Vivid Green
  };

  return (
    <div className="analytics-card capsule-bars-card">
      <div className="card-top-header">
        <h3 className="card-heading">Sales by regions</h3>
        <button type="button" className="card-arrow-btn" aria-label="Expand regional breakdown">
          <ArrowUpRight size={14} />
        </button>
      </div>

      <div className="capsule-chart-body">
        {/* Y Axis Guide */}
        <div className="chart-y-axis">
          <span>300k</span>
          <span>200k</span>
          <span>100k</span>
          <span>0</span>
        </div>

        {/* 5 Vertical Capsule Columns */}
        <div className="capsules-columns-wrap">
          {REGION_DATA.map((item) => (
            <div key={item.region} className="capsule-col-group">
              <div className="capsule-pill-track">
                {/* 12 horizontal stacked pill bars, top to bottom */}
                {Array.from({ length: totalSegments }).map((_, i) => {
                  const segmentIndexFromBottom = totalSegments - 1 - i;
                  const isFilled = segmentIndexFromBottom < item.fillCount;
                  const color = isFilled ? getSegmentColor(segmentIndexFromBottom) : '#F1F3F5';

                  return (
                    <div
                      key={i}
                      className="capsule-single-pill"
                      style={{
                        backgroundColor: color,
                        opacity: isFilled ? 1 : 0.6
                      }}
                    />
                  );
                })}
              </div>

              {/* Region Label */}
              <span className="capsule-col-label">{item.region}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
