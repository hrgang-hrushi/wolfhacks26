/**
 * Text taken from README.md, so both dashboards say the same thing the repo says.
 * The headline numbers themselves come from stats.json (readme_metrics), which the
 * build script copies from the README with the source noted.
 */

export const TAGLINE = 'Which NC roads fail next, even the ones nobody inspects';

export const SCOPE_NOTE =
  'State-maintained roads only (112,443 NCDOT stretches). City streets are not scored.';

/** README.md, "What we cannot claim". */
export const CANNOT_CLAIM: { head: string; body: string }[] = [
  {
    head: 'It is one snapshot.',
    body: 'The state publishes one inspection per road, with no history. Wear per year is rating lost divided by age, not a measured trend.',
  },
  {
    head: 'Flood risk comes from one storm.',
    body: 'The model learned what Helene damaged in western North Carolina. Another storm could behave differently.',
  },
  {
    head: 'City streets are not scored yet.',
    body: 'Only state roads have ratings to learn from, so a city-street score would be borrowed from state roads and could not be checked the same way.',
  },
  {
    head: 'Traffic counts are thin.',
    body: 'About 48% of roads have a real count.',
  },
  {
    head: 'The photos are older than the inspections.',
    body: 'They are from 2022; most inspections are from 2025.',
  },
];

/** README.md, data line. */
export const DATA_SOURCES: string[] = [
  'NCDOT Pavement Condition Survey (ratings, age, recommended treatment and cost)',
  'USGS 3DEP elevation (the shape of the land)',
  'USDA NAIP 2022 aerial imagery (tested; has not improved the predictions)',
  'Hurricane Helene damage records from NCDOT, the NC Geological Survey and USGS',
];

/** README.md, "Does it work?": what the model reads. Used for the honest "Why" line. */
export const MODEL_INPUTS =
  'The model reads three kinds of input: the inspection record (surface age, road type), traffic, and the shape of the land (elevation, slope, how low the road sits). It does not report which one mattered most for a single road.';

export const HELDOUT_EXPLAIN =
  'Held-out: this number came from a model trained without this road or any road in its 5 km square.';

export const INSAMPLE_EXPLAIN =
  'In-sample: this road had no label to hold out, so the number comes from the model fitted on all labelled roads.';

export const NEGATIVE_RATE_NOTE = 'Predicted wear below zero is shown as 0.';
