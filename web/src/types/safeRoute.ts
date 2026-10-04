export interface RouteComparisonOption {
  id: 'fastest' | 'safest';
  label: string;
  tag: string;
  travelTimeMinutes: number;
  distanceMiles: number;
  pciScore: number; // 0 - 100 Pavement Condition Index
  floodRiskPercent: number; // 0 - 100%
  severePotholesCount: number;
  criticalHazards: string[];
  summary: string;
  geometry: [number, number][]; // [lng, lat][]
}

export interface HazardWaypoint {
  name: string;
  coordinate: [number, number];
  type: 'flood_washout' | 'severe_pothole' | 'structural_rutting' | 'dune_breach';
  severity: 'high' | 'critical';
  description: string;
}

export interface RouteCorridor {
  id: string;
  name: string;
  region: string;
  badge: string;
  badgeColor: 'red' | 'green' | 'yellow' | 'blue';
  center: [number, number]; // [lng, lat]
  zoom: number;
  originName: string;
  destinationName: string;
  fastest: RouteComparisonOption;
  safest: RouteComparisonOption;
  hazardsAvoidedCount: {
    potholes: number;
    floodZones: number;
    roughPavementMiles: number;
  };
  hazards: HazardWaypoint[];
  aiRationale: string;
}

export interface RoutePreviewState {
  corridor: RouteCorridor;
  selectedOption: 'fastest' | 'safest' | 'both';
}
