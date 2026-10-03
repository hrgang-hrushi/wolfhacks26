1. **Critical** — Fixture runs can overwrite the tracked map artifact. Step 4 writes to `handoff/predictions_geo.parquet` independently of `p`, while S3/S4 supply fixture geometry. Make the handoff destination injectable and direct tests into `tmp_path`. Verify the GeoParquet CRS, schema, segment coverage, and held-out flags.

2. **Critical** — R4 cannot pass as specified: `PV` will include `pv_age_at_survey`, but that derived column does not exist in `segments.parquet`, and the pipeline is explicitly unchanged. Check baseline feature availability after `add_targets`, and separately check the raw columns required to derive targets.

3. **Critical** — Sparse subsets remain unsafe. The copied `oof` skips folds with no training rows, leaving masked predictions null; `final_ablation.evaluate` then passes them to metrics. An existing embedding file with no matching segments also produces empty rate/cracking inputs. Define explicit handling for empty subsets, labels confined to one fold, and single-class classification training sets. Test these cases and never substitute full-model predictions while marking them held out.

4. **Critical** — Step 4 omits part of D11: the existing `final_ablation.evaluate` neither reports `rate_mae_naive` nor applies the Spearman tripwire. Add both explicitly to every final-ablation row, using that row’s subset mask, and verify them in S3/S4.

5. **Suggestion** — Embedding and geometry merges lack cardinality checks. Duplicate `seg_id` values can multiply rows, distort metrics, or duplicate map features. Require unique keys and validated one-to-one left joins, assert segment coverage, and add duplicate-key tests.

6. **Suggestion** — O5 conflicts with the new feature guard: a leakage demonstration using rating cannot pass through `prep`, which must reject rating. Specify an isolated direct-estimator demonstration, alongside a separate assertion that the production preparation path rejects those inputs.

7. **Suggestion** — Step 9 can invalidate the recorded real-data results. If the final pull changes model logic or feature generation, rerunning only fast tests leaves committed metrics and predictions associated with earlier code. Require regeneration and relevant acceptance checks whenever upstream changes affect those outputs.
