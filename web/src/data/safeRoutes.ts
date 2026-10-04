import type { RouteCorridor } from '../types/safeRoute';

export const NC_SAFE_ROUTE_CORRIDORS: RouteCorridor[] = [
  {
    id: 'asheville-helene',
    name: 'Asheville Mountain Pass (Helene Corridor)',
    region: 'Western NC / Blue Ridge',
    badge: 'Helene Impact Zone',
    badgeColor: 'red',
    center: [-82.445, 35.602],
    zoom: 11.8,
    originName: 'Asheville River Arts District (US-25)',
    destinationName: 'Black Mountain / Swannanoa (I-40 East)',
    fastest: {
      id: 'fastest',
      label: 'Fastest Route (Google Maps Baseline)',
      tag: '19 min • 14.2 mi',
      travelTimeMinutes: 19,
      distanceMiles: 14.2,
      pciScore: 41,
      floodRiskPercent: 92,
      severePotholesCount: 8,
      criticalHazards: [
        'Swannanoa River Lowland Washout (92% flood failure hazard)',
        'Severe Sub-base Structural Collapses (8 axle-strike potholes)',
        'Erosion scouring along river embankment (impassable in rain)'
      ],
      summary: 'Direct route following Swannanoa River Rd (US-70). Completely submerged and obliterated during Hurricane Helene; remains structurally vulnerable.',
      geometry: [
        [-82.565, 35.585],
        [-82.551, 35.589],
        [-82.535, 35.592],
        [-82.518, 35.595],
        [-82.498, 35.599],
        [-82.475, 35.604],
        [-82.451, 35.607],
        [-82.430, 35.611],
        [-82.405, 35.614],
        [-82.378, 35.616],
        [-82.350, 35.617],
        [-82.321, 35.618]
      ]
    },
    safest: {
      id: 'safest',
      label: 'Safest Route (RoadSense AI Hazard-Penalized)',
      tag: '22 min • 16.5 mi (+3 min)',
      travelTimeMinutes: 22,
      distanceMiles: 16.5,
      pciScore: 89,
      floodRiskPercent: 0,
      severePotholesCount: 0,
      criticalHazards: [],
      summary: 'Elevated I-40 Ridge High Ground & Blue Ridge Parkway Pass. 100% immune to river floodplain surges with reinforced modern concrete roadbeds.',
      geometry: [
        [-82.565, 35.585],
        [-82.560, 35.568],
        [-82.542, 35.558],
        [-82.515, 35.552],
        [-82.485, 35.559],
        [-82.450, 35.572],
        [-82.420, 35.588],
        [-82.390, 35.602],
        [-82.360, 35.612],
        [-82.335, 35.616],
        [-82.321, 35.618]
      ]
    },
    hazardsAvoidedCount: {
      potholes: 8,
      floodZones: 2,
      roughPavementMiles: 7.4
    },
    hazards: [
      {
        name: 'Swannanoa River Low-Water Crossing',
        coordinate: [-82.475, 35.604],
        type: 'flood_washout',
        severity: 'critical',
        description: 'Historical Helene flood depth reached 14.8ft above roadway. Pavement bed eroded.'
      },
      {
        name: 'Azalea Rd Structural Collapse Pothole',
        coordinate: [-82.518, 35.595],
        type: 'severe_pothole',
        severity: 'high',
        description: '7-inch deep frost heave and water pocket cavity causing rim damage.'
      },
      {
        name: 'Grovestone Quarry Runoff Wash',
        coordinate: [-82.378, 35.616],
        type: 'structural_rutting',
        severity: 'high',
        description: 'Mud sedimentation and severe longitudinal crack depth > 45mm.'
      }
    ],
    aiRationale:
      'RoadSense AI penalizes the Google Maps default (US-70) due to 92% flood vulnerability along the Swannanoa riverbed and 8 unpatched severe potholes. Rerouting via the I-40 Ridge adds only 3 minutes to travel time while eliminating 100% of flood hazard and boosting Pavement Condition Index from 41 to 89.'
  },
  {
    id: 'raleigh-capital',
    name: 'Raleigh Capital Corridor (Crabtree Creek Lowland)',
    region: 'Central NC / Research Triangle',
    badge: 'Capital District',
    badgeColor: 'green',
    center: [-78.658, 35.807],
    zoom: 12.4,
    originName: 'NC State Centennial Campus (Fitts-Woolard Hall)',
    destinationName: 'North Hills / Midtown Raleigh (Six Forks Rd)',
    fastest: {
      id: 'fastest',
      label: 'Fastest Route (Google Maps Baseline)',
      tag: '14 min • 8.1 mi',
      travelTimeMinutes: 14,
      distanceMiles: 8.1,
      pciScore: 56,
      floodRiskPercent: 68,
      severePotholesCount: 4,
      criticalHazards: [
        'Crabtree Creek Flash Floodway (68% high water surge danger)',
        'Glenwood Ave Rutting & Pothole Clusters (4 tire-puncture risks)',
        'Storm drain backing during high-intensity cloudbursts'
      ],
      summary: 'Cuts directly through Glenwood Ave (US-70) and the Crabtree Creek floodplain. Known for rapid flash flood inundation and severe frost-thaw asphalt degradation.',
      geometry: [
        [-78.6748, 35.7725],
        [-78.6720, 35.7850],
        [-78.6650, 35.7980],
        [-78.6610, 35.8110],
        [-78.6570, 35.8230],
        [-78.6520, 35.8340],
        [-78.6410, 35.8420]
      ]
    },
    safest: {
      id: 'safest',
      label: 'Safest Route (RoadSense AI Hazard-Penalized)',
      tag: '16 min • 9.4 mi (+2 min)',
      travelTimeMinutes: 16,
      distanceMiles: 9.4,
      pciScore: 92,
      floodRiskPercent: 2,
      severePotholesCount: 0,
      criticalHazards: [],
      summary: 'Elevated I-440 Beltline High Flyover bypass. Completely elevates vehicle traffic 30ft above the Crabtree basin over smooth, freshly-laid asphalt.',
      geometry: [
        [-78.6748, 35.7725],
        [-78.6850, 35.7800],
        [-78.6920, 35.7950],
        [-78.6880, 35.8150],
        [-78.6750, 35.8310],
        [-78.6580, 35.8400],
        [-78.6410, 35.8420]
      ]
    },
    hazardsAvoidedCount: {
      potholes: 4,
      floodZones: 1,
      roughPavementMiles: 4.8
    },
    hazards: [
      {
        name: 'Crabtree Creek Lowland Dip',
        coordinate: [-78.6610, 35.8110],
        type: 'flood_washout',
        severity: 'high',
        description: 'Frequent 2-foot flash ponding during heavy rainstorms; traps low-clearance passenger cars.'
      },
      {
        name: 'Glenwood Commercial Corridor Potholes',
        coordinate: [-78.6650, 35.7980],
        type: 'severe_pothole',
        severity: 'high',
        description: 'Severe alligator cracking and deep wheel-path rutting with exposed aggregate.'
      }
    ],
    aiRationale:
      'RoadSense AI detects high vulnerability in the Crabtree Creek basin. By shifting the vehicle path to the I-440 elevated flyover, drivers avoid 4 severe potholes and 1 critical flood entrapment hazard for a minor 2-minute delta, raising road quality from 56 to 92 PCI.'
  },
  {
    id: 'outer-banks-coast',
    name: 'Outer Banks Coastal Corridor (NC 12 Dune Overwash)',
    region: 'Eastern NC / Cape Hatteras Coast',
    badge: 'Atlantic Surge Zone',
    badgeColor: 'blue',
    center: [-75.535, 35.773],
    zoom: 10.4,
    originName: 'Nags Head Beachfront (US-158)',
    destinationName: 'Rodanthe / Hatteras Island (NC-12 South)',
    fastest: {
      id: 'fastest',
      label: 'Fastest Route (Google Maps Baseline)',
      tag: '32 min • 25.1 mi',
      travelTimeMinutes: 32,
      distanceMiles: 25.1,
      pciScore: 48,
      floodRiskPercent: 84,
      severePotholesCount: 6,
      criticalHazards: [
        'Pea Island Ocean Dune Breach (84% ocean overwash hazard)',
        'Saltwater Ponding & Undermined Asphalt Shoulders',
        'Corrosive saltwater spray and deep sand rutting'
      ],
      summary: 'Traditional route along barrier island sand spits. At astronomical high tide or storm winds, the ocean breaches the barrier dunes, washing sand and saltwater directly over the roadway.',
      geometry: [
        [-75.602, 35.952],
        [-75.589, 35.910],
        [-75.578, 35.865],
        [-75.565, 35.815],
        [-75.548, 35.760],
        [-75.525, 35.700],
        [-75.495, 35.645],
        [-75.468, 35.594]
      ]
    },
    safest: {
      id: 'safest',
      label: 'Safest Route (RoadSense AI Hazard-Penalized)',
      tag: '35 min • 27.2 mi (+3 min)',
      travelTimeMinutes: 35,
      distanceMiles: 27.2,
      pciScore: 95,
      floodRiskPercent: 4,
      severePotholesCount: 0,
      criticalHazards: [],
      summary: 'Jug Handle Bridge Bypass & Reinforced High Elevation Causeway. Spans 15 feet over Pamlico Sound waters, fully bypassing the vulnerable S-Curves overwash hotspot.',
      geometry: [
        [-75.602, 35.952],
        [-75.592, 35.910],
        [-75.582, 35.865],
        [-75.572, 35.815],
        [-75.560, 35.760],
        [-75.545, 35.695],
        [-75.510, 35.635],
        [-75.480, 35.608],
        [-75.468, 35.594]
      ]
    },
    hazardsAvoidedCount: {
      potholes: 6,
      floodZones: 2,
      roughPavementMiles: 11.2
    },
    hazards: [
      {
        name: 'Pea Island S-Curves Breach Point',
        coordinate: [-75.525, 35.700],
        type: 'dune_breach',
        severity: 'critical',
        description: 'Frequent ocean surge breach deposits 18 inches of sand and saltwater onto lanes.'
      },
      {
        name: 'Oregon Inlet Shoulder Scour',
        coordinate: [-75.565, 35.815],
        type: 'structural_rutting',
        severity: 'high',
        description: 'Sub-base erosion from tidal current eddies along road shoulder.'
      }
    ],
    aiRationale:
      'RoadSense AI detects high-tide overwash risks along NC-12 barrier dunes. Directing drivers onto the Jug Handle Bridge structure avoids the notorious S-curves dune breach zone, ensuring 100% passability and protecting vehicle undercarriages from corrosive saltwater.'
  }
];
