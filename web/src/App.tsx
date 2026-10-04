import { lazy, Suspense } from 'react';
import { loadStats } from './lib/data';
import { googleConfigured } from './lib/mapTypes';
import { prefetchStart } from './mobile/start';

/** Phones and narrow windows get the judge dashboard; everything else gets the executive or agency dashboard. */
const MOBILE_MAX_WIDTH = 820;

function route(): 'dashboard' | 'gov' | 'm' {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const path = window.location.pathname.slice(base.length).replace(/\/+$/, '');
  if (path === '/gov') return 'gov';
  if (path === '/m') return 'm';
  if (path === '/dashboard') return 'dashboard';
  // Default to phone dashboard on narrow screens, executive dashboard on desktop
  const target = window.innerWidth < MOBILE_MAX_WIDTH ? 'm' : 'dashboard';
  return target;
}

const page = route();

// Start prefetching depending on the view
if (page === 'm') {
  prefetchStart();
  if (!googleConfigured) void import('./lib/MapLibreDeck');
} else if (page === 'gov') {
  void loadStats().catch(() => undefined);
}

const Page = lazy(() => {
  if (page === 'gov') return import('./gov/GovApp');
  if (page === 'm') return import('./mobile/MobileApp');
  return import('./components/ExecutiveDashboard');
});

export function App() {
  return (
    <Suspense fallback={<div className="boot">Loading RoadSense AI…</div>}>
      <Page />
    </Suspense>
  );
}

export default App;
