"""Anomal-E DGI 全量预训练：在纯良性 train.pt 上自监督训练 E-GraphSAGE，
再用良性嵌入 fit CBLOF，一并存入 checkpoint。

用法：
    .venv/Scripts/python.exe scripts/train_anomal_e.py --epochs 100
"""
import argparse
import os
import pickle
import sys

import numpy as np
import torch
from pyod.models.cblof import CBLOF
from torch_geometric.nn import DeepGraphInfomax

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.anomal_e import EGraphSAGEEncoder  # noqa: E402
from server import config  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TRAIN_PT = os.path.join(config.DATA_DIR, "pyg_graph_data",
                        config.DEFAULT_DATASET, "train.pt")


def make_summary():
    def summary(z, *args, **kwargs):
        return torch.sigmoid(z.mean(dim=0))
    return summary


def make_corruption():
    def corruption(edge_index, edge_attr, num_nodes):
        perm = torch.randperm(edge_attr.size(0), device=edge_attr.device)
        return edge_index, edge_attr[perm], num_nodes
    return corruption


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--edge-batch", type=int, default=100000,
                    help="每步采样的边数，控制显存（全图消息传递，仅批边算嵌入/loss）")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    hp = config.ANOMALE_HPARAMS
    g = torch.load(TRAIN_PT, weights_only=False)[0].to(DEVICE)
    num_edges = g.edge_index.shape[1]
    print(f"[data] edges={num_edges} nodes={g.num_nodes} "
          f"edim={g.edge_attr.shape[1]} device={DEVICE} edge_batch={args.edge_batch}")

    encoder = EGraphSAGEEncoder(
        edim_in=g.edge_attr.shape[1], hidden_dim=hp["hidden_dim"],
        embed_dim=hp["embed_dim"], num_layers=hp["num_layers"],
        dropout=hp["dropout"],
    ).to(DEVICE)

    dgi = DeepGraphInfomax(
        hidden_channels=hp["embed_dim"], encoder=encoder,
        summary=make_summary(), corruption=make_corruption(),
    ).to(DEVICE)

    summary_fn = make_summary()
    opt = torch.optim.Adam(dgi.parameters(), lr=args.lr)
    dgi.train()
    for ep in range(1, args.epochs + 1):
        # 采样一批边：全图聚合到节点，仅这批边投影为嵌入并算 DGI loss（控显存）。
        bs = min(args.edge_batch, num_edges)
        idx = torch.randperm(num_edges, device=DEVICE)[:bs]
        batch_ei = g.edge_index[:, idx]

        opt.zero_grad()
        # 正样本：真实 edge_attr 聚合；负样本：打乱行序的 edge_attr 聚合（破坏图）。
        _, cor_ea, _ = make_corruption()(g.edge_index, g.edge_attr, g.num_nodes)
        pos_z = encoder(g.edge_index, g.edge_attr, g.num_nodes, edge_couples=batch_ei)
        neg_z = encoder(g.edge_index, cor_ea, g.num_nodes, edge_couples=batch_ei)
        summ = summary_fn(pos_z)
        loss = dgi.loss(pos_z, neg_z, summ)
        loss.backward()
        opt.step()
        if ep % 10 == 0 or ep == 1:
            print(f"[train] epoch {ep}/{args.epochs} loss={loss.item():.4f}")

    # fit CBLOF on benign embeddings（分块推理避免一次性大张量）
    encoder.eval()
    embs = []
    with torch.inference_mode():
        for s in range(0, num_edges, args.edge_batch):
            be = g.edge_index[:, s:s + args.edge_batch]
            z = encoder(g.edge_index, g.edge_attr, g.num_nodes, edge_couples=be)
            embs.append(z.cpu().numpy().astype("float32"))
    emb = np.concatenate(embs, axis=0)
    print(f"[cblof] fitting on benign emb {emb.shape} ...")
    cblof = CBLOF(n_clusters=hp["n_clusters"],
                  contamination=hp["contamination"], random_state=args.seed)
    cblof.fit(emb)
    threshold = float(np.quantile(cblof.decision_scores_, 1 - hp["contamination"]))
    print(f"[cblof] threshold(q={1-hp['contamination']:.2f}) = {threshold:.4f}")

    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    out = config.ANOMALE_CHECKPOINT
    torch.save({
        "model_state_dict": encoder.state_dict(),
        "cblof": pickle.dumps(cblof),
        "threshold": threshold,
        "contamination": hp["contamination"],
        "hparams": dict(hp),
        "epoch": args.epochs,
    }, out)
    print(f"[done] saved -> {out}")


if __name__ == "__main__":
    main()
