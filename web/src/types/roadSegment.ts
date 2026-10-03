export type RoadSource = 'ncdot' | 'city';

export interface RoadSegment {
  // Required schema fields matching real production predictions drops
  seg_id: string;
  source: RoadSource;
  pv_rating: number; // Pavement rating (e.g., 0 - 100)
  pv_age: number; // Pavement age in years
  years_to_poor: number; // Predicted years until reaching 'Poor' threshold
  flood_rank: string | number; // Flood vulnerability ranking or FEMA tier
  drivers: [string, string, string]; // Top 3 explanatory degradation factors
  chip_url: string; // Aerial / satellite image chip URL or placeholder

  // Geometry and visualization properties for deck.gl PathLayer
  path: [number, number][]; // [[lng, lat], [lng, lat], ...]
  score: number; // Score from 0 to 1 used for PathLayer color mapping
  
  // Helpful metadata for display and navigation
  name: string;
  city: 'Raleigh' | 'Asheville';
}

export type ViewFilter = 'all' | 'ncdot'; // 'what we predict' (all) vs 'what the state surveys' (ncdot)
