import { useState, useMemo } from 'react';
import type { FC } from 'react';
import { Search, ChevronRight, X, Building2, MapPin, ListFilter } from 'lucide-react';
import type { RoadSegment } from '../types/roadSegment';
import { getConditionInfo } from '../utils/colors';

interface SegmentListDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  segments: RoadSegment[];
  selectedSegment: RoadSegment | null;
  onSelectSegment: (segment: RoadSegment) => void;
}

export const SegmentListDrawer: FC<SegmentListDrawerProps> = ({
  isOpen,
  onClose,
  segments,
  selectedSegment,
  onSelectSegment
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [cityFilter, setCityFilter] = useState<'All' | 'Raleigh' | 'Asheville'>('All');

  const filtered = useMemo(() => {
    return segments.filter((s) => {
      const matchesSearch =
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.seg_id.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCity = cityFilter === 'All' || s.city === cityFilter;
      return matchesSearch && matchesCity;
    });
  }, [segments, searchQuery, cityFilter]);

  if (!isOpen) return null;

  return (
    <div className="drawer-panel" aria-label="Road segments catalogue">
      <div className="drawer-header">
        <div className="drawer-title-row">
          <div className="flex items-center gap-2">
            <ListFilter size={16} className="text-cyan-400" />
            <h3>Road Segments Directory</h3>
          </div>
          <button onClick={onClose} className="drawer-close-btn" aria-label="Close drawer">
            <X size={18} />
          </button>
        </div>

        {/* Search input */}
        <div className="drawer-search-box">
          <Search size={14} className="search-icon" />
          <input
            type="text"
            placeholder="Search by street name or ID (e.g. Capital, Patton)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="drawer-search-input"
          />
        </div>

        {/* City Filter Tabs */}
        <div className="city-filter-tabs">
          {(['All', 'Raleigh', 'Asheville'] as const).map((city) => (
            <button
              key={city}
              type="button"
              className={`city-tab ${cityFilter === city ? 'active' : ''}`}
              onClick={() => setCityFilter(city)}
            >
              {city} ({segments.filter((s) => city === 'All' || s.city === city).length})
            </button>
          ))}
        </div>
      </div>

      <div className="drawer-body">
        <div className="segments-count-text">
          Showing <strong>{filtered.length}</strong> matching segments:
        </div>

        <div className="segments-list">
          {filtered.map((s) => {
            const condition = getConditionInfo(s.score);
            const isSelected = selectedSegment?.seg_id === s.seg_id;

            return (
              <div
                key={s.seg_id}
                className={`segment-list-item ${isSelected ? 'selected' : ''}`}
                onClick={() => onSelectSegment(s)}
                style={{
                  borderLeftColor: condition.color
                }}
              >
                <div className="item-top">
                  <span className="item-name">{s.name}</span>
                  <span
                    className="item-rating"
                    style={{ color: condition.color }}
                  >
                    {s.pv_rating} / 100
                  </span>
                </div>

                <div className="item-details">
                  <span className="item-id">{s.seg_id}</span>
                  <span className={`item-source ${s.source === 'ncdot' ? 'ncdot' : 'city'}`}>
                    <Building2 size={10} />
                    {s.source === 'ncdot' ? 'NCDOT' : 'City'}
                  </span>
                  <span className="item-city">
                    <MapPin size={10} />
                    {s.city}
                  </span>
                  <span className="item-years">
                    {s.years_to_poor}y to Poor
                  </span>
                </div>

                <ChevronRight size={14} className="item-arrow" />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
