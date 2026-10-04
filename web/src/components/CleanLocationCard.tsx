import { useState, useEffect } from 'react';
import { Calendar, Eye, Thermometer, CloudRain, ChevronRight } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { fetchWeatherByCoords, type WeatherData } from '../services/weatherService';
import { routeClassOf, useRoadRecord } from '../utils/roadFacts';

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
  // Surface age and traffic come from the road's NCDOT record. A dash means it is not on record.
  const record = useRoadRecord(seg);
  const pavedYear = record?.ry ?? null;
  const pvAge = pavedYear != null ? Math.max(0, new Date().getFullYear() - pavedYear) : null;
  const aadt = record?.aadt != null ? (record.aadt >= 1000 ? `${(record.aadt / 1000).toFixed(1)}k` : String(record.aadt)) : null;
  const routeClass = seg ? routeClassOf(seg.seg_id) : null;

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
              <h2>{seg ? seg.name : 'Select a road on the map'}</h2>
            </div>
            <p className="loc-address-text">
              {seg ? <>Near {seg.city}, NC • Segment <code>{seg.seg_id}</code></> : 'No road selected'}
            </p>
          </div>
          <div className="loc-arrow-indicator" aria-hidden="true">
            <ChevronRight size={14} />
          </div>
        </div>

        {/* 3 Minimalist Telemetry Pods */}
        <div className="loc-pods-grid">
          {/* Pod 1: Pavement Age */}
          <div className="loc-pod" title={pavedYear != null ? `Years since NCDOT last resurfaced this road (${pavedYear})` : 'No resurfacing year on record for this road'}>
            <div className="pod-header">
              <Calendar size={13} className="pod-icon" />
              <span className="pod-label">SURFACE AGE</span>
            </div>
            <div className="pod-body">
              <span className="pod-val">{pvAge != null ? <>{pvAge} <span className="pod-unit">yrs</span></> : '–'}</span>
              <span className="pod-subtext">{pavedYear != null ? `Last resurfaced ${pavedYear}` : 'Not on record'}</span>
            </div>
          </div>

          {/* Pod 2: Traffic Volume (AADT) */}
          <div className="loc-pod" title="NCDOT's vehicles-per-day figure for this road (a count where it has one, otherwise its estimate)">
            <div className="pod-header">
              <Eye size={13} className="pod-icon" />
              <span className="pod-label">DAILY TRAFFIC</span>
            </div>
            <div className="pod-body">
              <span className="pod-val">{aadt != null ? <>{aadt} <span className="pod-unit">AADT</span></> : '–'}</span>
              <span className="pod-subtext">{aadt != null ? `Vehicles / day${record?.as === 'count' ? '' : ' (est.)'}` : 'Not on record'}</span>
            </div>
          </div>

          {/* Pod 3: Live Weather Temperature */}
          <div
            className="loc-pod"
            title={
              weather
                ? `${weather.cityName}: ${weather.temp}°F, ${weather.description}, Humidity ${weather.humidity}%, Wind ${weather.windSpeed} mph`
                : 'Weather is not available right now'
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
              <span className="pod-val">{weather ? `${weather.temp}°F` : '–'}</span>
              <span className="pod-subtext">{!weather ? 'Weather unavailable' : isRaining ? 'Raining now' : weather.description}</span>
            </div>
          </div>
        </div>

        {/* Footer Dossier Note */}
        <div className="loc-footer-row">
          <span className="loc-footer-status">
            Route class: <strong>{routeClass ?? 'State road'}</strong>
          </span>
          <span className="loc-footer-action">Inspect Segment →</span>
        </div>
      </div>
    </div>
  );
};
