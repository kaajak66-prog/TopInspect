"""FastAPI 应用：路由 + CORS + SSE + 静态托管前端。"""
import asyncio
import io
import json
import os
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from server import config, inference
from server.jobs import JobManager

app = FastAPI(title="TopInspect API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_mgr = JobManager()
_model = None
_threshold = None


def _ensure_model():
    global _model, _threshold
    if _model is None:
        if not os.path.exists(config.DEFAULT_CHECKPOINT):
            raise HTTPException(500, f"checkpoint 缺失: {config.DEFAULT_CHECKPOINT}")
        _model, _threshold = inference.load_model()
    return _model, _threshold


def _make_run_fn():
    """返回 run_fn(df, progress_cb) 供 JobManager 调用。"""
    model, threshold = _ensure_model()

    def run_fn(df, progress_cb=None):
        labels = df["Label"].values.astype(int) if "Label" in df.columns else None
        attacks = (df["Attack"].astype(str).values if "Attack" in df.columns
                   else np.array(["Benign"] * len(df)))
        ts_ms = (df["FLOW_START_MILLISECONDS"].values.astype("int64")
                 if "FLOW_START_MILLISECONDS" in df.columns else np.arange(len(df)))
        # 真实 NetFlow 字节/包列，供节点详情显示全量真值（缺列则置 0）。
        def _col(name):
            return (df[name].fillna(0).values.astype("int64")
                    if name in df.columns else np.zeros(len(df), dtype="int64"))
        feats = {"in_bytes": _col("IN_BYTES"), "out_bytes": _col("OUT_BYTES"),
                 "in_pkts": _col("IN_PKTS"), "out_pkts": _col("OUT_PKTS")}
        result = inference.run_inference(df, model, threshold, progress_cb=progress_cb)
        return {"result": result, "ts_ms": ts_ms, "attacks": attacks,
                "labels": labels, "feats": feats, "total_rows": len(df)}

    return run_fn


@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": _model is not None, "device": inference.DEVICE}


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(400, f"CSV 解析失败: {e}")
    try:
        inference.validate_columns(df)
    except inference.ColumnMismatchError as e:
        return JSONResponse(status_code=400,
                            content={"error": "列结构不符，需 NetFlow v3 格式",
                                     "missing": e.missing})
    job_id = _mgr.create_job(df, _make_run_fn())
    return {"job_id": job_id, "filename": file.filename,
            "total_rows": len(df), "status": "queued"}


@app.post("/api/jobs/sample")
def create_sample_job(sample_rows: int = 50000):
    """一键示例：读默认数据集前 sample_rows 行（演示用，避免 551MB 全跑）。"""
    path = os.path.join(config.DATA_DIR, config.DEFAULT_DATASET,
                        f"{config.DEFAULT_DATASET}.csv")
    if not os.path.exists(path):
        raise HTTPException(404, f"示例数据集不存在: {path}")
    df = pd.read_csv(path, nrows=sample_rows)
    job_id = _mgr.create_job(df, _make_run_fn())
    return {"job_id": job_id, "filename": f"{config.DEFAULT_DATASET}(示例{sample_rows}行)",
            "total_rows": len(df), "status": "queued"}


@app.get("/api/jobs/{job_id}/progress")
async def progress(job_id: str):
    async def gen():
        while True:
            st = _mgr.get_status(job_id)
            yield {"data": json.dumps(st, ensure_ascii=False)}
            if st["stage"] in ("done", "error"):
                break
            await asyncio.sleep(0.4)

    return EventSourceResponse(gen())


@app.get("/api/jobs/{job_id}/replay")
def replay(job_id: str, model: str = "improved"):
    if model == "baseline":
        _get_anomale_bundle(job_id)  # 确保对比模型 bundle 已按需生成并缓存
    p = _mgr.get_replay(job_id, model)
    if p is None:
        raise HTTPException(404, "结果未就绪")
    return p


@app.get("/api/jobs/{job_id}/metrics")
def metrics(job_id: str, model: str = "improved"):
    if model == "baseline":
        _get_anomale_bundle(job_id)
    m = _mgr.get_metrics(job_id, model)
    if m is None:
        raise HTTPException(404, "结果未就绪")
    return m


@app.post("/api/jobs/{job_id}/report")
def report(job_id: str):
    from server import aggregate, report as report_mod
    bundle = _mgr.get_raw(job_id)
    if not bundle:
        raise HTTPException(404, "结果未就绪")
    m = aggregate.build_metrics(bundle["result"], bundle["labels"])
    facts = report_mod.build_facts(bundle, m)
    ai_sections = report_mod.generate_ai_sections(facts)
    tz = timezone(timedelta(hours=8))
    return {
        "job_id": job_id,
        "generated_at": datetime.now(tz).isoformat(timespec="seconds"),
        "model": {
            "name": "无监督 Graph AutoEncoder",
            "type": "unsupervised",
            "dataset": config.DEFAULT_DATASET,
        },
        "facts": facts,
        "ai_sections": ai_sections,
    }


# ─── 模型对比注册表 ───
# metricDefs：每个对比指标的定义。higherBetter=False 表示"越低越好"（误报率/延迟）。
_COMPARE_METRIC_DEFS = [
    {"key": "accuracy",  "label": "准确率",   "unit": "%",  "higherBetter": True},
    {"key": "recall",    "label": "召回率",   "unit": "%",  "higherBetter": True},
    {"key": "fpr",       "label": "误报率",   "unit": "%",  "higherBetter": False},
    {"key": "f1",        "label": "F1 分数",  "unit": "",   "higherBetter": True},
    {"key": "auc",       "label": "PR-AUC",   "unit": "",   "higherBetter": True},
    {"key": "latencyMs", "label": "推理延迟", "unit": "ms", "higherBetter": False},
]


def _metrics_from_result(result, labels):
    """从推理结果 + 真实标签提取对比指标。无标签返回 None。

    指标：accuracy / recall / fpr / f1 / auc(PR-AUC) / latencyMs，全真值。
    """
    from server import aggregate
    m = aggregate.build_metrics(result, labels)
    if m.get("accuracy") is None:  # 无标签数据集，无法算监督指标
        return None
    # PR-AUC：用 prCurve 的点做梯形积分近似（recall 单调段）
    auc = None
    pr = m.get("prCurve") or []
    if len(pr) >= 2:
        pts = sorted(pr, key=lambda p: p["recall"])
        auc = 0.0
        for i in range(1, len(pts)):
            dr = pts[i]["recall"] - pts[i - 1]["recall"]
            auc += dr * (pts[i]["precision"] + pts[i - 1]["precision"]) / 2.0
        auc = round(float(auc), 4)
    return {
        "accuracy": m["accuracy"],
        "recall": m["recall"],
        "fpr": m["fpr"],
        "f1": m["f1"],
        "auc": auc,
        "latencyMs": m["latencyMs"],
    }


# 基础模型（enhanced 架构）懒加载，仅模型对比页用，不影响主检测。
_baseline_model = None
_baseline_threshold = None


def _ensure_baseline_model():
    global _baseline_model, _baseline_threshold
    if _baseline_model is None:
        if not os.path.exists(config.BASELINE_CHECKPOINT):
            raise HTTPException(500, f"基础模型 checkpoint 缺失: {config.BASELINE_CHECKPOINT}")
        _baseline_model, _baseline_threshold = inference.load_model(
            config.BASELINE_CHECKPOINT, hparams=config.BASELINE_HPARAMS)
    return _baseline_model, _baseline_threshold


def _get_baseline_bundle(job_id: str):
    """基础模型对同一张图的完整 bundle（按需跑一次并缓存）。

    复用优化后 bundle 的图结构与真值（node_list/src_idx/dst_idx/ts_ms/attacks/
    feats/labels 全相同），仅换上基础模型的 scores/preds/threshold/latency。
    未就绪或无图返回 None。
    """
    cached = _mgr.get_baseline_cache(job_id)
    if cached is not None:
        return cached
    main = _mgr.get_raw(job_id, "improved")
    if not main:
        return None
    graph = main["result"].get("graph")
    if graph is None:
        return None
    model, threshold = _ensure_baseline_model()
    scored = inference.score_graph(graph, model, threshold)
    # 用基础模型的分数/判定覆盖，其余图元数据与真值复用主 bundle。
    base_result = dict(main["result"])
    base_result.update({
        "scores": scored["scores"],
        "preds": scored["preds"],
        "threshold": scored["threshold"],
        "latency_ms": scored["latency_ms"],
    })
    bundle = {
        "result": base_result,
        "ts_ms": main["ts_ms"],
        "attacks": main["attacks"],
        "labels": main["labels"],
        "feats": main.get("feats"),
        "total_rows": main["total_rows"],
    }
    _mgr.set_baseline_cache(job_id, bundle)
    return bundle


# Anomal-E-CBLOF 对比模型懒加载，仅对比页用，不影响主检测。
_anomale_model = None


def _ensure_anomale_model():
    global _anomale_model
    if _anomale_model is None:
        if not os.path.exists(config.ANOMALE_CHECKPOINT):
            raise HTTPException(500, f"Anomal-E checkpoint 缺失: {config.ANOMALE_CHECKPOINT}")
        _anomale_model = inference.load_anomale_model()
    return _anomale_model


def _get_anomale_bundle(job_id: str):
    """Anomal-E-CBLOF 对同一张图的完整 bundle（按需跑一次并缓存于对比槽）。

    复用主 job 的图结构与真值（node_list/src_idx/dst_idx/ts_ms/attacks/feats/labels
    全相同），仅换上 Anomal-E 的 scores/preds/threshold/latency。未就绪或无图返回 None。
    缓存复用 JobManager 的 baseline 槽（对比模型槽），无需改 jobs.py。
    """
    cached = _mgr.get_baseline_cache(job_id)
    if cached is not None:
        return cached
    main = _mgr.get_raw(job_id, "improved")
    if not main:
        return None
    graph = main["result"].get("graph")
    if graph is None:
        return None
    model = _ensure_anomale_model()
    scored = inference.score_graph_anomale(graph, model)
    base_result = dict(main["result"])
    base_result.update({
        "scores": scored["scores"],
        "preds": scored["preds"],
        "threshold": scored["threshold"],
        "latency_ms": scored["latency_ms"],
    })
    bundle = {
        "result": base_result,
        "ts_ms": main["ts_ms"],
        "attacks": main["attacks"],
        "labels": main["labels"],
        "feats": main.get("feats"),
        "total_rows": main["total_rows"],
    }
    _mgr.set_baseline_cache(job_id, bundle)
    return bundle


def _compare_metrics(job_id: str, model: str):
    """指定模型对上传数据的真实对比指标。无标签/未就绪返回 None。"""
    if model == "baseline":
        bundle = _get_anomale_bundle(job_id)
    else:
        bundle = _mgr.get_raw(job_id, "improved")
    if not bundle:
        return None
    return _metrics_from_result(bundle["result"], bundle["labels"])


@app.get("/api/compare")
def compare(job_id: str | None = None):
    """模型对比：Anomal-E-CBLOF(论文基线) vs TopInspect·拓察(优化后主检测)。

    两个模型对同一份上传数据实跑、复用同一张图、按真实标签算指标。
    - 优化后：复用 job 已有推理结果。
    - Anomal-E-CBLOF：按需用 E-GraphSAGE 编码器 + CBLOF 跑同一张图，结果缓存。
    无标签数据集时两槽 metrics 为 None（前端显示 --）。
    """
    improved_metrics = _compare_metrics(job_id, "improved") if job_id else None
    baseline_metrics = _compare_metrics(job_id, "baseline") if job_id else None
    return {
        "dataset": config.DEFAULT_DATASET,
        "metricDefs": _COMPARE_METRIC_DEFS,
        "models": [
            {
                "id": "anomale",
                "name": "Anomal-E-CBLOF",
                "subtitle": "E-GraphSAGE 自监督 + CBLOF 聚类离群 · 论文基线",
                "role": "baseline",
                "status": "ready" if baseline_metrics else "waiting",
                "metrics": baseline_metrics,
            },
            {
                "id": "improved",
                "name": "TopInspect（拓察）",
                "subtitle": "轻量图自编码器 · 低误报优化版",
                "role": "improved",
                "status": "ready" if improved_metrics else "waiting",
                "metrics": improved_metrics,
            },
        ],
    }


@app.get("/api/jobs/{job_id}/nodes/{ip}")
def node_detail(job_id: str, ip: str, model: str = "improved"):
    from server import aggregate
    b = _get_anomale_bundle(job_id) if model == "baseline" else _mgr.get_raw(job_id, "improved")
    if not b:
        raise HTTPException(404, "结果未就绪")
    return aggregate.node_detail(b["result"], b["ts_ms"], b["attacks"], ip)


@app.get("/api/jobs/{job_id}/edges/{src}/{dst}")
def edge_flows(job_id: str, src: str, dst: str, page: int = 0, size: int = 50,
               model: str = "improved"):
    from server import aggregate
    b = _get_anomale_bundle(job_id) if model == "baseline" else _mgr.get_raw(job_id, "improved")
    if not b:
        raise HTTPException(404, "结果未就绪")
    return aggregate.edge_flows(b["result"], b["ts_ms"], b["attacks"], src, dst, page, size)


@app.get("/")
def index():
    if os.path.exists(config.FRONTEND_HTML):
        return FileResponse(config.FRONTEND_HTML)
    raise HTTPException(404, "前端未构建：请先在 frontend/ 运行 `npm run build`")


# Vue 构建产物的静态资源（hash 命名的 js/css）。挂在 API 路由之后，避免遮蔽 /api。
# favicon.svg / icons.svg 等 public 资源也在 dist 根目录，一并由此目录托管。
if os.path.isdir(config.FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(config.FRONTEND_DIST, "assets")), name="assets")
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
