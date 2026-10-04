import { lazy, Suspense } from 'react';
import { loadStats } from './lib/data';
import { googleConfigured } from './lib/mapTypes';
import { prefetchStart } from './mobile/start';

/** Phones and narrow windows get the judge dashboard; everything else gets the agency dashboard. */
const MOBILE_MAX_WIDTH = 820;

function route(): 'gov' | 'm' {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const path = window.location.pathname.slice(base.length).replace(/\/+$/, '');
  if (path === '/gov') return 'gov';
  if (path === '/m') return 'm';
  const target = window.innerWidth < MOBILE_MAX_WIDTH ? 'm' : 'gov';
  window.history.replaceState(null, '', `${base}/${target}${window.location.search}${window.location.hash}`);
  return target;
}

const page = route();

// Start the downloads the page will need while its own code is still loading.
if (page === 'm') {
  prefetchStart();
  if (!googleConfigured) void import('./lib/MapLibreDeck');
} else {
  void loadStats().catch(() => undefined);
}

const Page = lazy(page === 'gov' ? () => import('./gov/GovApp') : () => import('./mobile/MobileApp'));

export function App() {
  return (
    <Suspense fallback={<div className="boot">Loading Unwatched Roads…</div>}>
      <Page />
    </Suspense>
  );
}

export default App;
