// Built-in fallback public token for client-side raster/vector tiles
const getFallbackToken = (): string => {
  try {
    return typeof atob !== 'undefined'
      ? atob('cGsuZXlKMUlqb2lhSEoxYzJocFozSWlMQ0poSWpvaVkyMTFjM05tTXpSbU1UQnVZVEozYjJvMk5tYzJNelZsWnlKOS5Bdk5BWENJVDBYaU9rZDM2VTAyZVp3')
      : '';
  } catch {
    return '';
  }
};

export const DEFAULT_MAPBOX_TOKEN = getFallbackToken();

export const MAPBOX_TOKEN = 
  import.meta.env.VITE_MAPBOX_TOKEN || DEFAULT_MAPBOX_TOKEN;

// Free open-source vector basemap fallbacks (Carto Positron & Dark Matter - no token required)
export const CARTO_LIGHT_STYLE = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';
export const CARTO_DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
export const CARTO_VOYAGER_STYLE = 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json';

export type MapboxStyleKey = 'light' | 'streets' | 'satellite' | 'dark' | 'outdoors';

export const MAPBOX_STYLES: Record<MapboxStyleKey, { label: string; url: string; fallbackUrl: string; icon: string }> = {
  light: {
    label: 'Clean Light',
    url: 'mapbox://styles/mapbox/light-v11',
    fallbackUrl: CARTO_LIGHT_STYLE,
    icon: 'Sun'
  },
  streets: {
    label: 'Streets v12',
    url: 'mapbox://styles/mapbox/streets-v12',
    fallbackUrl: CARTO_VOYAGER_STYLE,
    icon: 'Map'
  },
  satellite: {
    label: 'Satellite HD',
    url: 'mapbox://styles/mapbox/satellite-streets-v12',
    fallbackUrl: CARTO_DARK_STYLE,
    icon: 'Globe'
  },
  dark: {
    label: 'Dark Matter',
    url: 'mapbox://styles/mapbox/dark-v11',
    fallbackUrl: CARTO_DARK_STYLE,
    icon: 'Moon'
  },
  outdoors: {
    label: 'Terrain / Topo',
    url: 'mapbox://styles/mapbox/outdoors-v12',
    fallbackUrl: CARTO_LIGHT_STYLE,
    icon: 'Compass'
  }
};

export const NC_CITY_COORDINATES: Record<string, { center: [number, number]; zoom: number; pitch: number; bearing: number }> = {
  Raleigh: {
    center: [-78.6382, 35.7796],
    zoom: 12.0,
    pitch: 35,
    bearing: -10
  },
  Asheville: {
    center: [-82.553, 35.610],
    zoom: 11.5,
    pitch: 40,
    bearing: 15
  },
  Statewide: {
    center: [-79.8, 35.5],
    zoom: 7.1,
    pitch: 0,
    bearing: 0
  },
  Charlotte: {
    center: [-80.8431, 35.2271],
    zoom: 11.8,
    pitch: 35,
    bearing: 0
  },
  Greensboro: {
    center: [-79.7919, 36.0726],
    zoom: 11.8,
    pitch: 35,
    bearing: 0
  },
  'Winston-Salem': {
    center: [-80.2442, 36.0999],
    zoom: 11.8,
    pitch: 35,
    bearing: 0
  },
  Wilmington: {
    center: [-77.9447, 34.2257],
    zoom: 11.8,
    pitch: 35,
    bearing: 0
  },
  Fayetteville: {
    center: [-78.8784, 35.0526],
    zoom: 11.8,
    pitch: 35,
    bearing: 0
  },
  Boone: {
    center: [-81.6748, 36.2168],
    zoom: 12.0,
    pitch: 35,
    bearing: 10
  },
  'Outer Banks': {
    center: [-75.62, 35.95],
    zoom: 10.0,
    pitch: 20,
    bearing: 0
  },
  // Regional Coordinates
  Mountains: {
    center: [-82.6, 35.55],
    zoom: 9.0,
    pitch: 30,
    bearing: 10
  },
  Piedmont: {
    center: [-79.5, 35.8],
    zoom: 8.8,
    pitch: 25,
    bearing: -5
  },
  Coastal: {
    center: [-77.2, 35.2],
    zoom: 8.5,
    pitch: 15,
    bearing: 0
  },
  // NCDOT Division Groupings
  'Div 1 & 3': {
    center: [-77.3, 34.8],
    zoom: 8.7,
    pitch: 15,
    bearing: 0
  },
  'Div 5 & 7': {
    center: [-79.1, 35.9],
    zoom: 9.2,
    pitch: 25,
    bearing: 0
  },
  'Div 10 & 12': {
    center: [-80.8, 35.3],
    zoom: 9.0,
    pitch: 25,
    bearing: 0
  },
  'Div 13 & 14': {
    center: [-82.6, 35.6],
    zoom: 9.0,
    pitch: 35,
    bearing: 10
  }
};

