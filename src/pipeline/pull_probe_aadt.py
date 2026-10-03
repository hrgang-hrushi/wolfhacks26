"""Fill the traffic gap on secondary roads with NCDOT's 2023 estimated AADT.

Usage:  python -m src.pipeline.pull_probe_aadt            (pull, then attach)
        python -m src.pipeline.pull_probe_aadt --attach-only
Reads:  data/raw/ncdot_joined.parquet, data/raw/aadt_attached.parquet
Writes: data/raw/ncdot_aadt_probe_2023.parquet   NCDOT's estimate per short road piece (no geometry)
        data/raw/aadt_probe_attached.parquet     one row per seg_id, tr_ columns

NCDOT counts traffic on nearly every interstate and primary road but on about a third of secondary
roads. Its "probe estimated" layer gives a 2023 estimate, with a 95% range, for almost every road,
cut into short pieces. A segment's estimate is the mean of its pieces weighted by shared length.
The layer carries no description, so how NCDOT made the estimate is not stated; the check printed
at the end compares it with the real counts where a segment has both.

The estimate ranks roads much as the counts do but runs lower, and below about 100 vehicles a day
it stops telling roads apart. So for tr_aadt_best the estimate is first rescaled to the counts: a
rising curve fitted, per road system, on the segments that have both. On roads nobody counts this
is "what counted roads with the same estimate carry", which is likely too high for the quietest.

Columns written (prefix tr_):
  tr_aadt_est                      estimated vehicles a day, 2023
  tr_aadt_est_lo, tr_aadt_est_hi   the estimate's 95% range
  tr_aadt_est_cover                share of the segment's length that has an estimate (0 to 1)
  tr_aadt_est_scaled               the estimate rescaled to the counts (see above)
  tr_aadt_best                     the real count where one exists, otherwise the rescaled estimate
  tr_aadt_best_source              "count" | "estimate" | "none"
"""
import sys

import numpy as np
import pandas as pd

from src.pipeline.milepost import (AGOL, RAW, fetch_table, load_segments, overlaps, route_key, weighted_mean,
                                   write_atomic)

PROBE = f"{AGOL}/NCDOT_AADT_ProbeEstimated_2023/FeatureServer/0"
FIELDS = ["RouteID", "BegMP", "EndMP", "Estimated", "Lower_95_P", "Upper_95_P"]
EST = {"Estimated": "tr_aadt_est", "Lower_95_P": "tr_aadt_est_lo", "Upper_95_P": "tr_aadt_est_hi"}
MIN_PAIRS = 50


def rescale(est, count, group=None):
    """The estimate mapped onto the count scale by a rising curve (isotonic, in logs), fitted per
    group on the rows that have both. A group with too few such rows uses the all-rows curve; with
    too few rows overall the estimate is returned unchanged."""
    from sklearn.isotonic import IsotonicRegression
    both = est.notna() & count.notna() & (est > 0) & (count > 0)
    if both.sum() < MIN_PAIRS:
        return est.copy()

    def curve(rows):
        return IsotonicRegression(out_of_bounds="clip").fit(np.log10(est[rows]), np.log10(count[rows]))

    overall, out = curve(both), pd.Series(np.nan, index=est.index)
    group = pd.Series("all", index=est.index) if group is None else group.reindex(est.index)
    for g in group.dropna().unique():
        rows = (group == g) & est.notna()
        fit = curve(both & rows) if (both & rows).sum() >= MIN_PAIRS else overall
        out[rows] = 10 ** fit.predict(np.log10(est[rows]))
    return out


def attach(segs, probe, counts, group=None):
    """Length-weighted estimate per segment, then the best available number (count before estimate).
    `group` is an optional per-seg_id label (the road system) for the rescaling curves."""
    p = probe.assign(rid=route_key(probe.RouteID))
    p = p[p.Estimated > 0]                      # 0 means "no estimate"
    m = overlaps(segs, p, "BegMP", "EndMP")
    out = pd.DataFrame({new: weighted_mean(m, old) for old, new in EST.items()})
    # two pieces can cover the same stretch (one per direction), so cap the share at 1
    seg_mi = segs.set_index("seg_id").seg_mi
    out["tr_aadt_est_cover"] = (m.groupby("seg_id").ov.sum() / seg_mi.reindex(out.index)).clip(upper=1)
    out = out.reindex(segs.seg_id)
    out["tr_aadt_est_cover"] = out.tr_aadt_est_cover.fillna(0)
    out = out.reset_index().merge(counts[["seg_id", "tr_aadt"]], on="seg_id", how="left", validate="one_to_one")
    out["tr_aadt_est_scaled"] = rescale(out.tr_aadt_est, out.tr_aadt,
                                        None if group is None else out.seg_id.map(group))
    out["tr_aadt_best"] = out.tr_aadt.fillna(out.tr_aadt_est_scaled)
    out["tr_aadt_best_source"] = np.where(out.tr_aadt.notna(), "count",
                                          np.where(out.tr_aadt_est.notna(), "estimate", "none"))
    return out.drop(columns="tr_aadt")


def report(out, counts):
    n = len(out)
    print(f"\nsegments with an estimate: {out.tr_aadt_est.notna().sum():,}/{n:,} ({out.tr_aadt_est.notna().mean():.1%})")
    print(f"with a count or an estimate: {out.tr_aadt_best.notna().mean():.1%} (counts alone: "
          f"{counts.tr_aadt.notna().mean():.1%})")
    print(out.tr_aadt_best_source.value_counts().to_string())
    both = out.merge(counts[["seg_id", "tr_aadt"]], on="seg_id").dropna(subset=["tr_aadt", "tr_aadt_est"])
    ratio = both.tr_aadt_est / both.tr_aadt
    inside = both.tr_aadt.between(both.tr_aadt_est_lo, both.tr_aadt_est_hi)
    print(f"\nwhere a segment has both ({len(both):,}): rank agreement (Spearman) "
          f"{both.tr_aadt_est.corr(both.tr_aadt, method='spearman'):.3f}; estimate / count median "
          f"{ratio.median():.2f}, middle half {ratio.quantile(.25):.2f} to {ratio.quantile(.75):.2f}; "
          f"count inside the 95% range: {inside.mean():.1%}")
    r2 = both.tr_aadt_est_scaled / both.tr_aadt
    print(f"after rescaling: median {r2.median():.2f}, middle half {r2.quantile(.25):.2f} to {r2.quantile(.75):.2f}")
    no_count = out[out.tr_aadt_best_source == "estimate"]
    print(f"roads with only an estimate ({len(no_count):,}): median estimate {no_count.tr_aadt_est.median():.0f}, "
          f"rescaled {no_count.tr_aadt_est_scaled.median():.0f} vehicles a day")


def main(attach_only=False):
    if not attach_only:
        write_atomic(fetch_table(PROBE, FIELDS, workers=6), RAW / "ncdot_aadt_probe_2023.parquet")
    probe = pd.read_parquet(RAW / "ncdot_aadt_probe_2023.parquet")
    counts = pd.read_parquet(RAW / "aadt_attached.parquet")
    segs = load_segments()
    system = pd.read_parquet(RAW / "ncdot_joined.parquet", columns=["seg_id", "NC_SYSTEM_CODE"])
    out = attach(segs, probe, counts, group=system.set_index("seg_id").NC_SYSTEM_CODE)
    assert len(out) == len(segs) and out.seg_id.is_unique
    write_atomic(out, RAW / "aadt_probe_attached.parquet")
    report(out, counts)
    print("saved", RAW / "aadt_probe_attached.parquet", out.shape)


if __name__ == "__main__":
    main(attach_only="--attach-only" in sys.argv)
