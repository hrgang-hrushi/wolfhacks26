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
    center: [-78.565, 35.625],
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
    zoom: 11.5,
    pitch: 35,
    bearing: 0
  },
  Greensboro: {
    center: [-79.7919, 36.0726],
    zoom: 11.5,
    pitch: 35,
    bearing: 0
  },
  Wilmington: {
    center: [-77.9447, 34.2257],
    zoom: 11.5,
    pitch: 35,
    bearing: 0
  }
};
