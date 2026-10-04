/**
 * Current weather for a point. OpenWeather when a key is configured; otherwise (or when that
 * fails) Open-Meteo, which needs no key. When neither answers, the result is null and the
 * dashboard says the weather is unavailable. It never shows a made-up reading.
 */
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
  /** Which service the reading came from. */
  source: 'OpenWeather' | 'Open-Meteo';
}

const WEATHER_API_KEY = import.meta.env.VITE_OPENWEATHER_API_KEY || '';

// 5-minute cache. A failure is remembered too, so a missing key is not retried on every click.
const cache = new Map<string, { data: WeatherData | null; expiresAt: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000;

export const CITY_WEATHER_COORDS = {
  Raleigh: { lat: 35.7796, lon: -78.6382 },
  Asheville: { lat: 35.5951, lon: -82.5515 },
};

/** WMO weather codes, as Open-Meteo reports them. */
function describeCode(code: number): { condition: string; description: string } {
  if (code === 0) return { condition: 'Clear', description: 'clear sky' };
  if (code <= 2) return { condition: 'Clouds', description: 'partly cloudy' };
  if (code === 3) return { condition: 'Clouds', description: 'overcast' };
  if (code <= 48) return { condition: 'Fog', description: 'fog' };
  if (code <= 57) return { condition: 'Drizzle', description: 'drizzle' };
  if (code <= 67) return { condition: 'Rain', description: code >= 65 ? 'heavy rain' : 'rain' };
  if (code <= 77) return { condition: 'Snow', description: 'snow' };
  if (code <= 82) return { condition: 'Rain', description: 'rain showers' };
  if (code <= 86) return { condition: 'Snow', description: 'snow showers' };
  return { condition: 'Thunderstorm', description: 'thunderstorm' };
}

async function fromOpenWeather(lat: number, lon: number, cityName: string | undefined, now: number): Promise<WeatherData> {
  const res = await fetch(`https://api.openweathermap.org/data/2.5/weather?lat=${lat}&lon=${lon}&appid=${WEATHER_API_KEY}&units=imperial`);
  if (!res.ok) throw new Error(`OpenWeather: HTTP ${res.status}`);
  const data = await res.json();
  return {
    temp: Math.round(data.main.temp),
    feelsLike: Math.round(data.main.feels_like),
    condition: data.weather[0]?.main || 'Clear',
    description: data.weather[0]?.description || 'clear sky',
    icon: data.weather[0]?.icon || '01d',
    humidity: data.main.humidity,
    windSpeed: Math.round(data.wind?.speed || 0),
    rain1h: data.rain ? data.rain['1h'] : undefined,
    cityName: cityName || data.name || 'This location',
    timestamp: now,
    source: 'OpenWeather',
  };
}

async function fromOpenMeteo(lat: number, lon: number, cityName: string | undefined, now: number): Promise<WeatherData> {
  const fields = 'temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m';
  const res = await fetch(
    `https://api.open-meteo.com/v1/forecast?latitude=${lat.toFixed(3)}&longitude=${lon.toFixed(3)}&current=${fields}&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=mm`,
  );
  if (!res.ok) throw new Error(`Open-Meteo: HTTP ${res.status}`);
  const c = (await res.json()).current;
  const { condition, description } = describeCode(Number(c.weather_code));
  return {
    temp: Math.round(c.temperature_2m),
    feelsLike: Math.round(c.apparent_temperature),
    condition,
    description,
    icon: '',
    humidity: Math.round(c.relative_humidity_2m),
    windSpeed: Math.round(c.wind_speed_10m),
    rain1h: c.precipitation > 0 ? c.precipitation : undefined,
    cityName: cityName || 'This location',
    timestamp: now,
    source: 'Open-Meteo',
  };
}

export async function fetchWeatherByCoords(lat: number, lon: number, cityName?: string): Promise<WeatherData | null> {
  const cacheKey = `${lat.toFixed(2)},${lon.toFixed(2)}`;
  const now = Date.now();
  const cached = cache.get(cacheKey);
  if (cached && cached.expiresAt > now) return cached.data && { ...cached.data, cityName: cityName || cached.data.cityName };

  let data: WeatherData | null = null;
  if (WEATHER_API_KEY) data = await fromOpenWeather(lat, lon, cityName, now).catch(() => null);
  if (!data) data = await fromOpenMeteo(lat, lon, cityName, now).catch(() => null);
  cache.set(cacheKey, { data, expiresAt: now + CACHE_TTL_MS });
  return data;
}

export async function fetchWeatherByCity(city: 'Raleigh' | 'Asheville'): Promise<WeatherData | null> {
  const coords = CITY_WEATHER_COORDS[city] || CITY_WEATHER_COORDS.Raleigh;
  return fetchWeatherByCoords(coords.lat, coords.lon, city);
}
