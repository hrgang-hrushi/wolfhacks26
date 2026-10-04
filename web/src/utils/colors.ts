/**
 * Color utility for mapping 0.0 - 1.0 pavement condition scores
 * 0.0 = Critical / Immediate Repair Needed (Crimson)
 * 0.5 = Fair / Approaching Maintenance Window (Amber)
 * 1.0 = Optimal / Excellent New Pavement (Emerald)
 */

export function getScoreRGB(score?: number): [number, number, number] {
  const safeScore = (typeof score === 'number' && !isNaN(score)) ? score : 0.75;
  const s = Math.max(0, Math.min(1, safeScore));
  
  if (s < 0.25) {
    // Red [239, 68, 68] to Orange-Red [249, 115, 22]
    const t = s / 0.25;
    return [
      Math.round(239 + (249 - 239) * t),
      Math.round(68 + (115 - 68) * t),
      Math.round(68 + (22 - 68) * t)
    ];
  } else if (s < 0.5) {
    // Orange-Red [249, 115, 22] to Amber [245, 158, 11]
    const t = (s - 0.25) / 0.25;
    return [
      Math.round(249 + (245 - 249) * t),
      Math.round(115 + (158 - 115) * t),
      Math.round(22 + (11 - 22) * t)
    ];
  } else if (s < 0.75) {
    // Amber [245, 158, 11] to Lime [132, 204, 22]
    const t = (s - 0.5) / 0.25;
    return [
      Math.round(245 + (132 - 245) * t),
      Math.round(158 + (204 - 158) * t),
      Math.round(11 + (22 - 11) * t)
    ];
  } else {
    // Lime [132, 204, 22] to Emerald [16, 185, 129]
    const t = (s - 0.75) / 0.25;
    return [
      Math.round(132 + (16 - 132) * t),
      Math.round(204 + (185 - 204) * t),
      Math.round(22 + (129 - 22) * t)
    ];
  }
}

export function getScoreRGBA(score: number, alpha: number = 255): [number, number, number, number] {
  const [r, g, b] = getScoreRGB(score);
  return [r, g, b, alpha];
}

export function getScoreHex(score: number): string {
  const [r, g, b] = getScoreRGB(score);
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
}

export interface ConditionInfo {
  label: string;
  category: 'Critical' | 'Poor' | 'Fair' | 'Good' | 'Optimal';
  color: string;
  bgRgba: string;
  borderRgba: string;
}

export function getConditionInfo(score: number): ConditionInfo {
  const color = getScoreHex(score);
  const [r, g, b] = getScoreRGB(score);
  
  if (score < 0.3) {
    return {
      label: 'Critical Condition',
      category: 'Critical',
      color,
      bgRgba: `rgba(${r}, ${g}, ${b}, 0.15)`,
      borderRgba: `rgba(${r}, ${g}, ${b}, 0.4)`
    };
  } else if (score < 0.5) {
    return {
      label: 'Poor - Watchlist',
      category: 'Poor',
      color,
      bgRgba: `rgba(${r}, ${g}, ${b}, 0.15)`,
      borderRgba: `rgba(${r}, ${g}, ${b}, 0.4)`
    };
  } else if (score < 0.7) {
    return {
      label: 'Fair Condition',
      category: 'Fair',
      color,
      bgRgba: `rgba(${r}, ${g}, ${b}, 0.15)`,
      borderRgba: `rgba(${r}, ${g}, ${b}, 0.4)`
    };
  } else if (score < 0.85) {
    return {
      label: 'Good Condition',
      category: 'Good',
      color,
      bgRgba: `rgba(${r}, ${g}, ${b}, 0.15)`,
      borderRgba: `rgba(${r}, ${g}, ${b}, 0.4)`
    };
  } else {
    return {
      label: 'Optimal Condition',
      category: 'Optimal',
      color,
      bgRgba: `rgba(${r}, ${g}, ${b}, 0.15)`,
      borderRgba: `rgba(${r}, ${g}, ${b}, 0.4)`
    };
  }
}
