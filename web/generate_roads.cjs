const fs = require('fs');

const reasonPool = [
  'Heavy commercial truck volume (AADT > 4,800)',
  'Subgrade saturation & recurrent stormwater pooling',
  'Severe alligator fatigue cracking along wheel paths',
  'Thermal contraction & mountain freeze-thaw stripping',
  'Reflective cracking propagating from cement base',
  'Oxidative aging & micro-surface aggregate loss',
  'High turn-shear stress from transit & delivery fleets',
  'Stormwater culvert siltation & embankment erosion',
  'Hurricane Helene localized flood inundation surge',
  'Rutting depth exceeding 0.45 in. along outer lane',
  'Longitudinal joint separation & water infiltration',
  'High ESAL accumulation over 12-year service cycle'
];

const floodRanks = [
  'Zone AE (High Risk - 94th %ile)',
  'Zone A (Severe Inundation Potential)',
  'Zone A (Floodway Fringe - 82nd %ile)',
  'Zone X500 (Moderate - 500-Year)',
  'Zone X500 (Elevated Runoff - 68th %ile)',
  'Zone X (Minimal Risk - 12th %ile)',
  'Zone X (Low Ponding Risk)'
];

function Mulberry32(seed) {
  return function() {
    let t = seed += 0x6D2B79F5;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

const rng = Mulberry32(1337);

function makeCorridor(name, source, city, prefix, startId, coordsList) {
  const segments = [];
  for (let i = 0; i < coordsList.length - 1; i++) {
    const p1 = coordsList[i];
    const p2 = coordsList[i+1];
    const midLng = (p1[0] + p2[0]) / 2 + (rng() - 0.5) * 0.0004;
    const midLat = (p1[1] + p2[1]) / 2 + (rng() - 0.5) * 0.0004;
    const path = [
      [Math.round(p1[0] * 100000) / 100000, Math.round(p1[1] * 100000) / 100000],
      [Math.round(midLng * 100000) / 100000, Math.round(midLat * 100000) / 100000],
      [Math.round(p2[0] * 100000) / 100000, Math.round(p2[1] * 100000) / 100000]
    ];
    
    const idNum = String(startId + i).padStart(3, '0');
    const seg_id = prefix + '-' + idNum;
    
    const score = Math.round((0.15 + rng() * 0.80) * 100) / 100;
    const pv_rating = Math.max(15, Math.min(98, Math.round(score * 80 + 15 + (rng() - 0.5) * 6)));
    const pv_age = Math.round((1.0 + (1 - score) * 14 + rng() * 3.5) * 10) / 10;
    const years_to_poor = Math.round((score * 8.5 + rng() * 1.5) * 10) / 10;
    
    const fIdx = Math.floor(rng() * floodRanks.length);
    const flood_rank = floodRanks[fIdx];
    
    const shuffled = [...reasonPool].sort(() => rng() - 0.5);
    const drivers = [shuffled[0], shuffled[1], shuffled[2]];
    
    segments.push({
      seg_id,
      source,
      pv_rating,
      pv_age,
      years_to_poor,
      flood_rank,
      drivers,
      chip_url: '',
      path,
      score,
      name: name + ' (Seg ' + (i + 1) + ')',
      city
    });
  }
  return segments;
}

// Raleigh corridors (50 total)
const raleighSegments = [
  ...makeCorridor('Capital Blvd (US-401)', 'ncdot', 'Raleigh', 'NC-RAL', 1, [
    [-78.6380, 35.7820], [-78.6330, 35.7940], [-78.6250, 35.8080], [-78.6180, 35.8220], [-78.6100, 35.8360], [-78.6020, 35.8500]
  ]), // 5 segs (1-5)
  ...makeCorridor('Hillsborough St', 'city', 'Raleigh', 'NC-RAL', 6, [
    [-78.6380, 35.7800], [-78.6480, 35.7815], [-78.6590, 35.7840], [-78.6700, 35.7870], [-78.6810, 35.7890], [-78.6920, 35.7910]
  ]), // 5 segs (6-10)
  ...makeCorridor('Glenwood Ave (US-70)', 'ncdot', 'Raleigh', 'NC-RAL', 11, [
    [-78.6470, 35.7890], [-78.6530, 35.7990], [-78.6620, 35.8110], [-78.6700, 35.8230], [-78.6780, 35.8350], [-78.6880, 35.8470]
  ]), // 5 segs (11-15)
  ...makeCorridor('Fayetteville St', 'city', 'Raleigh', 'NC-RAL', 16, [
    [-78.6385, 35.7720], [-78.6382, 35.7750], [-78.6380, 35.7780], [-78.6378, 35.7810], [-78.6375, 35.7840], [-78.6372, 35.7870]
  ]), // 5 segs (16-20)
  ...makeCorridor('Wade Ave Corridor', 'ncdot', 'Raleigh', 'NC-RAL', 21, [
    [-78.6390, 35.7930], [-78.6510, 35.7970], [-78.6650, 35.8010], [-78.6780, 35.8050], [-78.6900, 35.8110], [-78.7020, 35.8180]
  ]), // 5 segs (21-25)
  ...makeCorridor('Western Blvd', 'ncdot', 'Raleigh', 'NC-RAL', 26, [
    [-78.6480, 35.7760], [-78.6610, 35.7780], [-78.6740, 35.7800], [-78.6870, 35.7820], [-78.7000, 35.7840], [-78.7130, 35.7860]
  ]), // 5 segs (26-30)
  ...makeCorridor('I-440 Beltline North', 'ncdot', 'Raleigh', 'NC-RAL', 31, [
    [-78.6950, 35.8150], [-78.6750, 35.8270], [-78.6500, 35.8320], [-78.6250, 35.8300], [-78.6080, 35.8220], [-78.5980, 35.8080], [-78.5920, 35.7920]
  ]), // 6 segs (31-36)
  ...makeCorridor('Six Forks Rd', 'city', 'Raleigh', 'NC-RAL', 37, [
    [-78.6420, 35.8180], [-78.6390, 35.8300], [-78.6350, 35.8420], [-78.6300, 35.8540], [-78.6240, 35.8660], [-78.6180, 35.8780]
  ]), // 5 segs (37-41)
  ...makeCorridor('New Bern Ave (US-64 Bus)', 'ncdot', 'Raleigh', 'NC-RAL', 42, [
    [-78.6320, 35.7810], [-78.6180, 35.7820], [-78.6040, 35.7830], [-78.5900, 35.7840], [-78.5760, 35.7850], [-78.5620, 35.7860]
  ]), // 5 segs (42-46)
  ...makeCorridor('Peace & Morgan St', 'city', 'Raleigh', 'NC-RAL', 47, [
    [-78.6520, 35.7895], [-78.6420, 35.7895], [-78.6320, 35.7895], [-78.6220, 35.7895], [-78.6120, 35.7895]
  ]) // 4 segs (47-50)
];

// Asheville corridors (50 total)
const ashevilleSegments = [
  ...makeCorridor('Patton Ave (US-19/23)', 'ncdot', 'Asheville', 'NC-AVL', 1, [
    [-82.5950, 35.5890], [-82.5820, 35.5910], [-82.5690, 35.5930], [-82.5590, 35.5945], [-82.5530, 35.5955], [-82.5480, 35.5965]
  ]), // 5 segs (1-5)
  ...makeCorridor('Tunnel Rd (US-70)', 'ncdot', 'Asheville', 'NC-AVL', 6, [
    [-82.5440, 35.5960], [-82.5320, 35.5940], [-82.5200, 35.5910], [-82.5080, 35.5870], [-82.4960, 35.5820], [-82.4840, 35.5760]
  ]), // 5 segs (6-10)
  ...makeCorridor('Biltmore Ave (US-25)', 'ncdot', 'Asheville', 'NC-AVL', 11, [
    [-82.5510, 35.5930], [-82.5480, 35.5840], [-82.5440, 35.5740], [-82.5400, 35.5630], [-82.5370, 35.5520], [-82.5340, 35.5410], [-82.5300, 35.5300]
  ]), // 6 segs (11-16)
  ...makeCorridor('Merrimon Ave (US-25 Bus)', 'ncdot', 'Asheville', 'NC-AVL', 17, [
    [-82.5530, 35.6000], [-82.5535, 35.6100], [-82.5540, 35.6200], [-82.5545, 35.6300], [-82.5550, 35.6400], [-82.5555, 35.6500]
  ]), // 5 segs (17-21)
  ...makeCorridor('I-240 Mountain Expressway', 'ncdot', 'Asheville', 'NC-AVL', 22, [
    [-82.5850, 35.5850], [-82.5700, 35.5910], [-82.5550, 35.6020], [-82.5420, 35.6060], [-82.5310, 35.6000], [-82.5220, 35.5900], [-82.5180, 35.5780]
  ]), // 6 segs (22-27)
  ...makeCorridor('Haywood & Broadway St', 'city', 'Asheville', 'NC-AVL', 28, [
    [-82.5570, 35.5920], [-82.5550, 35.5950], [-82.5530, 35.5980], [-82.5510, 35.6010], [-82.5490, 35.6040], [-82.5470, 35.6070], [-82.5450, 35.6100]
  ]), // 6 segs (28-33)
  ...makeCorridor('Riverside Dr & Lyman St', 'city', 'Asheville', 'NC-AVL', 34, [
    [-82.5780, 35.6080], [-82.5740, 35.5990], [-82.5700, 35.5910], [-82.5670, 35.5840], [-82.5640, 35.5780], [-82.5600, 35.5720], [-82.5550, 35.5660]
  ]), // 6 segs (34-39)
  ...makeCorridor('Montford & Charlotte St', 'city', 'Asheville', 'NC-AVL', 40, [
    [-82.5620, 35.6020], [-82.5580, 35.6070], [-82.5520, 35.6110], [-82.5450, 35.6130], [-82.5380, 35.6120], [-82.5320, 35.6090]
  ]), // 5 segs (40-44)
  ...makeCorridor('Swannanoa River Rd', 'city', 'Asheville', 'NC-AVL', 45, [
    [-82.5380, 35.5620], [-82.5260, 35.5650], [-82.5140, 35.5690], [-82.5020, 35.5730], [-82.4900, 35.5760], [-82.4780, 35.5790], [-82.4660, 35.5820]
  ]) // 6 segs (45-50)
];

const allSegments = [...raleighSegments, ...ashevilleSegments];
console.log('Raleigh count:', raleighSegments.length);
console.log('Asheville count:', ashevilleSegments.length);
console.log('Total count:', allSegments.length);
console.log('NCDOT count:', allSegments.filter(s => s.source === 'ncdot').length);
console.log('City count:', allSegments.filter(s => s.source === 'city').length);

const fileContent = 'import type { RoadSegment } from "../types/roadSegment";\n\n' +
  'export const MOCK_ROAD_SEGMENTS: RoadSegment[] = ' + JSON.stringify(allSegments, null, 2) + ';\n';

fs.writeFileSync('src/data/mockRoads.ts', fileContent, 'utf8');
console.log('Successfully wrote src/data/mockRoads.ts');
