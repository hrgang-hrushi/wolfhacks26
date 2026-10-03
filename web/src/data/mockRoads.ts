import type { RoadSegment } from "../types/roadSegment";

export const MOCK_ROAD_SEGMENTS: RoadSegment[] = [
  {
    "seg_id": "NC-RAL-001",
    "source": "ncdot",
    "pv_rating": 80,
    "pv_age": 5.3,
    "years_to_poor": 7.4,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "Oxidative aging & micro-surface aggregate loss",
      "Longitudinal joint separation & water infiltration"
    ],
    "chip_url": "",
    "path": [
      [
        -78.638,
        35.782
      ],
      [
        -78.63563,
        35.78788
      ],
      [
        -78.633,
        35.794
      ]
    ],
    "score": 0.8,
    "name": "Capital Blvd (US-401) (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-002",
    "source": "ncdot",
    "pv_rating": 54,
    "pv_age": 9,
    "years_to_poor": 4.3,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "Stormwater culvert siltation & embankment erosion",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -78.633,
        35.794
      ],
      [
        -78.62919,
        35.80103
      ],
      [
        -78.625,
        35.808
      ]
    ],
    "score": 0.5,
    "name": "Capital Blvd (US-401) (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-003",
    "source": "ncdot",
    "pv_rating": 61,
    "pv_age": 9.1,
    "years_to_poor": 6,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Rutting depth exceeding 0.45 in. along outer lane",
      "Stormwater culvert siltation & embankment erosion"
    ],
    "chip_url": "",
    "path": [
      [
        -78.625,
        35.808
      ],
      [
        -78.62161,
        35.81491
      ],
      [
        -78.618,
        35.822
      ]
    ],
    "score": 0.57,
    "name": "Capital Blvd (US-401) (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-004",
    "source": "ncdot",
    "pv_rating": 56,
    "pv_age": 10.1,
    "years_to_poor": 4.6,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Hurricane Helene localized flood inundation surge",
      "Longitudinal joint separation & water infiltration"
    ],
    "chip_url": "",
    "path": [
      [
        -78.618,
        35.822
      ],
      [
        -78.61405,
        35.82908
      ],
      [
        -78.61,
        35.836
      ]
    ],
    "score": 0.52,
    "name": "Capital Blvd (US-401) (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-005",
    "source": "ncdot",
    "pv_rating": 73,
    "pv_age": 6.8,
    "years_to_poor": 6.2,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Severe alligator fatigue cracking along wheel paths",
      "Hurricane Helene localized flood inundation surge"
    ],
    "chip_url": "",
    "path": [
      [
        -78.61,
        35.836
      ],
      [
        -78.60616,
        35.84292
      ],
      [
        -78.602,
        35.85
      ]
    ],
    "score": 0.71,
    "name": "Capital Blvd (US-401) (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-006",
    "source": "city",
    "pv_rating": 32,
    "pv_age": 13.8,
    "years_to_poor": 3.2,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Oxidative aging & micro-surface aggregate loss",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -78.638,
        35.78
      ],
      [
        -78.64319,
        35.78074
      ],
      [
        -78.648,
        35.7815
      ]
    ],
    "score": 0.2,
    "name": "Hillsborough St (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-007",
    "source": "city",
    "pv_rating": 78,
    "pv_age": 5.2,
    "years_to_poor": 7,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Severe alligator fatigue cracking along wheel paths",
      "High turn-shear stress from transit & delivery fleets",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -78.648,
        35.7815
      ],
      [
        -78.65331,
        35.78281
      ],
      [
        -78.659,
        35.784
      ]
    ],
    "score": 0.76,
    "name": "Hillsborough St (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-008",
    "source": "city",
    "pv_rating": 62,
    "pv_age": 10.2,
    "years_to_poor": 5.6,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Longitudinal joint separation & water infiltration",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.659,
        35.784
      ],
      [
        -78.66466,
        35.78549
      ],
      [
        -78.67,
        35.787
      ]
    ],
    "score": 0.59,
    "name": "Hillsborough St (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-009",
    "source": "city",
    "pv_rating": 42,
    "pv_age": 11.6,
    "years_to_poor": 3,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Hurricane Helene localized flood inundation surge",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -78.67,
        35.787
      ],
      [
        -78.6755,
        35.78813
      ],
      [
        -78.681,
        35.789
      ]
    ],
    "score": 0.33,
    "name": "Hillsborough St (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-010",
    "source": "city",
    "pv_rating": 79,
    "pv_age": 4.7,
    "years_to_poor": 7,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Longitudinal joint separation & water infiltration",
      "Stormwater culvert siltation & embankment erosion",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.681,
        35.789
      ],
      [
        -78.68654,
        35.78996
      ],
      [
        -78.692,
        35.791
      ]
    ],
    "score": 0.82,
    "name": "Hillsborough St (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-011",
    "source": "ncdot",
    "pv_rating": 47,
    "pv_age": 9.8,
    "years_to_poor": 5.1,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "High turn-shear stress from transit & delivery fleets",
      "Oxidative aging & micro-surface aggregate loss"
    ],
    "chip_url": "",
    "path": [
      [
        -78.647,
        35.789
      ],
      [
        -78.64996,
        35.79381
      ],
      [
        -78.653,
        35.799
      ]
    ],
    "score": 0.43,
    "name": "Glenwood Ave (US-70) (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-012",
    "source": "ncdot",
    "pv_rating": 62,
    "pv_age": 8.8,
    "years_to_poor": 6.3,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Severe alligator fatigue cracking along wheel paths",
      "Thermal contraction & mountain freeze-thaw stripping",
      "Hurricane Helene localized flood inundation surge"
    ],
    "chip_url": "",
    "path": [
      [
        -78.653,
        35.799
      ],
      [
        -78.65756,
        35.80484
      ],
      [
        -78.662,
        35.811
      ]
    ],
    "score": 0.6,
    "name": "Glenwood Ave (US-70) (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-013",
    "source": "ncdot",
    "pv_rating": 88,
    "pv_age": 5.1,
    "years_to_poor": 7.8,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "High turn-shear stress from transit & delivery fleets",
      "Thermal contraction & mountain freeze-thaw stripping",
      "Hurricane Helene localized flood inundation surge"
    ],
    "chip_url": "",
    "path": [
      [
        -78.662,
        35.811
      ],
      [
        -78.66582,
        35.81715
      ],
      [
        -78.67,
        35.823
      ]
    ],
    "score": 0.89,
    "name": "Glenwood Ave (US-70) (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-014",
    "source": "ncdot",
    "pv_rating": 83,
    "pv_age": 4.8,
    "years_to_poor": 7.7,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "High turn-shear stress from transit & delivery fleets",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.67,
        35.823
      ],
      [
        -78.67407,
        35.82918
      ],
      [
        -78.678,
        35.835
      ]
    ],
    "score": 0.88,
    "name": "Glenwood Ave (US-70) (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-015",
    "source": "ncdot",
    "pv_rating": 34,
    "pv_age": 13,
    "years_to_poor": 2.6,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Severe alligator fatigue cracking along wheel paths",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -78.678,
        35.835
      ],
      [
        -78.68293,
        35.84107
      ],
      [
        -78.688,
        35.847
      ]
    ],
    "score": 0.23,
    "name": "Glenwood Ave (US-70) (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-016",
    "source": "city",
    "pv_rating": 39,
    "pv_age": 12.1,
    "years_to_poor": 3.7,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "Heavy commercial truck volume (AADT > 4,800)",
      "Stormwater culvert siltation & embankment erosion",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.6385,
        35.772
      ],
      [
        -78.63849,
        35.77365
      ],
      [
        -78.6382,
        35.775
      ]
    ],
    "score": 0.33,
    "name": "Fayetteville St (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-017",
    "source": "city",
    "pv_rating": 57,
    "pv_age": 8.6,
    "years_to_poor": 4.7,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "High turn-shear stress from transit & delivery fleets",
      "Reflective cracking propagating from cement base",
      "Severe alligator fatigue cracking along wheel paths"
    ],
    "chip_url": "",
    "path": [
      [
        -78.6382,
        35.775
      ],
      [
        -78.63823,
        35.77635
      ],
      [
        -78.638,
        35.778
      ]
    ],
    "score": 0.51,
    "name": "Fayetteville St (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-018",
    "source": "city",
    "pv_rating": 74,
    "pv_age": 7.6,
    "years_to_poor": 6.7,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "High turn-shear stress from transit & delivery fleets",
      "Stormwater culvert siltation & embankment erosion",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -78.638,
        35.778
      ],
      [
        -78.63806,
        35.7795
      ],
      [
        -78.6378,
        35.781
      ]
    ],
    "score": 0.77,
    "name": "Fayetteville St (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-019",
    "source": "city",
    "pv_rating": 76,
    "pv_age": 5.6,
    "years_to_poor": 6.9,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Severe alligator fatigue cracking along wheel paths",
      "Subgrade saturation & recurrent stormwater pooling",
      "Oxidative aging & micro-surface aggregate loss"
    ],
    "chip_url": "",
    "path": [
      [
        -78.6378,
        35.781
      ],
      [
        -78.63782,
        35.78231
      ],
      [
        -78.6375,
        35.784
      ]
    ],
    "score": 0.74,
    "name": "Fayetteville St (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-020",
    "source": "city",
    "pv_rating": 68,
    "pv_age": 7.9,
    "years_to_poor": 7.2,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "High ESAL accumulation over 12-year service cycle",
      "Severe alligator fatigue cracking along wheel paths"
    ],
    "chip_url": "",
    "path": [
      [
        -78.6375,
        35.784
      ],
      [
        -78.63743,
        35.78565
      ],
      [
        -78.6372,
        35.787
      ]
    ],
    "score": 0.68,
    "name": "Fayetteville St (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-021",
    "source": "ncdot",
    "pv_rating": 65,
    "pv_age": 7,
    "years_to_poor": 6.1,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Severe alligator fatigue cracking along wheel paths",
      "Subgrade saturation & recurrent stormwater pooling",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -78.639,
        35.793
      ],
      [
        -78.64518,
        35.79501
      ],
      [
        -78.651,
        35.797
      ]
    ],
    "score": 0.62,
    "name": "Wade Ave Corridor (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-022",
    "source": "ncdot",
    "pv_rating": 81,
    "pv_age": 7.4,
    "years_to_poor": 8,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "Reflective cracking propagating from cement base",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -78.651,
        35.797
      ],
      [
        -78.65815,
        35.79919
      ],
      [
        -78.665,
        35.801
      ]
    ],
    "score": 0.79,
    "name": "Wade Ave Corridor (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-023",
    "source": "ncdot",
    "pv_rating": 29,
    "pv_age": 15.3,
    "years_to_poor": 3.1,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Subgrade saturation & recurrent stormwater pooling",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -78.665,
        35.801
      ],
      [
        -78.67162,
        35.80287
      ],
      [
        -78.678,
        35.805
      ]
    ],
    "score": 0.2,
    "name": "Wade Ave Corridor (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-024",
    "source": "ncdot",
    "pv_rating": 55,
    "pv_age": 10.1,
    "years_to_poor": 5.4,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Hurricane Helene localized flood inundation surge",
      "Heavy commercial truck volume (AADT > 4,800)"
    ],
    "chip_url": "",
    "path": [
      [
        -78.678,
        35.805
      ],
      [
        -78.68391,
        35.80798
      ],
      [
        -78.69,
        35.811
      ]
    ],
    "score": 0.47,
    "name": "Wade Ave Corridor (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-025",
    "source": "ncdot",
    "pv_rating": 65,
    "pv_age": 7.8,
    "years_to_poor": 5.7,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "High turn-shear stress from transit & delivery fleets",
      "Severe alligator fatigue cracking along wheel paths",
      "Heavy commercial truck volume (AADT > 4,800)"
    ],
    "chip_url": "",
    "path": [
      [
        -78.69,
        35.811
      ],
      [
        -78.69606,
        35.81453
      ],
      [
        -78.702,
        35.818
      ]
    ],
    "score": 0.62,
    "name": "Wade Ave Corridor (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-026",
    "source": "ncdot",
    "pv_rating": 65,
    "pv_age": 9.2,
    "years_to_poor": 5.4,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Longitudinal joint separation & water infiltration",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.648,
        35.776
      ],
      [
        -78.65456,
        35.77713
      ],
      [
        -78.661,
        35.778
      ]
    ],
    "score": 0.63,
    "name": "Western Blvd (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-027",
    "source": "ncdot",
    "pv_rating": 70,
    "pv_age": 5.9,
    "years_to_poor": 7.3,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "High ESAL accumulation over 12-year service cycle",
      "Longitudinal joint separation & water infiltration",
      "Heavy commercial truck volume (AADT > 4,800)"
    ],
    "chip_url": "",
    "path": [
      [
        -78.661,
        35.778
      ],
      [
        -78.6676,
        35.77901
      ],
      [
        -78.674,
        35.78
      ]
    ],
    "score": 0.72,
    "name": "Western Blvd (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-028",
    "source": "ncdot",
    "pv_rating": 71,
    "pv_age": 7.5,
    "years_to_poor": 5.9,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Longitudinal joint separation & water infiltration",
      "Hurricane Helene localized flood inundation surge",
      "Stormwater culvert siltation & embankment erosion"
    ],
    "chip_url": "",
    "path": [
      [
        -78.674,
        35.78
      ],
      [
        -78.68042,
        35.78081
      ],
      [
        -78.687,
        35.782
      ]
    ],
    "score": 0.68,
    "name": "Western Blvd (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-029",
    "source": "ncdot",
    "pv_rating": 48,
    "pv_age": 9.3,
    "years_to_poor": 4.1,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Longitudinal joint separation & water infiltration",
      "Thermal contraction & mountain freeze-thaw stripping",
      "High turn-shear stress from transit & delivery fleets"
    ],
    "chip_url": "",
    "path": [
      [
        -78.687,
        35.782
      ],
      [
        -78.69356,
        35.78284
      ],
      [
        -78.7,
        35.784
      ]
    ],
    "score": 0.43,
    "name": "Western Blvd (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-030",
    "source": "ncdot",
    "pv_rating": 87,
    "pv_age": 5.5,
    "years_to_poor": 9.2,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Severe alligator fatigue cracking along wheel paths",
      "Rutting depth exceeding 0.45 in. along outer lane",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -78.7,
        35.784
      ],
      [
        -78.70666,
        35.78493
      ],
      [
        -78.713,
        35.786
      ]
    ],
    "score": 0.92,
    "name": "Western Blvd (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-031",
    "source": "ncdot",
    "pv_rating": 92,
    "pv_age": 3.7,
    "years_to_poor": 8.9,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Thermal contraction & mountain freeze-thaw stripping",
      "Longitudinal joint separation & water infiltration"
    ],
    "chip_url": "",
    "path": [
      [
        -78.695,
        35.815
      ],
      [
        -78.68492,
        35.82096
      ],
      [
        -78.675,
        35.827
      ]
    ],
    "score": 0.93,
    "name": "I-440 Beltline North (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-032",
    "source": "ncdot",
    "pv_rating": 90,
    "pv_age": 4.7,
    "years_to_poor": 8.7,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Longitudinal joint separation & water infiltration",
      "Oxidative aging & micro-surface aggregate loss",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.675,
        35.827
      ],
      [
        -78.66244,
        35.8295
      ],
      [
        -78.65,
        35.832
      ]
    ],
    "score": 0.95,
    "name": "I-440 Beltline North (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-033",
    "source": "ncdot",
    "pv_rating": 70,
    "pv_age": 8.3,
    "years_to_poor": 6.6,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "High ESAL accumulation over 12-year service cycle",
      "Heavy commercial truck volume (AADT > 4,800)",
      "Subgrade saturation & recurrent stormwater pooling"
    ],
    "chip_url": "",
    "path": [
      [
        -78.65,
        35.832
      ],
      [
        -78.63754,
        35.83105
      ],
      [
        -78.625,
        35.83
      ]
    ],
    "score": 0.66,
    "name": "I-440 Beltline North (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-034",
    "source": "ncdot",
    "pv_rating": 72,
    "pv_age": 8.3,
    "years_to_poor": 6.2,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Oxidative aging & micro-surface aggregate loss",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -78.625,
        35.83
      ],
      [
        -78.61643,
        35.82589
      ],
      [
        -78.608,
        35.822
      ]
    ],
    "score": 0.71,
    "name": "I-440 Beltline North (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-035",
    "source": "ncdot",
    "pv_rating": 67,
    "pv_age": 8.3,
    "years_to_poor": 6.2,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Rutting depth exceeding 0.45 in. along outer lane",
      "Thermal contraction & mountain freeze-thaw stripping",
      "Heavy commercial truck volume (AADT > 4,800)"
    ],
    "chip_url": "",
    "path": [
      [
        -78.608,
        35.822
      ],
      [
        -78.60281,
        35.81508
      ],
      [
        -78.598,
        35.808
      ]
    ],
    "score": 0.67,
    "name": "I-440 Beltline North (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-036",
    "source": "ncdot",
    "pv_rating": 79,
    "pv_age": 5.3,
    "years_to_poor": 7.7,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "High turn-shear stress from transit & delivery fleets",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.598,
        35.808
      ],
      [
        -78.59497,
        35.80015
      ],
      [
        -78.592,
        35.792
      ]
    ],
    "score": 0.81,
    "name": "I-440 Beltline North (Seg 6)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-037",
    "source": "city",
    "pv_rating": 58,
    "pv_age": 11.3,
    "years_to_poor": 5.5,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "High turn-shear stress from transit & delivery fleets",
      "Hurricane Helene localized flood inundation surge"
    ],
    "chip_url": "",
    "path": [
      [
        -78.642,
        35.818
      ],
      [
        -78.6407,
        35.82383
      ],
      [
        -78.639,
        35.83
      ]
    ],
    "score": 0.51,
    "name": "Six Forks Rd (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-038",
    "source": "city",
    "pv_rating": 62,
    "pv_age": 9.9,
    "years_to_poor": 5.4,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Heavy commercial truck volume (AADT > 4,800)",
      "Severe alligator fatigue cracking along wheel paths",
      "Reflective cracking propagating from cement base"
    ],
    "chip_url": "",
    "path": [
      [
        -78.639,
        35.83
      ],
      [
        -78.63696,
        35.83593
      ],
      [
        -78.635,
        35.842
      ]
    ],
    "score": 0.59,
    "name": "Six Forks Rd (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-039",
    "source": "city",
    "pv_rating": 31,
    "pv_age": 13.3,
    "years_to_poor": 2.4,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Hurricane Helene localized flood inundation surge",
      "High turn-shear stress from transit & delivery fleets"
    ],
    "chip_url": "",
    "path": [
      [
        -78.635,
        35.842
      ],
      [
        -78.63257,
        35.84819
      ],
      [
        -78.63,
        35.854
      ]
    ],
    "score": 0.21,
    "name": "Six Forks Rd (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-040",
    "source": "city",
    "pv_rating": 51,
    "pv_age": 9.7,
    "years_to_poor": 4.4,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "High ESAL accumulation over 12-year service cycle",
      "Oxidative aging & micro-surface aggregate loss",
      "High turn-shear stress from transit & delivery fleets"
    ],
    "chip_url": "",
    "path": [
      [
        -78.63,
        35.854
      ],
      [
        -78.62698,
        35.85983
      ],
      [
        -78.624,
        35.866
      ]
    ],
    "score": 0.48,
    "name": "Six Forks Rd (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-041",
    "source": "city",
    "pv_rating": 74,
    "pv_age": 5.2,
    "years_to_poor": 7.4,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "Hurricane Helene localized flood inundation surge",
      "High turn-shear stress from transit & delivery fleets"
    ],
    "chip_url": "",
    "path": [
      [
        -78.624,
        35.866
      ],
      [
        -78.62101,
        35.87187
      ],
      [
        -78.618,
        35.878
      ]
    ],
    "score": 0.75,
    "name": "Six Forks Rd (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-042",
    "source": "ncdot",
    "pv_rating": 43,
    "pv_age": 12.2,
    "years_to_poor": 3.6,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "Stormwater culvert siltation & embankment erosion",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.632,
        35.781
      ],
      [
        -78.62487,
        35.78136
      ],
      [
        -78.618,
        35.782
      ]
    ],
    "score": 0.38,
    "name": "New Bern Ave (US-64 Bus) (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-043",
    "source": "ncdot",
    "pv_rating": 40,
    "pv_age": 10.7,
    "years_to_poor": 3.4,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Oxidative aging & micro-surface aggregate loss",
      "Hurricane Helene localized flood inundation surge"
    ],
    "chip_url": "",
    "path": [
      [
        -78.618,
        35.782
      ],
      [
        -78.61095,
        35.78242
      ],
      [
        -78.604,
        35.783
      ]
    ],
    "score": 0.31,
    "name": "New Bern Ave (US-64 Bus) (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-044",
    "source": "ncdot",
    "pv_rating": 32,
    "pv_age": 14.1,
    "years_to_poor": 2.8,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "High turn-shear stress from transit & delivery fleets",
      "High ESAL accumulation over 12-year service cycle",
      "Stormwater culvert siltation & embankment erosion"
    ],
    "chip_url": "",
    "path": [
      [
        -78.604,
        35.783
      ],
      [
        -78.5972,
        35.78359
      ],
      [
        -78.59,
        35.784
      ]
    ],
    "score": 0.21,
    "name": "New Bern Ave (US-64 Bus) (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-045",
    "source": "ncdot",
    "pv_rating": 37,
    "pv_age": 13.8,
    "years_to_poor": 3.5,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "High ESAL accumulation over 12-year service cycle",
      "Heavy commercial truck volume (AADT > 4,800)",
      "Subgrade saturation & recurrent stormwater pooling"
    ],
    "chip_url": "",
    "path": [
      [
        -78.59,
        35.784
      ],
      [
        -78.58288,
        35.78435
      ],
      [
        -78.576,
        35.785
      ]
    ],
    "score": 0.3,
    "name": "New Bern Ave (US-64 Bus) (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-046",
    "source": "ncdot",
    "pv_rating": 31,
    "pv_age": 15.2,
    "years_to_poor": 1.7,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "High ESAL accumulation over 12-year service cycle",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -78.576,
        35.785
      ],
      [
        -78.56905,
        35.78535
      ],
      [
        -78.562,
        35.786
      ]
    ],
    "score": 0.18,
    "name": "New Bern Ave (US-64 Bus) (Seg 5)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-047",
    "source": "city",
    "pv_rating": 57,
    "pv_age": 7.9,
    "years_to_poor": 5.7,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "Heavy commercial truck volume (AADT > 4,800)",
      "Subgrade saturation & recurrent stormwater pooling",
      "Oxidative aging & micro-surface aggregate loss"
    ],
    "chip_url": "",
    "path": [
      [
        -78.652,
        35.7895
      ],
      [
        -78.64709,
        35.78958
      ],
      [
        -78.642,
        35.7895
      ]
    ],
    "score": 0.52,
    "name": "Peace & Morgan St (Seg 1)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-048",
    "source": "city",
    "pv_rating": 65,
    "pv_age": 9.3,
    "years_to_poor": 5.5,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Stormwater culvert siltation & embankment erosion",
      "Longitudinal joint separation & water infiltration"
    ],
    "chip_url": "",
    "path": [
      [
        -78.642,
        35.7895
      ],
      [
        -78.63692,
        35.78939
      ],
      [
        -78.632,
        35.7895
      ]
    ],
    "score": 0.59,
    "name": "Peace & Morgan St (Seg 2)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-049",
    "source": "city",
    "pv_rating": 37,
    "pv_age": 14.1,
    "years_to_poor": 2.8,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Heavy commercial truck volume (AADT > 4,800)",
      "Longitudinal joint separation & water infiltration",
      "Stormwater culvert siltation & embankment erosion"
    ],
    "chip_url": "",
    "path": [
      [
        -78.632,
        35.7895
      ],
      [
        -78.62704,
        35.78961
      ],
      [
        -78.622,
        35.7895
      ]
    ],
    "score": 0.25,
    "name": "Peace & Morgan St (Seg 3)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-RAL-050",
    "source": "city",
    "pv_rating": 72,
    "pv_age": 7.4,
    "years_to_poor": 6.5,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Reflective cracking propagating from cement base",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -78.622,
        35.7895
      ],
      [
        -78.61698,
        35.78951
      ],
      [
        -78.612,
        35.7895
      ]
    ],
    "score": 0.74,
    "name": "Peace & Morgan St (Seg 4)",
    "city": "Raleigh"
  },
  {
    "seg_id": "NC-AVL-001",
    "source": "ncdot",
    "pv_rating": 30,
    "pv_age": 13.8,
    "years_to_poor": 2.6,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Oxidative aging & micro-surface aggregate loss",
      "Stormwater culvert siltation & embankment erosion"
    ],
    "chip_url": "",
    "path": [
      [
        -82.595,
        35.589
      ],
      [
        -82.5887,
        35.58995
      ],
      [
        -82.582,
        35.591
      ]
    ],
    "score": 0.21,
    "name": "Patton Ave (US-19/23) (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-002",
    "source": "ncdot",
    "pv_rating": 67,
    "pv_age": 6,
    "years_to_poor": 6.3,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Longitudinal joint separation & water infiltration",
      "Reflective cracking propagating from cement base"
    ],
    "chip_url": "",
    "path": [
      [
        -82.582,
        35.591
      ],
      [
        -82.57566,
        35.59183
      ],
      [
        -82.569,
        35.593
      ]
    ],
    "score": 0.66,
    "name": "Patton Ave (US-19/23) (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-003",
    "source": "ncdot",
    "pv_rating": 39,
    "pv_age": 13.4,
    "years_to_poor": 3.3,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Subgrade saturation & recurrent stormwater pooling",
      "Rutting depth exceeding 0.45 in. along outer lane",
      "Reflective cracking propagating from cement base"
    ],
    "chip_url": "",
    "path": [
      [
        -82.569,
        35.593
      ],
      [
        -82.56389,
        35.59357
      ],
      [
        -82.559,
        35.5945
      ]
    ],
    "score": 0.27,
    "name": "Patton Ave (US-19/23) (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-004",
    "source": "ncdot",
    "pv_rating": 36,
    "pv_age": 11.8,
    "years_to_poor": 3.5,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "High ESAL accumulation over 12-year service cycle",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -82.559,
        35.5945
      ],
      [
        -82.55584,
        35.59501
      ],
      [
        -82.553,
        35.5955
      ]
    ],
    "score": 0.28,
    "name": "Patton Ave (US-19/23) (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-005",
    "source": "ncdot",
    "pv_rating": 60,
    "pv_age": 9.5,
    "years_to_poor": 5.9,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "Subgrade saturation & recurrent stormwater pooling",
      "High turn-shear stress from transit & delivery fleets"
    ],
    "chip_url": "",
    "path": [
      [
        -82.553,
        35.5955
      ],
      [
        -82.55035,
        35.596
      ],
      [
        -82.548,
        35.5965
      ]
    ],
    "score": 0.55,
    "name": "Patton Ave (US-19/23) (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-006",
    "source": "ncdot",
    "pv_rating": 85,
    "pv_age": 5.1,
    "years_to_poor": 8.2,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "High turn-shear stress from transit & delivery fleets",
      "Oxidative aging & micro-surface aggregate loss"
    ],
    "chip_url": "",
    "path": [
      [
        -82.544,
        35.596
      ],
      [
        -82.53798,
        35.59495
      ],
      [
        -82.532,
        35.594
      ]
    ],
    "score": 0.85,
    "name": "Tunnel Rd (US-70) (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-007",
    "source": "ncdot",
    "pv_rating": 26,
    "pv_age": 13,
    "years_to_poor": 2.1,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "High turn-shear stress from transit & delivery fleets",
      "Longitudinal joint separation & water infiltration"
    ],
    "chip_url": "",
    "path": [
      [
        -82.532,
        35.594
      ],
      [
        -82.52588,
        35.59244
      ],
      [
        -82.52,
        35.591
      ]
    ],
    "score": 0.16,
    "name": "Tunnel Rd (US-70) (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-008",
    "source": "ncdot",
    "pv_rating": 83,
    "pv_age": 5.8,
    "years_to_poor": 7.4,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "Thermal contraction & mountain freeze-thaw stripping",
      "Oxidative aging & micro-surface aggregate loss"
    ],
    "chip_url": "",
    "path": [
      [
        -82.52,
        35.591
      ],
      [
        -82.51411,
        35.5891
      ],
      [
        -82.508,
        35.587
      ]
    ],
    "score": 0.87,
    "name": "Tunnel Rd (US-70) (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-009",
    "source": "ncdot",
    "pv_rating": 43,
    "pv_age": 10.7,
    "years_to_poor": 3.4,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Reflective cracking propagating from cement base",
      "Longitudinal joint separation & water infiltration"
    ],
    "chip_url": "",
    "path": [
      [
        -82.508,
        35.587
      ],
      [
        -82.502,
        35.58444
      ],
      [
        -82.496,
        35.582
      ]
    ],
    "score": 0.32,
    "name": "Tunnel Rd (US-70) (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-010",
    "source": "ncdot",
    "pv_rating": 75,
    "pv_age": 7.9,
    "years_to_poor": 7.2,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "High ESAL accumulation over 12-year service cycle",
      "Subgrade saturation & recurrent stormwater pooling",
      "Oxidative aging & micro-surface aggregate loss"
    ],
    "chip_url": "",
    "path": [
      [
        -82.496,
        35.582
      ],
      [
        -82.49019,
        35.57911
      ],
      [
        -82.484,
        35.576
      ]
    ],
    "score": 0.72,
    "name": "Tunnel Rd (US-70) (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-011",
    "source": "ncdot",
    "pv_rating": 69,
    "pv_age": 7.5,
    "years_to_poor": 6.1,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "Thermal contraction & mountain freeze-thaw stripping",
      "Heavy commercial truck volume (AADT > 4,800)"
    ],
    "chip_url": "",
    "path": [
      [
        -82.551,
        35.593
      ],
      [
        -82.54965,
        35.5885
      ],
      [
        -82.548,
        35.584
      ]
    ],
    "score": 0.66,
    "name": "Biltmore Ave (US-25) (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-012",
    "source": "ncdot",
    "pv_rating": 59,
    "pv_age": 7.2,
    "years_to_poor": 6.1,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Subgrade saturation & recurrent stormwater pooling",
      "High turn-shear stress from transit & delivery fleets",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -82.548,
        35.584
      ],
      [
        -82.54586,
        35.57909
      ],
      [
        -82.544,
        35.574
      ]
    ],
    "score": 0.58,
    "name": "Biltmore Ave (US-25) (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-013",
    "source": "ncdot",
    "pv_rating": 65,
    "pv_age": 9.4,
    "years_to_poor": 5.6,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "High ESAL accumulation over 12-year service cycle",
      "Hurricane Helene localized flood inundation surge"
    ],
    "chip_url": "",
    "path": [
      [
        -82.544,
        35.574
      ],
      [
        -82.54194,
        35.5683
      ],
      [
        -82.54,
        35.563
      ]
    ],
    "score": 0.59,
    "name": "Biltmore Ave (US-25) (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-014",
    "source": "ncdot",
    "pv_rating": 45,
    "pv_age": 12.9,
    "years_to_poor": 4.1,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "High turn-shear stress from transit & delivery fleets",
      "High ESAL accumulation over 12-year service cycle",
      "Severe alligator fatigue cracking along wheel paths"
    ],
    "chip_url": "",
    "path": [
      [
        -82.54,
        35.563
      ],
      [
        -82.53863,
        35.55747
      ],
      [
        -82.537,
        35.552
      ]
    ],
    "score": 0.35,
    "name": "Biltmore Ave (US-25) (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-015",
    "source": "ncdot",
    "pv_rating": 35,
    "pv_age": 11.8,
    "years_to_poor": 3.7,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Heavy commercial truck volume (AADT > 4,800)",
      "Rutting depth exceeding 0.45 in. along outer lane",
      "Reflective cracking propagating from cement base"
    ],
    "chip_url": "",
    "path": [
      [
        -82.537,
        35.552
      ],
      [
        -82.53568,
        35.54635
      ],
      [
        -82.534,
        35.541
      ]
    ],
    "score": 0.29,
    "name": "Biltmore Ave (US-25) (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-016",
    "source": "ncdot",
    "pv_rating": 67,
    "pv_age": 9.4,
    "years_to_poor": 5.5,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Longitudinal joint separation & water infiltration",
      "Subgrade saturation & recurrent stormwater pooling",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.534,
        35.541
      ],
      [
        -82.53203,
        35.53567
      ],
      [
        -82.53,
        35.53
      ]
    ],
    "score": 0.62,
    "name": "Biltmore Ave (US-25) (Seg 6)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-017",
    "source": "ncdot",
    "pv_rating": 30,
    "pv_age": 12.6,
    "years_to_poor": 2,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Heavy commercial truck volume (AADT > 4,800)",
      "Hurricane Helene localized flood inundation surge",
      "High turn-shear stress from transit & delivery fleets"
    ],
    "chip_url": "",
    "path": [
      [
        -82.553,
        35.6
      ],
      [
        -82.55342,
        35.60503
      ],
      [
        -82.5535,
        35.61
      ]
    ],
    "score": 0.19,
    "name": "Merrimon Ave (US-25 Bus) (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-018",
    "source": "ncdot",
    "pv_rating": 43,
    "pv_age": 11,
    "years_to_poor": 3.3,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "Thermal contraction & mountain freeze-thaw stripping",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -82.5535,
        35.61
      ],
      [
        -82.55368,
        35.61515
      ],
      [
        -82.554,
        35.62
      ]
    ],
    "score": 0.35,
    "name": "Merrimon Ave (US-25 Bus) (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-019",
    "source": "ncdot",
    "pv_rating": 68,
    "pv_age": 6.2,
    "years_to_poor": 6.4,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "High ESAL accumulation over 12-year service cycle",
      "Rutting depth exceeding 0.45 in. along outer lane",
      "Stormwater culvert siltation & embankment erosion"
    ],
    "chip_url": "",
    "path": [
      [
        -82.554,
        35.62
      ],
      [
        -82.55406,
        35.62482
      ],
      [
        -82.5545,
        35.63
      ]
    ],
    "score": 0.68,
    "name": "Merrimon Ave (US-25 Bus) (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-020",
    "source": "ncdot",
    "pv_rating": 49,
    "pv_age": 10.5,
    "years_to_poor": 4,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Rutting depth exceeding 0.45 in. along outer lane",
      "Oxidative aging & micro-surface aggregate loss",
      "Heavy commercial truck volume (AADT > 4,800)"
    ],
    "chip_url": "",
    "path": [
      [
        -82.5545,
        35.63
      ],
      [
        -82.5546,
        35.63487
      ],
      [
        -82.555,
        35.64
      ]
    ],
    "score": 0.41,
    "name": "Merrimon Ave (US-25 Bus) (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-021",
    "source": "ncdot",
    "pv_rating": 29,
    "pv_age": 14.2,
    "years_to_poor": 1.9,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "Stormwater culvert siltation & embankment erosion",
      "Longitudinal joint separation & water infiltration"
    ],
    "chip_url": "",
    "path": [
      [
        -82.555,
        35.64
      ],
      [
        -82.55541,
        35.64511
      ],
      [
        -82.5555,
        35.65
      ]
    ],
    "score": 0.18,
    "name": "Merrimon Ave (US-25 Bus) (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-022",
    "source": "ncdot",
    "pv_rating": 68,
    "pv_age": 6,
    "years_to_poor": 6.9,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "High turn-shear stress from transit & delivery fleets",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.585,
        35.585
      ],
      [
        -82.57766,
        35.58786
      ],
      [
        -82.57,
        35.591
      ]
    ],
    "score": 0.68,
    "name": "I-240 Mountain Expressway (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-023",
    "source": "ncdot",
    "pv_rating": 68,
    "pv_age": 6,
    "years_to_poor": 6.2,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "High turn-shear stress from transit & delivery fleets",
      "Reflective cracking propagating from cement base"
    ],
    "chip_url": "",
    "path": [
      [
        -82.57,
        35.591
      ],
      [
        -82.56245,
        35.59639
      ],
      [
        -82.555,
        35.602
      ]
    ],
    "score": 0.69,
    "name": "I-240 Mountain Expressway (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-024",
    "source": "ncdot",
    "pv_rating": 52,
    "pv_age": 11.9,
    "years_to_poor": 4.9,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Longitudinal joint separation & water infiltration",
      "Reflective cracking propagating from cement base",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -82.555,
        35.602
      ],
      [
        -82.54839,
        35.60406
      ],
      [
        -82.542,
        35.606
      ]
    ],
    "score": 0.45,
    "name": "I-240 Mountain Expressway (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-025",
    "source": "ncdot",
    "pv_rating": 58,
    "pv_age": 7.1,
    "years_to_poor": 5.9,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Heavy commercial truck volume (AADT > 4,800)",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -82.542,
        35.606
      ],
      [
        -82.53655,
        35.60296
      ],
      [
        -82.531,
        35.6
      ]
    ],
    "score": 0.57,
    "name": "I-240 Mountain Expressway (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-026",
    "source": "ncdot",
    "pv_rating": 49,
    "pv_age": 11.5,
    "years_to_poor": 4.9,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "High turn-shear stress from transit & delivery fleets",
      "Stormwater culvert siltation & embankment erosion"
    ],
    "chip_url": "",
    "path": [
      [
        -82.531,
        35.6
      ],
      [
        -82.52661,
        35.59483
      ],
      [
        -82.522,
        35.59
      ]
    ],
    "score": 0.41,
    "name": "I-240 Mountain Expressway (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-027",
    "source": "ncdot",
    "pv_rating": 60,
    "pv_age": 7.9,
    "years_to_poor": 5.2,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "High turn-shear stress from transit & delivery fleets",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.522,
        35.59
      ],
      [
        -82.52014,
        35.58386
      ],
      [
        -82.518,
        35.578
      ]
    ],
    "score": 0.54,
    "name": "I-240 Mountain Expressway (Seg 6)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-028",
    "source": "city",
    "pv_rating": 93,
    "pv_age": 4.3,
    "years_to_poor": 9.3,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "Oxidative aging & micro-surface aggregate loss",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -82.557,
        35.592
      ],
      [
        -82.55595,
        35.59354
      ],
      [
        -82.555,
        35.595
      ]
    ],
    "score": 0.95,
    "name": "Haywood & Broadway St (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-029",
    "source": "city",
    "pv_rating": 89,
    "pv_age": 5.5,
    "years_to_poor": 8,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Severe alligator fatigue cracking along wheel paths",
      "Reflective cracking propagating from cement base",
      "Oxidative aging & micro-surface aggregate loss"
    ],
    "chip_url": "",
    "path": [
      [
        -82.555,
        35.595
      ],
      [
        -82.55414,
        35.59635
      ],
      [
        -82.553,
        35.598
      ]
    ],
    "score": 0.9,
    "name": "Haywood & Broadway St (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-030",
    "source": "city",
    "pv_rating": 27,
    "pv_age": 14.3,
    "years_to_poor": 2.2,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Oxidative aging & micro-surface aggregate loss",
      "Heavy commercial truck volume (AADT > 4,800)"
    ],
    "chip_url": "",
    "path": [
      [
        -82.553,
        35.598
      ],
      [
        -82.55215,
        35.59932
      ],
      [
        -82.551,
        35.601
      ]
    ],
    "score": 0.18,
    "name": "Haywood & Broadway St (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-031",
    "source": "city",
    "pv_rating": 43,
    "pv_age": 13.1,
    "years_to_poor": 4.1,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "High turn-shear stress from transit & delivery fleets",
      "Reflective cracking propagating from cement base",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.551,
        35.601
      ],
      [
        -82.54981,
        35.60251
      ],
      [
        -82.549,
        35.604
      ]
    ],
    "score": 0.34,
    "name": "Haywood & Broadway St (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-032",
    "source": "city",
    "pv_rating": 62,
    "pv_age": 9.7,
    "years_to_poor": 5.3,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Severe alligator fatigue cracking along wheel paths",
      "Longitudinal joint separation & water infiltration"
    ],
    "chip_url": "",
    "path": [
      [
        -82.549,
        35.604
      ],
      [
        -82.54817,
        35.60546
      ],
      [
        -82.547,
        35.607
      ]
    ],
    "score": 0.62,
    "name": "Haywood & Broadway St (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-033",
    "source": "city",
    "pv_rating": 54,
    "pv_age": 10.3,
    "years_to_poor": 4.5,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Longitudinal joint separation & water infiltration",
      "High turn-shear stress from transit & delivery fleets",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.547,
        35.607
      ],
      [
        -82.54597,
        35.60835
      ],
      [
        -82.545,
        35.61
      ]
    ],
    "score": 0.49,
    "name": "Haywood & Broadway St (Seg 6)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-034",
    "source": "city",
    "pv_rating": 60,
    "pv_age": 9.9,
    "years_to_poor": 5.8,
    "flood_rank": "Zone A (Severe Inundation Potential)",
    "drivers": [
      "High ESAL accumulation over 12-year service cycle",
      "Heavy commercial truck volume (AADT > 4,800)",
      "Subgrade saturation & recurrent stormwater pooling"
    ],
    "chip_url": "",
    "path": [
      [
        -82.578,
        35.608
      ],
      [
        -82.57611,
        35.60352
      ],
      [
        -82.574,
        35.599
      ]
    ],
    "score": 0.56,
    "name": "Riverside Dr & Lyman St (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-035",
    "source": "city",
    "pv_rating": 76,
    "pv_age": 7.5,
    "years_to_poor": 6.7,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Hurricane Helene localized flood inundation surge",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.574,
        35.599
      ],
      [
        -82.57218,
        35.59482
      ],
      [
        -82.57,
        35.591
      ]
    ],
    "score": 0.75,
    "name": "Riverside Dr & Lyman St (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-036",
    "source": "city",
    "pv_rating": 60,
    "pv_age": 8.7,
    "years_to_poor": 5.9,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "High turn-shear stress from transit & delivery fleets",
      "Rutting depth exceeding 0.45 in. along outer lane"
    ],
    "chip_url": "",
    "path": [
      [
        -82.57,
        35.591
      ],
      [
        -82.56857,
        35.58746
      ],
      [
        -82.567,
        35.584
      ]
    ],
    "score": 0.54,
    "name": "Riverside Dr & Lyman St (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-037",
    "source": "city",
    "pv_rating": 34,
    "pv_age": 11.8,
    "years_to_poor": 3.4,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Thermal contraction & mountain freeze-thaw stripping",
      "Oxidative aging & micro-surface aggregate loss"
    ],
    "chip_url": "",
    "path": [
      [
        -82.567,
        35.584
      ],
      [
        -82.56549,
        35.58118
      ],
      [
        -82.564,
        35.578
      ]
    ],
    "score": 0.25,
    "name": "Riverside Dr & Lyman St (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-038",
    "source": "city",
    "pv_rating": 35,
    "pv_age": 14.9,
    "years_to_poor": 2.1,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "High ESAL accumulation over 12-year service cycle",
      "Heavy commercial truck volume (AADT > 4,800)"
    ],
    "chip_url": "",
    "path": [
      [
        -82.564,
        35.578
      ],
      [
        -82.56194,
        35.57489
      ],
      [
        -82.56,
        35.572
      ]
    ],
    "score": 0.24,
    "name": "Riverside Dr & Lyman St (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-039",
    "source": "city",
    "pv_rating": 52,
    "pv_age": 11,
    "years_to_poor": 4.8,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "High ESAL accumulation over 12-year service cycle",
      "Hurricane Helene localized flood inundation surge",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -82.56,
        35.572
      ],
      [
        -82.55763,
        35.56914
      ],
      [
        -82.555,
        35.566
      ]
    ],
    "score": 0.47,
    "name": "Riverside Dr & Lyman St (Seg 6)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-040",
    "source": "city",
    "pv_rating": 35,
    "pv_age": 14.2,
    "years_to_poor": 3.3,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Heavy commercial truck volume (AADT > 4,800)",
      "Hurricane Helene localized flood inundation surge"
    ],
    "chip_url": "",
    "path": [
      [
        -82.562,
        35.602
      ],
      [
        -82.55981,
        35.60453
      ],
      [
        -82.558,
        35.607
      ]
    ],
    "score": 0.26,
    "name": "Montford & Charlotte St (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-041",
    "source": "city",
    "pv_rating": 71,
    "pv_age": 7.9,
    "years_to_poor": 7.1,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "Severe alligator fatigue cracking along wheel paths",
      "Subgrade saturation & recurrent stormwater pooling"
    ],
    "chip_url": "",
    "path": [
      [
        -82.558,
        35.607
      ],
      [
        -82.55499,
        35.6092
      ],
      [
        -82.552,
        35.611
      ]
    ],
    "score": 0.66,
    "name": "Montford & Charlotte St (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-042",
    "source": "city",
    "pv_rating": 49,
    "pv_age": 11.6,
    "years_to_poor": 4.6,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "Thermal contraction & mountain freeze-thaw stripping",
      "Severe alligator fatigue cracking along wheel paths",
      "Reflective cracking propagating from cement base"
    ],
    "chip_url": "",
    "path": [
      [
        -82.552,
        35.611
      ],
      [
        -82.54856,
        35.61217
      ],
      [
        -82.545,
        35.613
      ]
    ],
    "score": 0.45,
    "name": "Montford & Charlotte St (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-043",
    "source": "city",
    "pv_rating": 58,
    "pv_age": 9.7,
    "years_to_poor": 5.1,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Stormwater culvert siltation & embankment erosion",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.545,
        35.613
      ],
      [
        -82.5414,
        35.61236
      ],
      [
        -82.538,
        35.612
      ]
    ],
    "score": 0.53,
    "name": "Montford & Charlotte St (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-044",
    "source": "city",
    "pv_rating": 69,
    "pv_age": 7.1,
    "years_to_poor": 6.4,
    "flood_rank": "Zone A (Floodway Fringe - 82nd %ile)",
    "drivers": [
      "Hurricane Helene localized flood inundation surge",
      "Reflective cracking propagating from cement base",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.538,
        35.612
      ],
      [
        -82.5349,
        35.61038
      ],
      [
        -82.532,
        35.609
      ]
    ],
    "score": 0.67,
    "name": "Montford & Charlotte St (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-045",
    "source": "city",
    "pv_rating": 27,
    "pv_age": 15.7,
    "years_to_poor": 2,
    "flood_rank": "Zone X (Low Ponding Risk)",
    "drivers": [
      "Longitudinal joint separation & water infiltration",
      "Reflective cracking propagating from cement base",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -82.538,
        35.562
      ],
      [
        -82.53198,
        35.56365
      ],
      [
        -82.526,
        35.565
      ]
    ],
    "score": 0.18,
    "name": "Swannanoa River Rd (Seg 1)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-046",
    "source": "city",
    "pv_rating": 67,
    "pv_age": 7.6,
    "years_to_poor": 5.7,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "Stormwater culvert siltation & embankment erosion",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.526,
        35.565
      ],
      [
        -82.52011,
        35.56718
      ],
      [
        -82.514,
        35.569
      ]
    ],
    "score": 0.65,
    "name": "Swannanoa River Rd (Seg 2)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-047",
    "source": "city",
    "pv_rating": 65,
    "pv_age": 8,
    "years_to_poor": 6.7,
    "flood_rank": "Zone X500 (Moderate - 500-Year)",
    "drivers": [
      "High turn-shear stress from transit & delivery fleets",
      "Longitudinal joint separation & water infiltration",
      "Stormwater culvert siltation & embankment erosion"
    ],
    "chip_url": "",
    "path": [
      [
        -82.514,
        35.569
      ],
      [
        -82.50812,
        35.57106
      ],
      [
        -82.502,
        35.573
      ]
    ],
    "score": 0.61,
    "name": "Swannanoa River Rd (Seg 3)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-048",
    "source": "city",
    "pv_rating": 28,
    "pv_age": 12.9,
    "years_to_poor": 2.7,
    "flood_rank": "Zone X500 (Elevated Runoff - 68th %ile)",
    "drivers": [
      "Oxidative aging & micro-surface aggregate loss",
      "Stormwater culvert siltation & embankment erosion",
      "High ESAL accumulation over 12-year service cycle"
    ],
    "chip_url": "",
    "path": [
      [
        -82.502,
        35.573
      ],
      [
        -82.49592,
        35.57444
      ],
      [
        -82.49,
        35.576
      ]
    ],
    "score": 0.18,
    "name": "Swannanoa River Rd (Seg 4)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-049",
    "source": "city",
    "pv_rating": 83,
    "pv_age": 3.3,
    "years_to_poor": 8.2,
    "flood_rank": "Zone AE (High Risk - 94th %ile)",
    "drivers": [
      "Reflective cracking propagating from cement base",
      "Longitudinal joint separation & water infiltration",
      "Thermal contraction & mountain freeze-thaw stripping"
    ],
    "chip_url": "",
    "path": [
      [
        -82.49,
        35.576
      ],
      [
        -82.48397,
        35.5777
      ],
      [
        -82.478,
        35.579
      ]
    ],
    "score": 0.86,
    "name": "Swannanoa River Rd (Seg 5)",
    "city": "Asheville"
  },
  {
    "seg_id": "NC-AVL-050",
    "source": "city",
    "pv_rating": 72,
    "pv_age": 6,
    "years_to_poor": 6.9,
    "flood_rank": "Zone X (Minimal Risk - 12th %ile)",
    "drivers": [
      "Stormwater culvert siltation & embankment erosion",
      "High ESAL accumulation over 12-year service cycle",
      "Subgrade saturation & recurrent stormwater pooling"
    ],
    "chip_url": "",
    "path": [
      [
        -82.478,
        35.579
      ],
      [
        -82.4722,
        35.58031
      ],
      [
        -82.466,
        35.582
      ]
    ],
    "score": 0.72,
    "name": "Swannanoa River Rd (Seg 6)",
    "city": "Asheville"
  }
];
