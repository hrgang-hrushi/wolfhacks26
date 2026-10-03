import { useState } from 'react';
import type { FC } from 'react';
import {
  ChevronDown,
  Calendar,
  SlidersHorizontal,
  Download,
  Mountain,
  Landmark,
  Eye,
  Sparkles
} from 'lucide-react';
import type { ViewFilter } from '../types/roadSegment';

interface SubHeaderRowProps {
  viewFilter: ViewFilter;
  onToggleFilter: (filter: ViewFilter) => void;
  activeCity: 'Asheville' | 'Raleigh' | null;
  onZoomCity: (city: 'Asheville' | 'Raleigh') => void;
  onExportData?: () => void;
}

export const SubHeaderRow: FC<SubHeaderRowProps> = ({
  viewFilter,
  onToggleFilter,
  activeCity,
  onZoomCity,
  onExportData
}) => {
  const [selectedRegion, setSelectedRegion] = useState('USA');
  const [isRegionDropdownOpen, setIsRegionDropdownOpen] = useState(false);

  return (
    <div className="subheader-row-container">
      {/* Left: Greeting matching frame 7 */}
      <div className="subheader-left">
        <h1 className="subheader-greeting-title">Hey, Alex</h1>
      </div>

      {/* Right: Controls & Filters matching frame 7 */}
      <div className="subheader-right-actions">
        {/* Toggle: "What the State Surveys" vs "What We Predict" */}
        <div className="survey-mode-toggle" role="radiogroup" aria-label="Survey coverage mode">
          <button
            type="button"
            className={`survey-toggle-pill ${viewFilter === 'ncdot' ? 'active-pill' : ''}`}
            onClick={() => onToggleFilter('ncdot')}
            title="State surveyed highways only (NCDOT)"
          >
            <Eye size={13} />
            <span>What the State Surveys</span>
          </button>

          <button
            type="button"
            className={`survey-toggle-pill ${viewFilter === 'all' ? 'active-pill' : ''}`}
            onClick={() => onToggleFilter('all')}
            title="AI predictions across all streets"
          >
            <Sparkles size={13} />
            <span>What We Predict</span>
          </button>
        </div>

        {/* Two Zoom Buttons: Asheville and Raleigh */}
        <div className="city-zoom-pill-group">
          <button
            type="button"
            className={`city-pill-btn ${activeCity === 'Asheville' ? 'active-city-pill' : ''}`}
            onClick={() => onZoomCity('Asheville')}
            title="Fly to Asheville (Mountain corridor)"
          >
            <Mountain size={13} />
            <span>Asheville</span>
          </button>

          <button
            type="button"
            className={`city-pill-btn ${activeCity === 'Raleigh' ? 'active-city-pill' : ''}`}
            onClick={() => onZoomCity('Raleigh')}
            title="Fly to Raleigh (Capital corridor)"
          >
            <Landmark size={13} />
            <span>Raleigh</span>
          </button>
        </div>

        {/* Region Dropdown: USA ▾ */}
        <div className="region-dropdown-wrap">
          <button
            type="button"
            className="subheader-pill-btn region-btn"
            onClick={() => setIsRegionDropdownOpen((prev) => !prev)}
          >
            <span>{selectedRegion}</span>
            <ChevronDown size={14} />
          </button>

          {isRegionDropdownOpen && (
            <div className="region-dropdown-menu">
              {['USA', 'North Carolina', 'Raleigh Metro', 'Asheville Metro'].map((region) => (
                <button
                  key={region}
                  type="button"
                  className="dropdown-item-btn"
                  onClick={() => {
                    setSelectedRegion(region);
                    setIsRegionDropdownOpen(false);
                  }}
                >
                  {region}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Calendar Icon Pill */}
        <button
          type="button"
          className="subheader-pill-btn icon-only-pill"
          title="Date Range Picker"
        >
          <Calendar size={16} />
        </button>

        {/* Sliders / Filter Icon Pill */}
        <button
          type="button"
          className="subheader-pill-btn icon-only-pill"
          title="Filter Parameters"
        >
          <SlidersHorizontal size={16} />
        </button>

        {/* Export Button */}
        <button
          type="button"
          className="subheader-pill-btn export-btn"
          onClick={onExportData}
          title="Export road condition dataset"
        >
          <span>Export</span>
          <Download size={14} />
        </button>
      </div>
    </div>
  );
};
