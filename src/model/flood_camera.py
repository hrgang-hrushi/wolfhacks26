"""Flood depth on the road from a roadside-camera frame: DINOv2 ViT-S/14, frozen or fine-tuned.

  python -m src.model.flood_camera --frozen            # embeddings + ridge/logistic; minutes on a laptop
  python -m src.model.flood_camera --epochs 6          # fine-tune; wants a GPU (Colab T4 is enough)
  --split camera   hold out whole camera sites (default)      --split day   hold out whole days
  --data DIR --out DIR                                 # defaults: data/raw/sunnyday, data/processed
  --size 336                                           # smaller frames: what an 18 GB Mac can fine-tune (448 cannot)
Reads:  {data}/labels.parquet and the frames it lists (python -m src.pipeline.sunnyday --labels)
Writes: {out}/flood_camera_oof_{frozen|finetune}_{split}.parquet   held-out prediction per frame
        {out}/flood_camera_metrics_{frozen|finetune}_{split}.json
        {out}/flood_camera_vits14.pt                               --final only: weights trained on every frame
  python -m src.model.flood_camera --export            # no training: best held-out-camera run on disk ->
        {out}/flood_camera_depth.parquet                 one row per frame, with seg_id where the camera sits on
                                                         an NCDOT segment
        {out}/flood_camera_summary.json                  the four runs side by side; null = not run

Rows with role == "extra" (e.g. NCDOT stills, all known dry) are never trained on; --final scores them.
The frames carry a burned-in clock, and the tide floods every site at about the same hour, so the clock
is hidden from the model and every run is compared with a "tide clock" guess that never sees the image.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import timm
import torch
import torch.nn as nn
from PIL import Image
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torchvision.transforms import v2 as T

SIZE = 448
STAMP_FRAC = 0.04  # burned-in date and time along the top edge
FLOODED_CM = 2.0  # the road heights are read off frames by eye; below this is "wet", not "flooded"
CLOCK_MINUTES = 20
dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

_to_tensor = T.Compose([T.ToImage(), T.ToDtype(torch.float32, scale=True),
                        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])


def augment(size: int):
    return T.Compose([T.RandomResizedCrop(size, scale=(0.6, 1.0), ratio=(0.8, 1.25)),
                      T.RandomHorizontalFlip(), T.ColorJitter(0.3, 0.3, 0.2)])


def load_frame(path: Path, size: int = SIZE, aug=None) -> torch.Tensor:
    im = Image.open(path).convert("RGB")
    im.paste((0, 0, 0), (0, 0, im.width, int(im.height * STAMP_FRAC)))
    im = aug(im) if aug else im.resize((size, size), Image.BILINEAR)
    return _to_tensor(im)


class Frames(torch.utils.data.Dataset):
    def __init__(self, df: pd.DataFrame, root: Path, size: int, train: bool = False):
        self.files = [root / f for f in df["file"]]
        self.depth = df["depth_cm"].to_numpy("float32")
        self.size, self.aug = size, augment(size) if train else None

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        d = self.depth[i]
        return load_frame(self.files[i], self.size, self.aug), torch.tensor(float(d >= FLOODED_CM)), torch.tensor(d / 10)


def loader(df, root, size, train=False, bs=16):
    return torch.utils.data.DataLoader(Frames(df, root, size, train), bs, shuffle=train, drop_last=train, num_workers=2)


class Net(nn.Module):
    """ViT-S/14 trunk; the head sees the CLS token and the mean patch token."""

    def __init__(self, size: int = SIZE):
        super().__init__()
        self.b = timm.create_model("vit_small_patch14_dinov2.lvd142m", pretrained=True, num_classes=0, img_size=size)
        self.h = nn.Linear(768, 2)  # flooded logit, depth in decimetres

    def embed(self, x):
        t = self.b.forward_features(x)
        return torch.cat([t[:, 0], t[:, self.b.num_prefix_tokens:].mean(1)], 1)

    def forward(self, x):
        return self.h(self.embed(x))


@torch.no_grad()
def embeddings(df: pd.DataFrame, root: Path, size: int = SIZE) -> np.ndarray:
    net = Net(size).to(dev).eval()
    out = []
    for i, (x, _, _) in enumerate(loader(df, root, size, bs=32)):
        with torch.autocast("cuda", enabled=dev == "cuda"):
            out.append(net.embed(x.to(dev)).float().cpu().numpy())
        if i % 10 == 0:
            print(f"  embedded {min((i + 1) * 32, len(df))}/{len(df)}", flush=True)
    return np.concatenate(out)


def fit_frozen(emb_tr, depth_tr, emb_te):
    flooded = depth_tr >= FLOODED_CM
    reg = make_pipeline(StandardScaler(), Ridge(alpha=100.0)).fit(emb_tr, depth_tr)
    depth = np.clip(reg.predict(emb_te), 0, None)
    if flooded.all() or not flooded.any():
        return np.full(len(emb_te), float(flooded.mean())), depth
    clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000, class_weight="balanced"))
    return clf.fit(emb_tr, flooded).predict_proba(emb_te)[:, 1], depth


def fit_finetune(tr: pd.DataFrame, root: Path, epochs: int, size: int = SIZE) -> Net:
    net = Net(size).to(dev)
    opt = torch.optim.AdamW([{"params": net.b.parameters(), "lr": 1e-5},
                             {"params": net.h.parameters(), "lr": 1e-3}], weight_decay=0.05)
    dl = loader(tr, root, size, train=True)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[1e-5, 1e-3], total_steps=epochs * len(dl), pct_start=0.1)
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")
    share = float((tr["depth_cm"] >= FLOODED_CM).mean())
    weight = float(np.clip((1 - share) / max(share, 1e-3), 1, 5))
    bce = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(weight, dtype=torch.float32, device=dev))
    for ep in range(epochs):
        net.train()
        total = 0.0
        for x, f, d in dl:
            x, f, d = x.to(dev), f.to(dev), d.to(dev)
            with torch.autocast("cuda", enabled=dev == "cuda"):
                o = net(x).float()
                loss = bce(o[:, 0], f) + nn.functional.smooth_l1_loss(o[:, 1], d)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += loss.item()
        print(f"  epoch {ep + 1}/{epochs}  loss {total / len(dl):.3f}", flush=True)
    return net


@torch.no_grad()
def predict(net: Net, df: pd.DataFrame, root: Path, size: int = SIZE):
    net.eval()
    out = []
    for x, _, _ in loader(df, root, size, bs=32):
        with torch.autocast("cuda", enabled=dev == "cuda"):
            out.append(net(x.to(dev)).float().cpu())
    o = torch.cat(out)
    return torch.sigmoid(o[:, 0]).numpy(), np.clip(o[:, 1].numpy() * 10, 0, None)


def held_out_folds(groups: pd.Series, k: int):
    """Hold out whole camera sites or whole days; with k == number of groups, one group per fold."""
    fold_of = {g: i % k for i, g in enumerate(groups.value_counts().index)}
    fold = groups.map(fold_of).to_numpy()
    return [(np.flatnonzero(fold != i), np.flatnonzero(fold == i)) for i in range(k)]


def tide_clock(tr: pd.DataFrame, te: pd.DataFrame, by_day: bool):
    """Guess from the clock alone, never the image.

    Camera split: what the other cameras showed within 20 minutes of the test frame.
    Day split: what the same camera showed at that time of day on the other days.
    """
    def minutes(df):
        t = df["time_utc"]
        return (t.dt.hour * 60 + t.dt.minute).to_numpy() if by_day else t.to_numpy().astype("datetime64[m]").astype(np.int64)

    when = minutes(te)
    station = te["station"].to_numpy()
    p, d = np.zeros(len(te)), np.zeros(len(te))
    for s in np.unique(station) if by_day else [None]:
        pool = tr[tr["station"] == s] if by_day else tr
        pool = pool if len(pool) else tr
        order = np.argsort(minutes(pool), kind="stable")
        t, depth = minutes(pool)[order], pool["depth_cm"].to_numpy()[order]
        for i in np.flatnonzero(station == s) if by_day else range(len(te)):
            lo, hi = np.searchsorted(t, [when[i] - CLOCK_MINUTES, when[i] + CLOCK_MINUTES + 1])
            near = depth[lo:hi] if hi > lo else depth
            p[i], d[i] = (near >= FLOODED_CM).mean(), near.mean()
    return p, d


def score(depth_true, p_flooded, depth_pred) -> dict:
    y = depth_true >= FLOODED_CM
    hit = p_flooded >= 0.5
    tp = int((hit & y).sum())
    out = {
        "n": int(len(y)),
        "n_flooded": int(y.sum()),
        "precision": round(tp / max(int(hit.sum()), 1), 3),
        "recall": round(tp / max(int(y.sum()), 1), 3),
        "depth_mae_cm": round(float(np.abs(depth_pred - depth_true).mean()), 2),
    }
    if y.any():
        out["depth_mae_cm_flooded"] = round(float(np.abs(depth_pred - depth_true)[y].mean()), 2)
    if y.any() and not y.all():
        out["average_precision"] = round(float(average_precision_score(y, p_flooded)), 3)
    return out


def export(out: Path, max_dist_m: float = 75.0) -> pd.DataFrame:
    """Held-out-camera predictions (fine-tuned if present, else frozen) keyed to the NCDOT segment under each camera."""
    import geopandas as gpd
    import shapely

    src = next(p for m in ("finetune", "frozen") if (p := out / f"flood_camera_oof_{m}_camera.parquet").exists())
    df = pd.read_parquet(src)
    cams = df.groupby("site", as_index=False)[["lat", "lon"]].first()
    cams = gpd.GeoDataFrame(cams, geometry=gpd.points_from_xy(cams["lon"], cams["lat"]), crs=4326).to_crs(32119)
    seg = pd.read_parquet("data/raw/ncdot_joined.parquet", columns=["seg_id", "geometry"])
    seg = gpd.GeoDataFrame(seg[["seg_id"]], geometry=shapely.from_wkb(seg["geometry"].values), crs=4326).to_crs(32119)
    near = gpd.sjoin_nearest(cams, seg, max_distance=max_dist_m, distance_col="seg_dist_m").drop_duplicates("site")
    df = df.merge(near[["site", "seg_id", "seg_dist_m"]], on="site", how="left")
    ncdot = Path("data/raw/cctv/cameras.parquet")  # the camera collector's own match prefers the route a camera is named for
    if ncdot.exists():
        c = pd.read_parquet(ncdot, columns=["camera_id", "seg_id", "seg_dist_m"])
        c = c.assign(site="NCDOT_" + c["camera_id"].astype(str)).set_index("site")
        known = df["site"].isin(c.index)
        df.loc[known, "seg_id"] = df.loc[known, "site"].map(c["seg_id"])
        df.loc[known, "seg_dist_m"] = df.loc[known, "site"].map(c["seg_dist_m"])
    df = df.rename(columns={"depth_cm": "depth_measured_cm"})
    df.loc[df["role"] == "extra", "depth_measured_cm"] = np.nan  # known not flooded, but nothing was measured
    cols = ["station", "site", "name", "lat", "lon", "seg_id", "seg_dist_m", "time_utc", "file", "role",
            "depth_measured_cm", "p_flooded", "depth_pred_cm", "run"]
    df[cols].to_parquet(out / "flood_camera_depth.parquet", index=False)
    print(f"flood_camera_depth.parquet from {src.name}: {len(df)} frames, {df['site'].nunique()} cameras, "
          f"{df.loc[df['seg_id'].notna(), 'site'].nunique()} on an NCDOT segment", flush=True)
    runs = {}  # the results table: one entry per run, None where that run's metrics are not on disk
    for r in ("frozen_camera", "finetune_camera", "frozen_day", "finetune_day"):
        f = out / f"flood_camera_metrics_{r}.json"
        runs[r] = {k: v for k, v in json.loads(f.read_text()).items() if k not in ("run", "by_station")} if f.exists() else None
    (out / "flood_camera_summary.json").write_text(json.dumps({"predictions_from": src.name, "runs": runs}, indent=1))
    return df[cols]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frozen", action="store_true")
    ap.add_argument("--split", choices=["camera", "day"], default="camera")
    ap.add_argument("--folds", type=int, default=0, help="0 = one fold per camera site or per day")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--size", type=int, default=SIZE, help="frame side in pixels, a multiple of 14")
    ap.add_argument("--final", action="store_true", help="also train on every frame, save weights, score the extra rows")
    ap.add_argument("--data", type=Path, default=Path("data/raw/sunnyday"))
    ap.add_argument("--out", type=Path, default=Path("data/processed"))
    ap.add_argument("--export", action="store_true")
    args = ap.parse_args()
    if args.export:
        export(args.out)
        return
    mode = "frozen" if args.frozen else "finetune"
    run = f"{mode}_{args.split}"
    print(f"{run} on {dev}", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)  # before any training: --final saves weights here

    def save(oof, metrics):
        oof.drop(columns=["level_time"], errors="ignore").to_parquet(args.out / f"flood_camera_oof_{run}.parquet", index=False)
        (args.out / f"flood_camera_metrics_{run}.json").write_text(json.dumps(metrics, indent=1))

    labels = pd.read_parquet(args.data / "labels.parquet")
    cv = labels[labels["role"] == "cv"].reset_index(drop=True)
    extra = labels[labels["role"] == "extra"].reset_index(drop=True)
    groups = cv["site"] if args.split == "camera" else cv["time_utc"].dt.date.astype(str)
    k = min(args.folds or groups.nunique(), groups.nunique())
    folds = held_out_folds(groups, k)

    emb = embeddings(pd.concat([cv, extra]), args.data, args.size) if args.frozen else None
    p, d = np.zeros(len(cv)), np.zeros(len(cv))
    pc, dc = np.zeros(len(cv)), np.zeros(len(cv))
    for i, (tr, te) in enumerate(folds):
        print(f"fold {i + 1}/{k}: held out {sorted(groups.iloc[te].unique())}", flush=True)
        done = args.out / f".flood_camera_{run}_s{args.size}_e{args.epochs}_k{k}_fold{i}.npz"
        if args.frozen:
            p[te], d[te] = fit_frozen(emb[tr], cv["depth_cm"].to_numpy()[tr], emb[te])
        elif done.exists():  # a stopped run picks up where it left off
            p[te], d[te] = np.load(done)["p"], np.load(done)["d"]
            print("  already trained, reusing its predictions", flush=True)
        else:
            net = fit_finetune(cv.iloc[tr], args.data, args.epochs, args.size)
            p[te], d[te] = predict(net, cv.iloc[te], args.data, args.size)
            np.savez(done, p=p[te], d=d[te])
        pc[te], dc[te] = tide_clock(cv.iloc[tr], cv.iloc[te], by_day=args.split == "day")

    truth = cv["depth_cm"].to_numpy()
    metrics = {
        "run": run,
        "size": args.size,
        "epochs": None if args.frozen else args.epochs,
        "model": score(truth, p, d),
        "tide_clock": score(truth, pc, dc),
        "always_dry": score(truth, np.zeros(len(cv)), np.zeros(len(cv))),
        "by_station": {s: score(truth[m], p[m], d[m]) for s in sorted(cv["station"].unique())
                       for m in [(cv["station"] == s).to_numpy()]},
    }
    oof = cv.assign(p_flooded=p, depth_pred_cm=d, p_flooded_clock=pc, depth_clock_cm=dc, run=run)
    save(oof, metrics)  # the held-out results are on disk before the all-frames model is trained

    if args.final:
        if args.frozen:
            pe, de = fit_frozen(emb[: len(cv)], truth, emb[len(cv):]) if len(extra) else (np.array([]), np.array([]))
        else:
            net = fit_finetune(cv, args.data, args.epochs, args.size)
            torch.save(net.state_dict(), args.out / "flood_camera_vits14.pt")
            pe, de = predict(net, extra, args.data, args.size) if len(extra) else (np.array([]), np.array([]))
        if len(extra):
            metrics["extra_known_dry"] = {"n": int(len(extra)), "called_flooded": int((pe >= 0.5).sum()),
                                          "depth_mean_cm": round(float(de.mean()), 2)}
            oof = pd.concat([oof, extra.assign(p_flooded=pe, depth_pred_cm=de, run=run)], ignore_index=True)

        save(oof, metrics)
    for done in args.out.glob(f".flood_camera_{run}_*_fold*.npz"):
        done.unlink()
    print(json.dumps({key: metrics[key] for key in metrics if key != "by_station"}, indent=1), flush=True)


if __name__ == "__main__":
    main()
