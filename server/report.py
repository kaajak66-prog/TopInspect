"""检测结果 → 报告 facts（真值）+ AI 文字分析。指标绝不交给 AI 计算。"""
import collections
import json
import os

import httpx
import numpy as np

from server import config


def build_facts(bundle, metrics, top_k=8):
    """从 JobManager raw bundle 与 build_metrics 结果组装报告 facts（全真值）。"""
    result = bundle["result"]
    preds = np.asarray(result["preds"]).astype(int)
    attacks = np.asarray(bundle["attacks"])
    node_list = result["node_list"]
    src_idx = np.asarray(result["src_idx"])
    dst_idx = np.asarray(result["dst_idx"])
    total = int(bundle["total_rows"])
    anomaly = int(preds.sum())
    has_label = bundle["labels"] is not None

    # —— top 攻击类型：仅统计被判异常且非 Benign 的流 ——
    atk_count = collections.Counter()
    for i in np.where(preds == 1)[0]:
        if attacks[i] != "Benign":
            atk_count[str(attacks[i])] += 1
    top_attack_types = [{"type": t, "count": c}
                        for t, c in atk_count.most_common(top_k)]

    # —— top 异常 IP：每个节点累计异常流数，取 top_k ——
    node_anom = np.zeros(len(node_list), dtype=int)
    node_main_atk = [collections.Counter() for _ in node_list]
    for i in np.where(preds == 1)[0]:
        for nid in (int(src_idx[i]), int(dst_idx[i])):
            node_anom[nid] += 1
            if attacks[i] != "Benign":
                node_main_atk[nid][str(attacks[i])] += 1
    order = np.argsort(node_anom)[::-1][:top_k]
    top_anomaly_ips = []
    for nid in order:
        if node_anom[nid] == 0:
            continue
        main = node_main_atk[nid].most_common(1)
        top_anomaly_ips.append({
            "ip": node_list[nid],
            "anomaly_count": int(node_anom[nid]),
            "attack_type": main[0][0] if main else "未知",
        })

    return {
        "total_flows": total,
        "anomaly_count": anomaly,
        "anomaly_rate": round(anomaly / total, 4) if total else 0.0,
        "threshold": metrics["threshold"],
        "latency_ms": metrics["latencyMs"],
        "has_label": has_label,
        "accuracy": metrics["accuracy"],
        "f1": metrics["f1"],
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "fpr": metrics["fpr"],
        "confusion": metrics["confusion"],
        "pr_curve": metrics.get("prCurve"),
        "top_attack_types": top_attack_types,
        "top_anomaly_ips": top_anomaly_ips,
    }


_PROMPT_SYS = (
    "你是一名资深网络安全分析师，正在为一次网络入侵检测撰写正式分析报告。"
    "下面的 JSON 给出本次检测的真实统计指标（已由系统计算完成，"
    "你必须直接引用这些数字，严禁重新计算、估算或编造任何数值）。\n"
    "请用简体中文撰写一份专业、详尽、可落地的分析报告，严格输出如下 JSON 结构：\n"
    '{\n'
    '  "executive_summary": "执行摘要：3-5 句，面向管理层，概述本次检测规模、'
    '整体安全态势、最严重的威胁与核心结论。",\n'
    '  "threat_assessment": "威胁研判：5-8 句。详细分析检出的异常流量特征、'
    '主要攻击类型及其技战术含义（如 Fuzzers/Exploits/DoS 等各自的危害与典型手法）、'
    '重点异常源 IP 的行为模式、攻击在网络拓扑中的传播态势。",\n'
    '  "model_evaluation": "模型评估：4-6 句。结合准确率、F1、召回率、误报率(FPR)、'
    '检测阈值与混淆矩阵(TP/FP/TN/FN)，客观评价模型本次检测的可靠性、'
    '漏报与误报风险，并指出在何种场景下结论需要人工复核。",\n'
    '  "recommendations": "处置建议：分条目（用 1. 2. 3. … 编号，至少 5 条）。'
    '针对本次具体的攻击类型与异常 IP，给出可立即执行的处置动作，'
    '包括但不限于：网络隔离/封禁、访问控制策略调整、日志与流量取证、'
    '补丁与加固、阈值与模型调优、后续监控重点。每条都要具体、可操作。",\n'
    '  "conclusion": "总体结论：3-4 句，总结风险等级与下一步行动优先级。"\n'
    '}\n'
    "要求：语言专业严谨，避免空话套话，所有判断都要有指标支撑；"
    "处置建议必须结合本次数据中真实出现的攻击类型和 IP，不要泛泛而谈。"
)


# 报告分段的键顺序（前端按此渲染）
_SECTION_KEYS = (
    "executive_summary", "threat_assessment", "model_evaluation",
    "recommendations", "conclusion",
)


def _degraded(facts):
    rate = facts.get("anomaly_rate", 0) * 100
    total = facts.get("total_flows", 0)
    anomaly = facts.get("anomaly_count", 0)
    atks = facts.get("top_attack_types", []) or []
    ips = facts.get("top_anomaly_ips", []) or []
    atk_txt = "、".join(f"{a['type']}（{a['count']} 次）" for a in atks[:3]) or "未识别出具体攻击类型"
    ip_txt = "、".join(f"{i['ip']}（{i['anomaly_count']} 次异常）" for i in ips[:3]) or "无突出异常源"
    acc = facts.get("accuracy")
    acc_txt = f"{acc*100:.1f}%" if acc is not None else "无标签数据"
    msg = "（注：AI 分析服务未配置或暂不可用，以下为基于真实检测数据自动生成的摘要。）"
    return {
        "available": False,
        "executive_summary": (
            f"{msg}本次共分析网络流量 {total} 条，检出异常 {anomaly} 条，"
            f"异常率 {rate:.2f}%。主要攻击类型为 {atk_txt}。"
            f"重点关注异常源 IP：{ip_txt}。"),
        "threat_assessment": (
            f"检测识别出的异常流量集中表现为 {atk_txt}。"
            f"其中源 IP {ip_txt} 的异常行为最为突出，建议优先排查。"
            "异常流量在网络中的分布提示可能存在横向探测或针对特定主机的攻击尝试。"),
        "model_evaluation": (
            f"本次检测准确率 {acc_txt}，检测阈值 {facts.get('threshold', '—')}。"
            "请结合混淆矩阵中的误报(FP)与漏报(FN)情况判断结论可靠性，"
            "对临近阈值的边界样本建议人工复核。"),
        "recommendations": (
            "1. 立即隔离或封禁上述高风险异常源 IP，阻断其与内网的连接。\n"
            "2. 对涉及的攻击类型开展针对性排查，检查相关主机是否已被入侵。\n"
            "3. 留存相关流量与日志用于取证，必要时上报安全团队。\n"
            "4. 复核检测阈值与告警策略，降低误报对运营的干扰。\n"
            "5. 对高风险主机加强后续监控，关注是否出现二次攻击。"),
        "conclusion": (
            "本次检测已完成并识别出明确的异常活动，请结合上方真实指标与图表，"
            "按建议的优先级尽快处置高风险目标。"),
    }


def generate_ai_sections(facts):
    """调 DeepSeek 写三段文字。无 key / 超时 / 异常 / 解析失败 → 降级，不抛错。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return _degraded(facts)
    payload = {
        "model": config.DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": _PROMPT_SYS},
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_tokens": 2000,
    }
    try:
        with httpx.Client(timeout=config.DEEPSEEK_TIMEOUT) as client:
            r = client.post(
                config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        fallback = _degraded(facts)
        out = {"available": True}
        for k in _SECTION_KEYS:
            out[k] = str(data.get(k, "")).strip() or fallback[k]
        return out
    except Exception:
        return _degraded(facts)
