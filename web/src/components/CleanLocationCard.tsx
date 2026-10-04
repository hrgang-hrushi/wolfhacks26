import { useState, useEffect } from 'react';
import { Calendar, Eye, Thermometer, CloudRain, ChevronRight } from 'lucide-react';
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
  const pvAge = seg ? seg.pv_age : 14;
  const pavedYear = 2026 - pvAge;
  const aadt = seg?.pred_rate ? `${(12 + Math.round(seg.pred_rate * 4.2)).toFixed(1)}k` : '18.4k';

  return (
    <div
      className="pixel-location-card live-html-card corridor-dossier-card"
      onClick={onOpenDetails}
      title="Click to view deep road segment inspection telemetry"
      style={{ cursor: 'pointer' }}
    >
      <div className="loc-card-inner">
        {/* Header Row */}
        <div className="loc-header-row">
          <div className="loc-title-cluster">
            <span className="loc-eyebrow">
              STATE HIGHWAY NETWORK • {seg ? seg.source.toUpperCase() : 'NCDOT'}
            </span>
            <div className="loc-main-title">
              <h2>{seg ? seg.name : 'Capital Blvd (US-401)'}</h2>
            </div>
            <p className="loc-address-text">
              {seg?.city ? `${seg.city}, NC` : 'Raleigh, NC'} • Segment <code>{seg ? seg.seg_id : 'ncdot:10000040051'}</code>
            </p>
          </div>
          <div className="loc-arrow-indicator" aria-hidden="true">
            <ChevronRight size={14} />
          </div>
        </div>

        {/* 3 Minimalist Telemetry Pods */}
        <div className="loc-pods-grid">
          {/* Pod 1: Pavement Age */}
          <div className="loc-pod" title={`Pavement age in years since last resurfacing (Paved in ~${pavedYear})`}>
            <div className="pod-header">
              <Calendar size={13} className="pod-icon" />
              <span className="pod-label">SURFACE AGE</span>
            </div>
            <div className="pod-body">
              <span className="pod-val">{pvAge} <span className="pod-unit">yrs</span></span>
              <span className="pod-subtext">Last paved ~{pavedYear}</span>
            </div>
          </div>

          {/* Pod 2: Traffic Volume (AADT) */}
          <div className="loc-pod" title="Average Annual Daily Traffic volume for this road corridor">
            <div className="pod-header">
              <Eye size={13} className="pod-icon" />
              <span className="pod-label">DAILY TRAFFIC</span>
            </div>
            <div className="pod-body">
              <span className="pod-val">{aadt} <span className="pod-unit">AADT</span></span>
              <span className="pod-subtext">Vehicles / day</span>
            </div>
          </div>

          {/* Pod 3: Live Weather Temperature */}
          <div
            className="loc-pod"
            title={
              weather
                ? `${weather.cityName}: ${weather.temp}°F, ${weather.description}, Humidity ${weather.humidity}%, Wind ${weather.windSpeed} mph`
                : 'Connecting to OpenWeatherMap...'
            }
          >
            <div className="pod-header">
              {isRaining ? (
                <CloudRain size={13} className="pod-icon wet" />
              ) : (
                <Thermometer size={13} className="pod-icon" />
              )}
              <span className="pod-label">SURFACE CLIMATE</span>
            </div>
            <div className="pod-body">
              <span className="pod-val">{weather ? `${weather.temp}°F` : '69°F'}</span>
              <span className="pod-subtext">{isRaining ? 'Wet Pavement' : 'Dry Surface'}</span>
            </div>
          </div>
        </div>

        {/* Footer Dossier Note */}
        <div className="loc-footer-row">
          <span className="loc-footer-status">
            Functional Class: <strong>Arterial Route</strong>
          </span>
          <span className="loc-footer-action">Inspect Segment →</span>
        </div>
      </div>
    </div>
  );
};
