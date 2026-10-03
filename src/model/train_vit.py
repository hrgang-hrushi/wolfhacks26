"""ViT-S/14 (DINOv2 init) on NAIP chips. Uses the same 5 km spatial folds as train_tabular.

  uv run python -m src.model.train_vit --frozen            # embeddings -> PCA 16 (im_emb*)
  uv run python -m src.model.train_vit --epochs 3          # fine-tune, out-of-fold scores
  add --smoke to use only the chips already cut, 2k segments, 1 epoch
Writes: data/processed/vit_frozen.parquet, data/processed/vit_oof.parquet
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import timm
import torch
import torch.nn as nn
from sklearn.decomposition import PCA

from src.model.common import add_folds
from src.pipeline.chips import chip_path

P = Path("data/processed")
dev = "cuda" if torch.cuda.is_available() else "cpu"
MEAN = torch.tensor([0.485, 0.456, 0.406], device=dev).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225], device=dev).view(1, 3, 1, 1)


class DS(torch.utils.data.Dataset):
    def __init__(s, ids, yr, yc, train=False):
        s.ids, s.yr, s.yc, s.train = ids, yr, yc, train

    def __len__(s):
        return len(s.ids)

    def __getitem__(s, i):
        a = np.load(chip_path(s.ids[i]))[:3, 1:127, 1:127].astype("float32") / 255
        if s.train:
            if np.random.rand() < 0.5: a = a[:, :, ::-1]
            if np.random.rand() < 0.5: a = a[:, ::-1, :]
        yr, yc = s.yr[i], s.yc[i]
        return (torch.from_numpy(a.copy()), torch.tensor(0. if np.isnan(yr) else yr),
                torch.tensor(0. if np.isnan(yc) else yc),
                torch.tensor([float(not np.isnan(yr)), float(not np.isnan(yc))]))


class Net(nn.Module):
    def __init__(s):
        super().__init__()
        s.b = timm.create_model("vit_small_patch14_dinov2.lvd142m", pretrained=True,
                                num_classes=0, img_size=126)
        s.h = nn.Linear(384, 2)

    def forward(s, x, emb=False):
        z = s.b((x - MEAN) / STD)
        return z if emb else s.h(z)


def loader(ds, shuffle, bs=128):
    return torch.utils.data.DataLoader(ds, bs, shuffle=shuffle, num_workers=4, drop_last=shuffle)


@torch.no_grad()
def predict(net, ds, emb=False):
    net.eval(); out = []
    for x, *_ in loader(ds, False, 256):
        with torch.autocast(dev, enabled=dev == "cuda"):
            out.append(net(x.to(dev), emb).float().cpu())
    return torch.cat(out).numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", action="store_true")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()

    d = pd.read_parquet(P / "segments_targets.parquet")
    if "fold" not in d.columns:
        d = add_folds(d)
    d = d[[chip_path(s).exists() for s in d.seg_id]].reset_index(drop=True)
    if a.smoke:
        d = d.sample(min(2000, len(d)), random_state=0).reset_index(drop=True)
        a.epochs = 1
    print(f"{len(d):,} segments with chips, device={dev}", flush=True)
    yr, yc = d.y_rate.values, d.y_crack.values
    net = Net().to(dev)

    if a.frozen:
        E = predict(net, DS(d.seg_id.values, yr, yc), emb=True)
        Z = PCA(16, random_state=0).fit_transform(E)
        out = pd.DataFrame(Z, columns=[f"im_emb{i}" for i in range(16)]); out.insert(0, "seg_id", d.seg_id)
        out.to_parquet(P / "vit_frozen.parquet"); print("saved vit_frozen.parquet"); return

    oof = np.full((len(d), 2), np.nan, dtype="float32")
    for k in range(5):
        tr, te = np.where(d.fold != k)[0], np.where(d.fold == k)[0]
        if len(te) == 0: continue
        net = Net().to(dev)
        opt = torch.optim.AdamW([{"params": net.b.parameters(), "lr": 2e-5},
                                 {"params": net.h.parameters(), "lr": 1e-3}], weight_decay=0.05)
        dl = loader(DS(d.seg_id.values[tr], yr[tr], yc[tr], train=True), True)
        for ep in range(a.epochs):
            net.train()
            for i, (x, r, c, m) in enumerate(dl):
                x, r, c, m = x.to(dev), r.to(dev), c.to(dev), m.to(dev)
                with torch.autocast(dev, enabled=dev == "cuda"):
                    o = net(x).float()
                loss = ((o[:, 0] - r).abs() * m[:, 0]).sum() / m[:, 0].sum().clamp(min=1) \
                     + (nn.functional.binary_cross_entropy_with_logits(o[:, 1], c, reduction="none")
                        * m[:, 1]).sum() / m[:, 1].sum().clamp(min=1)
                opt.zero_grad(); loss.backward(); opt.step()
                if i % 100 == 0: print(f"fold {k} ep {ep} it {i} loss {loss.item():.3f}", flush=True)
        oof[te] = predict(net, DS(d.seg_id.values[te], yr[te], yc[te]))
        print(f"fold {k} done", flush=True)
    out = pd.DataFrame({"seg_id": d.seg_id, "im_vit_rate": oof[:, 0], "im_vit_crack": oof[:, 1]})
    out.to_parquet(P / "vit_oof.parquet"); print("saved vit_oof.parquet")


if __name__ == "__main__":
    main()