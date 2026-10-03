import { useState, useEffect } from 'react';
import { Heart, Calendar, Eye, Thermometer, CloudRain } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { fetchWeatherByCoords, type WeatherData } from '../services/weatherService';

interface CleanLocationCardProps {
  selectedSegment: RoadSegment | null;
  onOpenDetails?: () => void;
}

export const CleanLocationCard: React.FC<CleanLocationCardProps> = ({
  selectedSegment,
  onOpenDetails
}) => {
  const [isFavorite, setIsFavorite] = useState(true);
  const [weather, setWeather] = useState<WeatherData | null>(null);

  const seg = selectedSegment;

  useEffect(() => {
    let active = true;
    const midIdx = seg && seg.path && seg.path.length > 0 ? Math.floor(seg.path.length / 2) : 0;
    const [lon, lat] = (seg && seg.path && seg.path[midIdx]) || [-78.565, 35.625];

    fetchWeatherByCoords(lat, lon, seg?.city).then((data) => {
      if (active) {
        setWeather(data);
      }
    });

    return () => {
      active = false;
    };
  }, [seg?.seg_id, seg?.city]);

  const isRaining = weather?.condition.toLowerCase().includes('rain') || (weather?.rain1h && weather.rain1h > 0);

  return (
    <div
      className="pixel-location-card live-html-card"
      onClick={onOpenDetails}
      title="Click to view deep road segment inspection telemetry"
      style={{ cursor: 'pointer' }}
    >
      <div className="loc-card-inner">
        {/* Header Row */}
        <div className="loc-header-row">
          <div className="loc-title-cluster">
            <div className="loc-main-title">
              <h2>Location</h2>
              <button
                type="button"
                className={`heart-btn ${isFavorite ? 'active' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setIsFavorite(!isFavorite);
                }}
                title="Toggle favorite"
                aria-label="Toggle favorite"
              >
                <Heart size={18} fill={isFavorite ? '#f59e0b' : 'none'} color="#f59e0b" />
              </button>
            </div>
            <p className="loc-address-text">
              {seg ? seg.name : 'Capital Blvd (US-401), Raleigh, NC'}
            </p>
            <div className="loc-tags-row">
              <span className="loc-tag">{seg ? seg.seg_id : 'ncdot:10000040051:0.000'}</span>
              <span className="loc-date">{seg?.city ? `${seg.city}, NC` : 'Raleigh, NC'}</span>
            </div>
          </div>
        </div>

        {/* 3 Telemetry Pods */}
        <div className="loc-pods-grid">
          {/* Pod 1: Pavement Age */}
          <div className="loc-pod" title="Pavement age in years since last resurfacing/overlay">
            <div className="pod-icon-chip">
              <Calendar size={15} color="#475569" />
            </div>
            <div className="pod-meta">
              <span className="pod-label">Pavement Age</span>
              <span className="pod-val">{seg ? seg.pv_age + 'Y' : '26Y'}</span>
            </div>
          </div>

          {/* Pod 2: Traffic Volume (AADT) */}
          <div className="loc-pod" title="Average Annual Daily Traffic volume for this road corridor">
            <div className="pod-icon-chip">
              <Eye size={15} color="#475569" />
            </div>
            <div className="pod-meta">
              <span className="pod-label">Traffic Volume</span>
              <span className="pod-val">
                {seg?.pred_rate ? `${(12 + Math.round(seg.pred_rate * 4)).toFixed(1)}k` : '14.8k'}
              </span>
            </div>
          </div>

          {/* Pod 3: Live Weather Temperature */}
          <div
            className="loc-pod"
            title={
              weather
                ? `${weather.cityName}: ${weather.temp}°F, ${weather.description}, Humidity ${weather.humidity}%, Wind ${weather.windSpeed} mph${
                    weather.rain1h ? ` (Precip ${weather.rain1h} mm/h)` : ''
                  }`
                : 'Connecting to OpenWeatherMap...'
            }
          >
            <div className="pod-icon-chip" style={{ background: isRaining ? '#eff6ff' : undefined }}>
              {isRaining ? (
                <CloudRain size={15} color="#3b82f6" />
              ) : (
                <Thermometer size={15} color="#475569" />
              )}
            </div>
            <div className="pod-meta">
              <span className="pod-label">Temperature</span>
              <span className="pod-val" style={{ color: isRaining ? '#1d4ed8' : undefined }}>
                {weather ? `${weather.temp}°F` : '69°F'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
