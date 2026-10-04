import { useState, useImperativeHandle, forwardRef, useEffect, useRef, useMemo } from 'react';
import { Search, ChevronDown, X, MapPin, Compass, Thermometer, CloudRain, Sun, Navigation } from 'lucide-react';
import type { RoadSegment, ViewFilter } from '../types/roadSegment';
import { MapView, type MapViewHandle, type ConditionColorFilter } from './MapView';
import { fetchWeatherByCity, type WeatherData } from '../services/weatherService';
import { MAPBOX_TOKEN } from '../config/mapbox';
import { getConditionInfo } from '../utils/colors';

export interface CleanMapCardHandle {
  flyToCity: (city: string) => void;
  flyToSegment: (segment: RoadSegment) => void;
  flyToCoords: (lng: number, lat: number, zoom?: number) => void;
}

interface CleanMapCardProps {
  segments: RoadSegment[];
  selectedSegment: RoadSegment | null;
  onSelectSegment: (segment: RoadSegment) => void;
  viewFilter: ViewFilter;
  onToggleFilter: (filter: ViewFilter) => void;
  activeCity: 'Asheville' | 'Raleigh' | 'Statewide' | string | null;
  onZoomCity: (city: 'Asheville' | 'Raleigh' | 'Statewide' | string) => void;
  onOpenHelp: () => void;
  onBboxChange?: (bbox: [number, number, number, number]) => void;
  conditionColorFilter?: ConditionColorFilter;
  onConditionColorFilterChange?: (filter: ConditionColorFilter) => void;
}

interface GeocodedPlace {
  id: string;
  name: string;
  placeName: string;
  center: [number, number];
}

export const CleanMapCard = forwardRef<CleanMapCardHandle, CleanMapCardProps>(({
  segments,
  selectedSegment,
  onSelectSegment,
  viewFilter: _viewFilter,
  onToggleFilter,
  activeCity,
  onZoomCity,
  onOpenHelp,
  onBboxChange,
  conditionColorFilter = 'all',
  onConditionColorFilterChange
}, ref) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<'insurance' | 'state' | 'city' | 'district' | 'condition' | null>(null);
  const [geocodedPlaces, setGeocodedPlaces] = useState<GeocodedPlace[]>([]);
  const [weather, setWeather] = useState<WeatherData | null>(null);

  const topBarRef = useRef<HTMLDivElement>(null);
  const searchContainerRef = useRef<HTMLDivElement>(null);
  const gisMapRef = useRef<MapViewHandle>(null);

  // Sync live weather for active city (Statewide → Raleigh)
  useEffect(() => {
    let active = true;
    const weatherCity = activeCity === 'Asheville' ? 'Asheville' : 'Raleigh';
    fetchWeatherByCity(weatherCity).then((w) => {
      if (active) setWeather(w);
    });
    return () => { active = false; };
  }, [activeCity]);

  // Close dropdowns and search suggestions when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (topBarRef.current && !topBarRef.current.contains(e.target as Node)) {
        setOpenDropdown(null);
      }
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setIsSearchFocused(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Mapbox Geocoding lookup for broader North Carolina locations (debounced)
  useEffect(() => {
    const query = searchQuery.trim();
    if (query.length < 3) {
      setGeocodedPlaces([]);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(query)}.json?access_token=${MAPBOX_TOKEN}&bbox=-84.3,33.8,-75.4,36.6&limit=3`;
        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        if (data && Array.isArray(data.features)) {
          const places: GeocodedPlace[] = data.features.map((f: any) => ({
            id: f.id,
            name: f.text,
            placeName: f.place_name,
            center: f.center
          }));
          setGeocodedPlaces(places);
        }
      } catch (e) {
        console.warn('Mapbox Geocoding error:', e);
      }
    }, 280);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  useImperativeHandle(ref, () => ({
    flyToCity: (city: string) => {
      gisMapRef.current?.flyToCity(city);
    },
    flyToSegment: (segment: RoadSegment) => {
      gisMapRef.current?.flyToSegment(segment);
    },
    flyToCoords: (lng: number, lat: number, zoom?: number) => {
      gisMapRef.current?.flyToCoords(lng, lat, zoom);
    }
  }));

  // Filter road segments matching query
  const matchedSegments = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return [];
    return segments
      .filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.seg_id.toLowerCase().includes(q) ||
        s.city.toLowerCase().includes(q)
      )
      .slice(0, 6);
  }, [segments, searchQuery]);

  // Matched cities
  const matchedCities = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return [];
    const cities: string[] = [];
    if ('statewide'.includes(q) || 'north carolina'.includes(q) || 'state'.includes(q)) cities.push('Statewide');
    if ('raleigh'.includes(q) || 'capital'.includes(q) || 'wake'.includes(q)) cities.push('Raleigh');
    if ('charlotte'.includes(q) || 'mecklenburg'.includes(q)) cities.push('Charlotte');
    if ('greensboro'.includes(q) || 'triad'.includes(q)) cities.push('Greensboro');
    if ('wilmington'.includes(q) || 'cape fear'.includes(q)) cities.push('Wilmington');
    if ('asheville'.includes(q) || 'helene'.includes(q) || 'buncombe'.includes(q)) cities.push('Asheville');
    return cities;
  }, [searchQuery]);

  const handleSelectMatchedSegment = (segment: RoadSegment) => {
    onSelectSegment(segment);
    gisMapRef.current?.flyToSegment(segment);
    setSearchQuery(segment.name);
    setIsSearchFocused(false);
  };

  const handleSelectCity = (city: string) => {
    if (city === 'Raleigh' || city === 'Asheville') {
      onZoomCity(city);
    }
    const firstInCity = segments.find(s => s.city.toLowerCase() === city.toLowerCase());
    if (firstInCity) onSelectSegment(firstInCity);
    gisMapRef.current?.flyToCity(city);
    setSearchQuery(city === 'Statewide' ? 'North Carolina' : `${city}, NC`);
    setIsSearchFocused(false);
  };

  const handleSelectGeocodedPlace = (place: GeocodedPlace) => {
    gisMapRef.current?.flyToCoords(place.center[0], place.center[1], 15.2);
    setSearchQuery(place.name);
    setIsSearchFocused(false);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (matchedSegments.length > 0) {
      handleSelectMatchedSegment(matchedSegments[0]);
    } else if (matchedCities.length > 0) {
      handleSelectCity(matchedCities[0]);
    } else if (geocodedPlaces.length > 0) {
      handleSelectGeocodedPlace(geocodedPlaces[0]);
    }
  };

  const toggleDropdown = (name: 'insurance' | 'state' | 'city' | 'district' | 'condition') => {
    setOpenDropdown(prev => (prev === name ? null : name));
  };

  // Compute subtle U-shape ambient glow rating: Green (Safe), Yellow (Caution), Red (Danger), Blue (Flood)
  const ratingStatus: 'safe' | 'caution' | 'danger' | 'blue' = useMemo(() => {
    if (conditionColorFilter === 'green') return 'safe';
    if (conditionColorFilter === 'yellow') return 'caution';
    if (conditionColorFilter === 'red') return 'danger';
    if (conditionColorFilter === 'blue') return 'blue';

    if (selectedSegment) {
      if (selectedSegment.in_helene_zone || (selectedSegment.pred_flood && selectedSegment.pred_flood > 0.15)) {
        return 'blue';
      }
      const score = typeof selectedSegment.score === 'number' && !isNaN(selectedSegment.score)
        ? selectedSegment.score
        : (selectedSegment.pv_rating ? selectedSegment.pv_rating / 100 : 0.75);
      if (score < 0.45 || (selectedSegment.pred_crack && selectedSegment.pred_crack > 0.4)) {
        return 'danger';
      }
      if (score < 0.70) {
        return 'caution';
      }
      return 'safe';
    }

    return 'safe';
  }, [conditionColorFilter, selectedSegment]);

  const showSuggestions = isSearchFocused && searchQuery.trim().length > 0;
  const isRaining = weather?.condition.toLowerCase().includes('rain') || (weather?.rain1h && weather.rain1h > 0);

  return (
    <div className="pixel-map-card">
      {/* Live Vector GIS Map (Mapbox GL + deck.gl) */}
      <div style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}>
        <MapView
          ref={gisMapRef}
          segments={segments}
          selectedSegment={selectedSegment}
          onSelectSegment={onSelectSegment}
          onBboxChange={onBboxChange}
          conditionColorFilter={conditionColorFilter}
        />
      </div>

      {/* Subtle U-Shaped Rating Ambient Glow (Bottom-Left, Bottom, Bottom-Right) */}
      <div className={`map-rating-u-glow rating-${ratingStatus}`} aria-hidden="true" />

      {/* Top Floating Controls Bar */}
      <div className="pixel-map-top-bar" ref={topBarRef}>
        {/* Interactive Search Input Form with Autocomplete */}
        <div className="pixel-search-container" ref={searchContainerRef}>
          <form onSubmit={handleSearchSubmit} className="pixel-search-form">
            <Search size={16} className="pixel-search-icon" />
            <input
              type="text"
              className="pixel-search-input"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setIsSearchFocused(true);
              }}
              onFocus={() => setIsSearchFocused(true)}
              placeholder="Search Raleigh, Asheville, US-70, Hillsborough..."
              aria-label="Search road segments and North Carolina places"
            />
            {searchQuery && (
              <button
                type="button"
                className="search-clear-btn"
                onClick={() => {
                  setSearchQuery('');
                  setGeocodedPlaces([]);
                }}
                title="Clear search"
                aria-label="Clear search"
              >
                <X size={14} />
              </button>
            )}
          </form>

          {/* Autocomplete Suggestions Menu */}
          {showSuggestions && (
            <div className="pixel-search-dropdown" role="listbox">
              {/* Road Segments Section */}
              {matchedSegments.length > 0 && (
                <div className="search-section">
                  <div className="search-section-header">Road Segments ({matchedSegments.length})</div>
                  {matchedSegments.map((s) => {
                    const cond = getConditionInfo(s.score);
                    return (
                      <button
                        key={s.seg_id}
                        type="button"
                        className="search-item"
                        onClick={() => handleSelectMatchedSegment(s)}
                      >
                        <div className="search-item-left">
                          <MapPin size={14} className="search-item-icon" />
                          <div>
                            <div className="search-item-title">{s.name}</div>
                            <div className="search-item-sub">
                              {s.city}, NC • {s.seg_id} • {s.years_to_poor}y to poor
                            </div>
                          </div>
                        </div>
                        <span
                          className="search-item-pill"
                          style={{ background: cond.bgRgba, color: cond.color }}
                        >
                          {s.pv_rating} / 100
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Cities Section */}
              {matchedCities.length > 0 && (
                <div className="search-section">
                  <div className="search-section-header">City Corridors</div>
                  {matchedCities.map((city) => (
                    <button
                      key={city}
                      type="button"
                      className="search-item"
                      onClick={() => handleSelectCity(city)}
                    >
                      <div className="search-item-left">
                        <Compass size={14} className="search-item-icon" />
                        <div>
                          <div className="search-item-title">{city}, North Carolina</div>
                          <div className="search-item-sub">
                            {city === 'Raleigh'
                              ? 'Capital District • 6,257 Arterial Segments'
                              : 'Helene Disaster Zone • Western NC Mountain Corridor'}
                          </div>
                        </div>
                      </div>
                      <span className="search-item-pill pill-city-tag">
                        Fly to City
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Mapbox Places Geocoding */}
              {geocodedPlaces.length > 0 && (
                <div className="search-section">
                  <div className="search-section-header">North Carolina Places (Mapbox)</div>
                  {geocodedPlaces.map((place) => (
                    <button
                      key={place.id}
                      type="button"
                      className="search-item"
                      onClick={() => handleSelectGeocodedPlace(place)}
                    >
                      <div className="search-item-left">
                        <Navigation size={14} className="search-item-icon" />
                        <div>
                          <div className="search-item-title">{place.name}</div>
                          <div className="search-item-sub">{place.placeName}</div>
                        </div>
                      </div>
                      <span className="search-item-pill pill-gis-tag">
                        Mapbox GIS
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {matchedSegments.length === 0 && matchedCities.length === 0 && geocodedPlaces.length === 0 && (
                <div className="search-no-results">
                  No segments found for "{searchQuery}". Press Enter to search statewide.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Filter Cluster */}
        <div className="pixel-filters-cluster">
          {/* Live Atmospheric Weather Pill */}
          <div
            className="weather-top-pill"
            title={
              weather
                ? `Live OpenWeatherMap Telemetry for ${weather.cityName}, NC\nTemperature: ${weather.temp}°F (Feels like ${weather.feelsLike}°F)\nCondition: ${weather.description}\nHumidity: ${weather.humidity}%\nWind Speed: ${weather.windSpeed} mph${
                    weather.rain1h ? `\nPrecipitation: ${weather.rain1h} mm/hr (Helene Flood Exposure Risk)` : ''
                  }`
                : 'Loading weather...'
            }
            onClick={() => onZoomCity(activeCity === 'Raleigh' ? 'Asheville' : 'Raleigh')}
          >
            {isRaining ? (
              <CloudRain size={15} color="#3b82f6" />
            ) : weather && weather.temp > 70 ? (
              <Sun size={15} color="#f59e0b" />
            ) : (
              <Thermometer size={15} color="#475569" />
            )}
            <span style={{ color: isRaining ? '#1d4ed8' : '#0f172a' }}>
              {weather ? `${weather.temp}°F` : '69°F'}
            </span>
            <span style={{ color: '#64748b', fontSize: '11px', fontWeight: 500 }}>
              {weather?.cityName || activeCity || 'Raleigh'}
            </span>
          </div>

          {/* Insurance Type Dropdown */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className={`pixel-filter-btn ${openDropdown === 'insurance' ? 'active' : ''}`}
              onClick={() => toggleDropdown('insurance')}
              title="Insurance Type"
              aria-label="Insurance Type"
            >
              <span>Insurance Type</span>
              <ChevronDown size={14} className="pixel-filter-chevron" />
            </button>
            {openDropdown === 'insurance' && (
              <div className="pixel-dropdown-menu">
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    onToggleFilter('all');
                    setOpenDropdown(null);
                  }}
                >
                  All Street Types (Prediction)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    onToggleFilter('ncdot');
                    setOpenDropdown(null);
                  }}
                >
                  State Surveys (NCDOT Only)
                </button>
              </div>
            )}
          </div>

          {/* State Dropdown */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className={`pixel-filter-btn ${openDropdown === 'state' ? 'active' : ''}`}
              onClick={() => toggleDropdown('state')}
              title="State / Region"
              aria-label="State"
            >
              <span>State</span>
              <ChevronDown size={14} className="pixel-filter-chevron" />
            </button>
            {openDropdown === 'state' && (
              <div className="pixel-dropdown-menu">
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    handleSelectCity('Statewide');
                    setOpenDropdown(null);
                  }}
                >
                  North Carolina Statewide (112,443 Segments)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    handleSelectCity('Statewide');
                    setOpenDropdown(null);
                  }}
                >
                  All State Jurisdictions
                </button>
              </div>
            )}
          </div>

          {/* City Dropdown */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className={`pixel-filter-btn ${openDropdown === 'city' ? 'active' : ''}`}
              onClick={() => toggleDropdown('city')}
              title="City Focus"
              aria-label="City"
            >
              <span>{activeCity || 'City'}</span>
              <ChevronDown size={14} className="pixel-filter-chevron" />
            </button>
            {openDropdown === 'city' && (
              <div className="pixel-dropdown-menu">
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    handleSelectCity('Statewide');
                    setOpenDropdown(null);
                  }}
                >
                  Statewide (All North Carolina)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    handleSelectCity('Raleigh');
                    setOpenDropdown(null);
                  }}
                >
                  Raleigh (Capital District)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    handleSelectCity('Charlotte');
                    setOpenDropdown(null);
                  }}
                >
                  Charlotte (Metrolina Corridor)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    handleSelectCity('Greensboro');
                    setOpenDropdown(null);
                  }}
                >
                  Greensboro (Piedmont Triad)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    handleSelectCity('Wilmington');
                    setOpenDropdown(null);
                  }}
                >
                  Wilmington (Coastal Corridor)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => {
                    handleSelectCity('Asheville');
                    setOpenDropdown(null);
                  }}
                >
                  Asheville (Helene Mountain Zone)
                </button>
              </div>
            )}
          </div>

          {/* District Dropdown */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className={`pixel-filter-btn ${openDropdown === 'district' ? 'active' : ''}`}
              onClick={() => toggleDropdown('district')}
              title="District"
              aria-label="District"
            >
              <span>District</span>
              <ChevronDown size={14} className="pixel-filter-chevron" />
            </button>
            {openDropdown === 'district' && (
              <div className="pixel-dropdown-menu">
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => setOpenDropdown(null)}
                >
                  District 1 (Western Mountains / Helene)
                </button>
                <button
                  type="button"
                  className="pixel-dropdown-item"
                  onClick={() => setOpenDropdown(null)}
                >
                  District 2 (Central Piedmont &amp; Triangle)
                </button>
              </div>
            )}
          </div>

          {/* Condition Dropdown (Blue, Green, Yellow, Red) */}
          <div className="pixel-filter-wrap">
            <button
              type="button"
              className={`pixel-filter-btn condition-filter-btn ${openDropdown === 'condition' ? 'active' : ''} ${conditionColorFilter !== 'all' ? `active-filter-${conditionColorFilter}` : ''}`}
              onClick={() => toggleDropdown('condition')}
              title="Filter Road Condition (Blue, Green, Yellow, Red)"
              aria-label="Filter Road Condition"
            >
              <span className={`condition-indicator-dot ${conditionColorFilter}`} />
              <span>
                {conditionColorFilter === 'all' && 'Condition'}
                {conditionColorFilter === 'blue' && 'Blue (Helene)'}
                {conditionColorFilter === 'green' && 'Green (Safe)'}
                {conditionColorFilter === 'yellow' && 'Yellow (Caution)'}
                {conditionColorFilter === 'red' && 'Red (Danger)'}
              </span>
              <ChevronDown size={14} className="pixel-filter-chevron" />
            </button>
            {openDropdown === 'condition' && (
              <div className="pixel-dropdown-menu condition-dropdown-menu">
                <button
                  type="button"
                  className={`pixel-dropdown-item ${conditionColorFilter === 'all' ? 'selected' : ''}`}
                  onClick={() => {
                    onConditionColorFilterChange?.('all');
                    setOpenDropdown(null);
                  }}
                >
                  <span className="condition-item-dot all" />
                  <span className="condition-item-label">All Conditions</span>
                </button>
                <button
                  type="button"
                  className={`pixel-dropdown-item ${conditionColorFilter === 'blue' ? 'selected' : ''}`}
                  onClick={() => {
                    onConditionColorFilterChange?.('blue');
                    setOpenDropdown(null);
                  }}
                >
                  <span className="condition-item-dot blue" />
                  <span className="condition-item-label">Blue (Helene / Flood Zone)</span>
                  <span className="condition-badge blue">Zone</span>
                </button>
                <button
                  type="button"
                  className={`pixel-dropdown-item ${conditionColorFilter === 'green' ? 'selected' : ''}`}
                  onClick={() => {
                    onConditionColorFilterChange?.('green');
                    setOpenDropdown(null);
                  }}
                >
                  <span className="condition-item-dot green" />
                  <span className="condition-item-label">Green (Safe / Optimal)</span>
                  <span className="condition-badge green">Safe</span>
                </button>
                <button
                  type="button"
                  className={`pixel-dropdown-item ${conditionColorFilter === 'yellow' ? 'selected' : ''}`}
                  onClick={() => {
                    onConditionColorFilterChange?.('yellow');
                    setOpenDropdown(null);
                  }}
                >
                  <span className="condition-item-dot yellow" />
                  <span className="condition-item-label">Yellow (Caution / Fair)</span>
                  <span className="condition-badge yellow">Caution</span>
                </button>
                <button
                  type="button"
                  className={`pixel-dropdown-item ${conditionColorFilter === 'red' ? 'selected' : ''}`}
                  onClick={() => {
                    onConditionColorFilterChange?.('red');
                    setOpenDropdown(null);
                  }}
                >
                  <span className="condition-item-dot red" />
                  <span className="condition-item-label">Red (Danger / Critical)</span>
                  <span className="condition-badge red">Danger</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Floating 3 Frosted Glass Telemetry Widgets */}
      <div className="pixel-black-cards-group gis-mode">
        <div className="gis-telemetry-chip">
          <span className="telemetry-value">
            {selectedSegment ? selectedSegment.pv_rating : '94'}
          </span>
          <span className="telemetry-label">Ratings</span>
        </div>
        <div className="gis-telemetry-chip chip-wide">
          <span className="telemetry-value">
            {selectedSegment ? `-${(selectedSegment.pred_rate || 0.4).toFixed(1)} pts/yr` : '-0.4 pts/yr'}
          </span>
          <span className="telemetry-label">Degradation Rate</span>
        </div>
        <div className="gis-telemetry-chip">
          <span className="telemetry-value">
            {selectedSegment ? `${selectedSegment.years_to_poor} yrs` : '42.5 yrs'}
          </span>
          <span className="telemetry-label">Years to Pour</span>
        </div>
      </div>

      {/* Bottom Right Floating Question Button */}
      <button
        type="button"
        className="pixel-help-btn-hotspot"
        onClick={onOpenHelp}
        title="Help & Info"
        aria-label="Help & Info"
      />
    </div>
  );
});

CleanMapCard.displayName = 'CleanMapCard';
