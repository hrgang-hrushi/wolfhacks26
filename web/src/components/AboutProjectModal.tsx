import type { FC } from 'react';
import { X, Info, Sparkles, Droplets, MapPin, Eye, ShieldCheck } from 'lucide-react';

interface AboutProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AboutProjectModal: FC<AboutProjectModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card about-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-header-title">
            <Info className="text-cyan-400" size={22} />
            <div>
              <h3>What is RoadSense AI?</h3>
              <span className="modal-subtitle">WolfHacks '26 &bull; North Carolina Infrastructure Condition &amp; Flood Risk Intelligence</span>
            </div>
          </div>
          <button onClick={onClose} className="modal-close-btn" aria-label="Close modal">
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {/* Core Problem Callout */}
          <div className="arch-callout">
            <Droplets size={22} className="text-cyan-400 shrink-0 mt-0.5" />
            <div>
              <strong>The Infrastructure Blindspot</strong>
              <p>
                The North Carolina Department of Transportation (NCDOT) surveys primary state highways annually,
                leaving over <strong>60% of municipal city roads and neighborhood streets unmonitored</strong>.
                Meanwhile, extreme storms (like Hurricane Helene) saturate road sub-bases, causing sudden pavement
                failures and washouts long before traditional inspection crews ever visit.
              </p>
            </div>
          </div>

          {/* How this App Works */}
          <div className="about-grid">
            <div className="about-card">
              <div className="about-card-icon text-cyan-400">
                <Sparkles size={18} />
              </div>
              <h4>AI Pavement Prediction</h4>
              <p>
                Combines high-resolution aerial imagery, heavy truck traffic (ESAL), and pavement age to predict
                the current pavement condition (0–100) and <strong>years until the road reaches "Poor" condition</strong>.
              </p>
            </div>

            <div className="about-card">
              <div className="about-card-icon text-rose-400">
                <Droplets size={18} />
              </div>
              <h4>Flood &amp; Washout Risk</h4>
              <p>
                Calculates sub-base water saturation using NOAA elevation models and FEMA flood plains to highlight
                segments vulnerable to structural collapse under recurrent inundation.
              </p>
            </div>

            <div className="about-card">
              <div className="about-card-icon text-amber-400">
                <Eye size={18} />
              </div>
              <h4>Survey Gap Toggle</h4>
              <p>
                Switch between <strong>"What the state surveys"</strong> (NCDOT only) and <strong>"What we predict"</strong> (every street)
                to visualize how AI expands state surveillance across the entire road network.
              </p>
            </div>

            <div className="about-card">
              <div className="about-card-icon text-emerald-400">
                <MapPin size={18} />
              </div>
              <h4>Dual-Region Corridors</h4>
              <p>
                Explore 50 connected segments in <strong>Raleigh</strong> (Piedmont Capital) and 50 segments in <strong>Asheville</strong> (Mountain
                Region impacted by mountain freeze-thaw and river flooding).
              </p>
            </div>
          </div>

          {/* Quick Guide */}
          <div className="arch-section">
            <h4 className="section-heading">How to Explore the Map</h4>
            <div className="explore-steps">
              <div className="explore-step">
                <span className="step-badge">1</span>
                <span>Click <strong>Asheville</strong> or <strong>Raleigh</strong> in the top bar to jump between regions.</span>
              </div>
              <div className="explore-step">
                <span className="step-badge">2</span>
                <span>Click any <strong>road segment line</strong> or open <strong>Roads List</strong> to inspect predictions.</span>
              </div>
              <div className="explore-step">
                <span className="step-badge">3</span>
                <span>Check the right panel for <strong>rating, pavement age, years to poor, flood rank, and aerial chip</strong>.</span>
              </div>
              <div className="explore-step">
                <span className="step-badge">4</span>
                <span>Use the <strong>Streets / Satellite / Dark</strong> buttons (bottom-right of map) to change basemap cartography.</span>
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <div className="footer-status">
            <ShieldCheck size={16} className="text-emerald-400" />
            <span>Ready for live prediction data and 112k+ PMTiles</span>
          </div>
          <button onClick={onClose} className="btn-primary">
            Start Exploring Map
          </button>
        </div>
      </div>
    </div>
  );
};
