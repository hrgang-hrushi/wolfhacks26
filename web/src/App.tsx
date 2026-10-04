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
  // Default to phone dashboard on narrow screens, agency dashboard on desktop
  const target = window.innerWidth < MOBILE_MAX_WIDTH ? 'm' : 'gov';
  window.history.replaceState(null, '', `${base}/${target}${window.location.search}${window.location.hash}`);
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

// One loader per page, each in its own function. With all three import() calls in a single
// function, the production build attaches only the dashboard's stylesheet list to them, so
// /gov and /m ship without their CSS (the dev server is unaffected).
const loaders = {
  gov: () => import('./gov/GovApp'),
  m: () => import('./mobile/MobileApp'),
  dashboard: () => import('./components/ExecutiveDashboard'),
};

const Page = lazy(loaders[page]);

export function App() {
  return (
    <Suspense fallback={<div className="boot">Loading RoadSense AI…</div>}>
      <Page />
    </Suspense>
  );
}

export default App;
