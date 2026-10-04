import { useEffect, useState } from 'react';
import { loadDetail, type Detail, type Seg, type Stats } from './data';

/** The NCDOT record for one road, fetched when the road is opened. */
export function useDetail(seg: Seg | null, stats: Stats | null): Detail | null {
  const [state, setState] = useState<{ id: string; detail: Detail | null }>({ id: '', detail: null });
  useEffect(() => {
    if (!seg || !stats) return;
    let live = true;
    loadDetail(seg, stats)
      .then((d) => live && setState({ id: seg.id, detail: d }))
      .catch(() => live && setState({ id: seg.id, detail: null }));
    return () => {
      live = false;
    };
  }, [seg, stats]);
  return seg && state.id === seg.id ? state.detail : null;
}

export function useMediaQuery(query: string): boolean {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [query]);
  return match;
}
