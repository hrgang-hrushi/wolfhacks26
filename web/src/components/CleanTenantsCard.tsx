import React from 'react';
import type { RoadSegment } from '../types/roadSegment';
import { Gauge } from './Gauge';

interface CleanTenantsCardProps {
  selectedSegment: RoadSegment | null;
  onOpenNetworkStats?: () => void;
}

export const CleanTenantsCard: React.FC<CleanTenantsCardProps> = ({
  selectedSegment,
  onOpenNetworkStats
}) => {
  const seg = selectedSegment;
  const isBuncombe = seg?.city === 'Asheville' || (seg?.seg_id && seg.seg_id.includes('buncombe'));
  const divisionName = isBuncombe ? 'NCDOT Division 13 (Western/Helene)' : 'NCDOT Division 5 (Central)';

  return (
    <div
      className="pixel-tenants-card live-html-card"
      onClick={onOpenNetworkStats}
      style={{ cursor: 'pointer' }}
    >
      <div className="tenants-card-inner">
        {/* Clean Auto-Layout Header */}
        <div className="tenants-header-row">
          <div className="tenants-title-cluster" style={{ width: '100%' }}>
            <span className="agency-division-label">
              {divisionName} • Active Dispatch
            </span>
            <h2 className="tenants-title">Agency Operations</h2>
            <p className="tenants-subtitle">
              Active highway patrol &amp; rapid repair dispatch
            </p>
          </div>
        </div>

        {/* 110% Pixel-to-Pixel Cloned Gauge - Royal Fleet Blue (#2563eb) */}
        <div className="tenants-gauge-area">
          <Gauge
            centerValue={428_000}
            defaultLabel="ARR run rate"
            formatOptions={{ style: "currency", currency: "USD", maximumFractionDigits: 0 }}
            inactiveFillOpacity={0.7}
            notchCornerRadius={1.2}
            notchLengthPercent={100}
            spacing={25}
            value={66}
            size={230}
            activeColor="#2563eb"
            inactiveColor="#e2e8f0"
            valueColor="#0f172a"
            labelColor="#64748b"
          />
        </div>

        {/* Clean Auto-Layout Footer Telemetry Matching Royal Fleet Blue Theme */}
        <div className="agency-footer-telemetry">
          <span className="agency-footer-note">
            Trending up by <strong style={{ color: '#2563eb' }}>5.2%</strong> this month
          </span>
          <span className="agency-footer-readiness">
            14 Crews • <strong style={{ color: '#2563eb' }}>94% Ready</strong>
          </span>
        </div>
      </div>
    </div>
  );
};
