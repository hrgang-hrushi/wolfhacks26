export interface WeatherData {
  temp: number;
  feelsLike: number;
  condition: string;
  description: string;
  icon: string;
  humidity: number;
  windSpeed: number;
  rain1h?: number;
  cityName: string;
  timestamp: number;
}

const WEATHER_API_KEY =
  import.meta.env.VITE_OPENWEATHER_API_KEY || '';

// 5-minute TTL cache
const cache = new Map<string, { data: WeatherData; expiresAt: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000;

export const CITY_WEATHER_COORDS = {
  Raleigh: { lat: 35.7796, lon: -78.6382 },
  Asheville: { lat: 35.5951, lon: -82.5515 }
};

export async function fetchWeatherByCoords(lat: number, lon: number, cityName?: string): Promise<WeatherData> {
  const cacheKey = `${lat.toFixed(2)},${lon.toFixed(2)}`;
  const cached = cache.get(cacheKey);
  const now = Date.now();

  if (cached && cached.expiresAt > now) {
    return cached.data;
  }

  try {
    const url = `https://api.openweathermap.org/data/2.5/weather?lat=${lat}&lon=${lon}&appid=${WEATHER_API_KEY}&units=imperial`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`OpenWeather API error: ${res.status}`);
    }
    const data = await res.json();

    const weatherData: WeatherData = {
      temp: Math.round(data.main.temp),
      feelsLike: Math.round(data.main.feels_like),
      condition: data.weather[0]?.main || 'Clear',
      description: data.weather[0]?.description || 'clear sky',
      icon: data.weather[0]?.icon || '01d',
      humidity: data.main.humidity,
      windSpeed: Math.round(data.wind?.speed || 0),
      rain1h: data.rain ? data.rain['1h'] : undefined,
      cityName: cityName || data.name || (lat > 35.65 ? 'Raleigh' : 'Asheville'),
      timestamp: now
    };

    cache.set(cacheKey, { data: weatherData, expiresAt: now + CACHE_TTL_MS });
    return weatherData;
  } catch (err) {
    console.warn('Weather fetch failed, using fallback:', err);
    // Fallback data
    const isAsh = Math.abs(lon - (-82.55)) < 1.0;
    return {
      temp: isAsh ? 74 : 69,
      feelsLike: isAsh ? 75 : 70,
      condition: 'Rain',
      description: 'light rain',
      icon: '10d',
      humidity: isAsh ? 84 : 93,
      windSpeed: isAsh ? 8 : 12,
      rain1h: isAsh ? 0.11 : 0.85,
      cityName: cityName || (isAsh ? 'Asheville' : 'Raleigh'),
      timestamp: now
    };
  }
}

export async function fetchWeatherByCity(city: 'Raleigh' | 'Asheville'): Promise<WeatherData> {
  const coords = CITY_WEATHER_COORDS[city] || CITY_WEATHER_COORDS.Raleigh;
  return fetchWeatherByCoords(coords.lat, coords.lon, city);
}
