/**
 * Real facts about a road for the executive dashboard: its route, county and milepost read from
 * its id, and its NCDOT record from the same data files /gov uses. Nothing here is made up; a
 * fact that is not on record comes back as null.
 */
import { useEffect, useState } from 'react';
import { CLASS_LABEL, loadDetail, loadStats, parseId, routeName, type Detail } from '../lib/data';
import type { RoadSegment } from '../types/roadSegment';

/** North Carolina's counties in NCDOT code order (001 Alamance to 100 Yancey). */
export const NC_COUNTIES = [
  'Alamance', 'Alexander', 'Alleghany', 'Anson', 'Ashe', 'Avery', 'Beaufort', 'Bertie', 'Bladen', 'Brunswick',
  'Buncombe', 'Burke', 'Cabarrus', 'Caldwell', 'Camden', 'Carteret', 'Caswell', 'Catawba', 'Chatham', 'Cherokee',
  'Chowan', 'Clay', 'Cleveland', 'Columbus', 'Craven', 'Cumberland', 'Currituck', 'Dare', 'Davidson', 'Davie',
  'Duplin', 'Durham', 'Edgecombe', 'Forsyth', 'Franklin', 'Gaston', 'Gates', 'Graham', 'Granville', 'Greene',
  'Guilford', 'Halifax', 'Harnett', 'Haywood', 'Henderson', 'Hertford', 'Hoke', 'Hyde', 'Iredell', 'Jackson',
  'Johnston', 'Jones', 'Lee', 'Lenoir', 'Lincoln', 'Macon', 'Madison', 'Martin', 'McDowell', 'Mecklenburg',
  'Mitchell', 'Montgomery', 'Moore', 'Nash', 'New Hanover', 'Northampton', 'Onslow', 'Orange', 'Pamlico',
  'Pasquotank', 'Pender', 'Perquimans', 'Person', 'Pitt', 'Polk', 'Randolph', 'Richmond', 'Robeson', 'Rockingham',
  'Rowan', 'Rutherford', 'Sampson', 'Scotland', 'Stanly', 'Stokes', 'Surry', 'Swain', 'Transylvania', 'Tyrrell',
  'Union', 'Vance', 'Wake', 'Warren', 'Washington', 'Watauga', 'Wayne', 'Wilkes', 'Wilson', 'Yadkin', 'Yancey',
];

/** State road ids look like `ncdot:20000013008:0.141`. */
export function isStateRoadId(segId: string): boolean {
  return /^ncdot:\d{11}:/.test(segId);
}

export function countyOfId(segId: string): string | null {
  if (!isStateRoadId(segId)) return null;
  return NC_COUNTIES[parseInt(parseId(segId).cty, 10) - 1] ?? null;
}

/** "US 13, Bertie County (mp 0.14)". null when the id is not a state road id. */
export function realRoadName(segId: string): string | null {
  if (!isStateRoadId(segId)) return null;
  const county = countyOfId(segId);
  const mp = parseId(segId).mp;
  return `${routeName(segId)}${county ? `, ${county} County` : ''}${Number.isFinite(mp) ? ` (mp ${mp.toFixed(2)})` : ''}`;
}

/** "Interstate", "US route", "NC route" or "Secondary road". */
export function routeClassOf(segId: string): string | null {
  return isStateRoadId(segId) ? CLASS_LABEL[parseId(segId).cls] : null;
}

/** The road's NCDOT record (traffic, resurfacing year, rating, treatment). null while loading or when there is none. */
export function useRoadRecord(seg: RoadSegment | null): Detail | null {
  const [state, setState] = useState<{ id: string; detail: Detail | null }>({ id: '', detail: null });
  const id = seg?.seg_id ?? '';
  useEffect(() => {
    if (!seg || !isStateRoadId(seg.seg_id) || !seg.path?.length) return;
    let live = true;
    loadStats()
      .then((stats) => loadDetail({ id: seg.seg_id, paths: [seg.path.flat()] }, stats))
      .then((detail) => live && setState({ id: seg.seg_id, detail }))
      .catch(() => live && setState({ id: seg.seg_id, detail: null }));
    return () => {
      live = false;
    };
    // The record depends on the road, not on the object that carries it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  return state.id === id ? state.detail : null;
}
