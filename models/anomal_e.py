"""Anomal-E 检测管线：E-GraphSAGE 自监督编码器 + CBLOF 离群检测。

E-GraphSAGE 复用 TopInspect SAGELayer 的边->节点->边 聚合思路（PyG 原生，无需 DGL）。
编码器用 Deep Graph Infomax 在纯良性流上自监督预训练；CBLOF 在良性嵌入上 fit 后冻结。
"""
import pickle
import time

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.nn import MessagePassing


class _EdgeSAGEConv(MessagePassing):
    """单层 E-GraphSAGE：边特征聚合到节点，再由端点嵌入拼接投影回边。"""

    def __init__(self, edim_in, node_out, edge_out, dropout=0.0):
        super().__init__(aggr="mean")
        self.fc_neigh = nn.Linear(edim_in, node_out)
        self.fc_edge = nn.Linear(node_out * 2, edge_out)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def message(self, edge_attr):  # type: ignore[override]
        return edge_attr

    def forward(self, edge_index, edge_attr, num_nodes, out_edge_index=None):
        """消息传递用全量 edge_index/edge_attr 聚合到节点；
        边嵌入只对 out_edge_index 指定的边投影（缺省=全部边，向后兼容）。"""
        node_emb = self.propagate(edge_index, edge_attr=edge_attr,
                                  size=(num_nodes, num_nodes))
        node_emb = self.relu(self.fc_neigh(node_emb))
        tgt = edge_index if out_edge_index is None else out_edge_index
        edge_emb = self.fc_edge(
            torch.cat([node_emb[tgt[0]], node_emb[tgt[1]]], dim=1)
        )
        return self.dropout(edge_emb)


class EGraphSAGEEncoder(nn.Module):
    """多层 E-GraphSAGE 边嵌入编码器。

    forward(edge_index, edge_attr, num_nodes, edge_couples=None) -> [num_edges, embed_dim]
    多层时：首层用原始 edge_attr；后续层把上一层的边嵌入当作新的 edge_attr 继续聚合。
    edge_couples（2×B 索引张量）非空时：中间层仍算全量边嵌入（后续层聚合所需），
    仅最后一层的投影限定到这批边——用于训练时的边小批量以控制显存。
    """

    def __init__(self, edim_in, hidden_dim, embed_dim, num_layers=1, dropout=0.0):
        super().__init__()
        self.layers = nn.ModuleList()
        in_dim = edim_in
        for i in range(num_layers):
            out_dim = embed_dim if i == num_layers - 1 else hidden_dim
            self.layers.append(_EdgeSAGEConv(in_dim, hidden_dim, out_dim, dropout))
            in_dim = out_dim

    def forward(self, edge_index, edge_attr, num_nodes, edge_couples=None):
        h = edge_attr
        last = len(self.layers) - 1
        for i, layer in enumerate(self.layers):
            if i == last and edge_couples is not None:
                h = layer(edge_index, h, num_nodes, out_edge_index=edge_couples)
            else:
                h = layer(edge_index, h, num_nodes)
        return h


class AnomalECBLOF:
    """Anomal-E 推理封装：编码器出嵌入 + 冻结 CBLOF 打分 + 阈值判定。

    非 nn.Module（含 pyod 对象）。score() 返回结构与 inference.score_graph 一致，
    便于下游（aggregate/build_metrics）无差别复用。

    阈值策略：CBLOF 分数在不同图上分布会整体偏移，训练图上标定的绝对阈值无法迁移。
    因此按 pyod CBLOF `predict` 的标准语义，在**当前被评估图**的分数上取
    (1-contamination) 分位作为阈值——这是无监督离群检测的忠实做法。
    checkpoint 里保留训练阈值 `train_threshold` 仅作参考。
    """

    def __init__(self, encoder, cblof, contamination, train_threshold=None, device="cpu"):
        self.encoder = encoder
        self.cblof = cblof
        self.contamination = float(contamination)
        self.train_threshold = None if train_threshold is None else float(train_threshold)
        self.device = device

    @classmethod
    def load_checkpoint(cls, path, hparams, device="cpu"):
        ckpt = torch.load(path, map_location=device, weights_only=False)
        enc = EGraphSAGEEncoder(
            edim_in=hparams.get("edim_in", 49),
            hidden_dim=hparams["hidden_dim"],
            embed_dim=hparams["embed_dim"],
            num_layers=hparams["num_layers"],
            dropout=hparams.get("dropout", 0.0),
        ).to(device)
        enc.load_state_dict(ckpt["model_state_dict"])
        enc.eval()
        cblof = pickle.loads(ckpt["cblof"])
        contamination = ckpt.get("contamination", hparams.get("contamination", 0.05))
        return cls(enc, cblof, contamination,
                   train_threshold=ckpt.get("threshold"), device=device)

    @torch.inference_mode()
    def score(self, graph):
        t0 = time.perf_counter()
        emb = self.encoder(graph.edge_index, graph.edge_attr, graph.num_nodes)
        emb_np = emb.detach().cpu().numpy().astype("float32")
        scores = np.asarray(self.cblof.decision_function(emb_np), dtype="float64")
        # 在当前图分数上按 contamination 分位定阈值（适配分布偏移）。
        threshold = float(np.quantile(scores, 1.0 - self.contamination))
        latency_ms = (time.perf_counter() - t0) * 1000.0
        preds = (scores > threshold).astype(int)
        return {
            "scores": scores,
            "preds": preds,
            "threshold": threshold,
            "latency_ms": latency_ms,
        }
