// Real North Carolina Road Segments from LightGBM + 3DEP + Helene Pipeline
// Source: handoff/predictions_geo.parquet (112,443 total segments statewide)
import type { RoadSegment } from '../types/roadSegment';
import { realRoadName } from '../utils/roadFacts';
import rawRoads from './realRoads.json';

export interface StatewideMetadata {
  total_nc_segments: number;
  helene_zone_segments: number;
  statewide_avg_rate: number;
  statewide_avg_years_to_poor: number;
  high_crack_count: number;
  high_flood_count: number;
}

export const NC_STATEWIDE_METRICS: StatewideMetadata = {
  total_nc_segments: 112443,
  helene_zone_segments: 32558,
  statewide_avg_rate: 1.34,
  statewide_avg_years_to_poor: 23.5,
  high_crack_count: 39901,
  high_flood_count: 1209
};

// The sample file carries placeholder street names. The road's own route, county and milepost replace them.
export const REAL_NC_ROAD_SEGMENTS: RoadSegment[] = (rawRoads as unknown as RoadSegment[]).map((s) => ({
  ...s,
  name: realRoadName(s.seg_id) ?? s.name,
  flood_rank: !s.in_helene_zone
    ? 'Not scored (outside the Helene zone)'
    : (s.pred_flood ?? 0) >= 0.5
      ? 'High flood score (Helene zone)'
      : 'Lower flood score (Helene zone)',
  drivers: ['Pavement record (age, last treatment)', 'Traffic volume', 'Shape of the land (slope, drainage)'],
}));
