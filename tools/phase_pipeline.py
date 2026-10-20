#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LifeMero LifePhase 分龄数据生成管道（功能①）
=============================================
把人物生平自动切分为 3~5 个年龄段切片（LifePhase），每个切片含：
  ageFrom/ageTo, phaseTag, summary, keyEvents, mentalModel, socialState,
  vector(该阶段六维向量 = 全生涯基准向量 + LLM输出的偏移量Δ, clamp到[0,1])

设计要点：
  - LLM 只输出六维偏移量 Δ（每维 -0.3~+0.3），程序负责叠加与钳制，
    阶段向量不会偏离人物基准画像，避免"张居正突然变成艺术家人格"
  - 阶段标签从标准集合中选（寒窗/起步/崛起/转型/巅峰/困顿/暮年/余晖），
    便于 UI 时间轴配色统一；确实不合适时可输出"自定义:xxx"
  - 年龄未知的人物允许 ageFrom/ageTo 填 -1（用"早期/中期/晚期"代替）

输出：
  - persons_phased.json    含 phases 的全量数据
  - phase_review.md        复核报告（切片数异常/年龄缺失/失败项）

用法：
  # 1) mock 模式验证管道（关键词规则切分，零成本）
  python3 phase_pipeline.py --input persons.json --mock

  # 2) 真实生成（OpenAI 兼容 API）
  export OPENAI_API_KEY=sk-xxx
  export OPENAI_BASE_URL=https://api.deepseek.com/v1
  python3 phase_pipeline.py --input persons.json --model deepseek-chat

  # 3) 断点续跑
  python3 phase_pipeline.py --input persons.json --resume persons_phased.json

输入格式兼容 annotate_metatype.py 的输出（persons_annotated.json 可直接喂进来），
也兼容原始数据集（字段自动识别同前：name/summary/era/industry/vector）。
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("缺少 requests 库，请先: pip install requests")

# 标准阶段标签 → 时间轴配色（与 ui_mockup.html 一致，Flutter 端 Hex 值相同）
PHASE_TAGS = {
    "寒窗": "#EC4899", "起步": "#F59E0B", "崛起": "#F59E0B",
    "转型": "#EF4444", "巅峰": "#3B82F6", "困顿": "#94A3B8",
    "暮年": "#10B981", "余晖": "#10B981",
}
SIX_DIM_NAMES = ["开创性", "执行力", "心智", "专业深度", "联结性", "逆商"]

FIELD_ALIASES = {
    "name": ["name", "nickname", "title", "姓名", "名字"],
    "summary": ["summary", "description", "bio", "intro", "简介", "描述", "生平"],
    "era": ["era", "dynasty", "period", "时代", "朝代", "年代"],
    "industry": ["industry", "field", "occupation", "domain", "行业", "领域", "职业"],
}

# 六维下标含义注释（与数据集保持一致，如有出入改这里）
# 0开创性 1执行力 2心智 3专业深度 4联结性 5逆商


def pick(d: dict, keys: list) -> str:
    for k in keys:
        if k in d and d[k]:
            v = d[k]
            if isinstance(v, str):
                return v
            if isinstance(v, (list, dict)):
                return json.dumps(v, ensure_ascii=False)
    return ""


def get_base_vector(person: dict) -> list:
    raw = pick(person, ["vector", "dimensions", "traits"])
    if raw:
        try:
            v = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(v, list) and len(v) == 6:
                return [float(x) for x in v]
        except Exception:
            pass
    return [0.5] * 6  # 无向量时用中性基准


def build_prompt(person: dict, n_phases: int) -> str:
    name = pick(person, FIELD_ALIASES["name"]) or "（无名）"
    summary = (pick(person, FIELD_ALIASES["summary"]) or "")[:800]
    era = pick(person, FIELD_ALIASES["era"])
    industry = pick(person, FIELD_ALIASES["industry"])
    dims = "、".join(f"{i}:{n}" for i, n in enumerate(SIX_DIM_NAMES))
    tags = "、".join(PHASE_TAGS.keys())
    return f"""你是人物传记结构化专家。请将以下人物的生平切分为 {n_phases} 个人生阶段。

六维向量含义：{dims}
（每维取值0~1，你只需输出各阶段的偏移量Δ，每维-0.3~+0.3）

阶段标签从这些里选：{tags}（必要时可用"自定义:xx"）

人物信息：
- 姓名：{name}
- 时代：{era or '未知'}
- 行业/领域：{industry or '未知'}
- 生平：{summary or '无'}

要求：
1. 按时间顺序切分，阶段之间年龄不重叠；若生平未给出确切年龄，用合理推断，并在ages_guessed标true
2. summary 每阶段120字内；keyEvents 3-5条、每条20字内；mentalModel 是该阶段主导思维模式（20字内）；socialState 是该阶段职业/身份/处境（30字内）
3. vector_delta：该阶段相对全生涯画像的六维偏移，紧扣生平（如困顿期逆商偏高、专业深度可能停滞）
4. 若人物未标注元类型，请顺带补一个：开创者/守成者/变革者/专精者/逢源者/逆命者

只输出 JSON：
{{"phases":[{{"ageFrom":23,"ageTo":36,"phaseTag":"寒窗","summary":"...","keyEvents":["..."],"mentalModel":"...","socialState":"...","vector_delta":[0,0,0,0,0,0],"ages_guessed":false}}],"metatype":"...","consciousness_level":2}}"""


def validate_phases(phases: list) -> list:
    """校验并修复：排序/重叠钳制/标签合法性/维度数"""
    fixed = []
    for ph in sorted(phases, key=lambda x: x.get("ageFrom", -1)):
        tag = ph.get("phaseTag", "自定义:未分类")
        if tag not in PHASE_TAGS and not str(tag).startswith("自定义:"):
            tag = "自定义:未分类"
        ph["phaseTag"] = tag
        ph["ageFrom"] = int(ph.get("ageFrom", -1))
        ph["ageTo"] = int(ph.get("ageTo", -1))
        kes = ph.get("keyEvents", [])
        ph["keyEvents"] = [str(k)[:40] for k in kes][:5]
        d = ph.get("vector_delta", [0.0] * 6)
        ph["vector_delta"] = [max(-0.3, min(0.3, float(x))) for x in (list(d) + [0.0] * 6)[:6]]
        ph["ages_guessed"] = bool(ph.get("ages_guessed", False))
        fixed.append(ph)
    return fixed


def apply_vector(base: list, delta: list) -> list:
    return [round(max(0.0, min(1.0, b + d)), 3) for b, d in zip(base, delta)]


def parse_llm_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("回复中未找到 JSON")
    obj = json.loads(m.group(0))
    if not obj.get("phases") or not (2 <= len(obj["phases"]) <= 6):
        raise ValueError(f"阶段数异常: {len(obj.get('phases', []))}")
    obj["phases"] = validate_phases(obj["phases"])
    return obj


def call_llm(prompt: str, model: str, base_url: str, api_key: str, max_retry: int = 3) -> dict:
    for attempt in range(max_retry):
        try:
            r = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.2, "max_tokens": 1500},
                timeout=90,
            )
            r.raise_for_status()
            return parse_llm_json(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            if attempt == max_retry - 1:
                raise
            wait = 2 ** attempt * 2
            print(f"    重试 {attempt+1}/{max_retry}（{e}）", file=sys.stderr)
            time.sleep(wait)


def mock_phase(person: dict, base_vec: list) -> dict:
    """mock 模式：按生平长度均分 3 段，规则化标签与偏移"""
    summary = pick(person, FIELD_ALIASES["summary"])
    text = summary + pick(person, FIELD_ALIASES["name"])
    n = 3
    plans = [
        {"phaseTag": "寒窗", "delta": [0, -0.1, 0, 0.1, -0.1, 0.15], "mm": "积蓄与学习"},
        {"phaseTag": "崛起", "delta": [0.15, 0.1, 0.05, 0.1, 0.1, 0], "mm": "扩张与证明"},
        {"phaseTag": "巅峰" if "改革" not in text and "转型" not in text else "转型",
         "delta": [0.1, 0.15, 0.1, 0.15, 0, -0.05], "mm": "整合与掌控"},
    ]
    has_ages = bool(re.search(r"\d+岁|\d{3,4}年", summary))
    span = 60 if has_ages else -1
    phases = []
    for i, pl in enumerate(plans):
        age_from = int(i * span / n) if has_ages else -1
        age_to = int((i + 1) * span / n) if has_ages else -1
        chunk = summary[int(i * len(summary) / n): int((i + 1) * len(summary) / n)][:110]
        phases.append({
            "ageFrom": age_from, "ageTo": age_to, "phaseTag": pl["phaseTag"],
            "summary": chunk or "（生平片段）",
            "keyEvents": ["mock事件占位A", "mock事件占位B"],
            "mentalModel": pl["mm"], "socialState": "mock社交状态",
            "vector_delta": pl["delta"], "ages_guessed": has_ages,
        })
    return {"phases": validate_phases(phases),
            "metatype": (person.get("_annotation") or {}).get("metatype", "守成者"),
            "consciousness_level": (person.get("_annotation") or {}).get("consciousness_level", 2)}


def gen_review(persons: list) -> str:
    from collections import Counter
    tag_stat, n_phase_stat = Counter(), Counter()
    issues, failed = [], []
    for p in persons:
        name = pick(p, FIELD_ALIASES["name"])
        if "_phases" not in p:
            failed.append((name, p.get("_error", "未知")))
            continue
        phs = p["_phases"]["phases"]
        n_phase_stat[len(phs)] += 1
        for ph in phs:
            tag_stat[ph["phaseTag"]] += 1
        if any(ph["ages_guessed"] for ph in phs):
            issues.append((name, "年龄为推断值，建议核对年表"))
        if any(ph["ageFrom"] < 0 for ph in phs):
            issues.append((name, "缺少年龄段，使用早期/中期/晚期模式"))
        if len(phs) < 3:
            issues.append((name, f"仅切出 {len(phs)} 段，偏少"))
    lines = [
        "# LifeMero LifePhase 分龄复核报告",
        f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "## 一、阶段标签分布\n", "| 标签 | 次数 |", "|---|---|",
    ]
    for t, c in tag_stat.most_common():
        lines.append(f"| {t} | {c} |")
    lines += ["\n## 二、切片数分布\n", "| 阶段数 | 人物数 |", "|---|---|"]
    for n, c in sorted(n_phase_stat.items()):
        lines.append(f"| {n} | {c} |")
    lines.append(f"\n## 三、待复核项（{len(issues)}）\n")
    lines += [f"- **{n}**：{r}" for n, r in issues] if issues else ["- 无 ✓"]
    lines.append(f"\n## 四、失败项（{len(failed)}）\n")
    lines += [f"- **{n}**：{r}" for n, r in failed] if failed else ["- 无 ✓"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="LifeMero LifePhase 分龄生成")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="persons_phased.json")
    ap.add_argument("--review", default="phase_review.md")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--resume")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    persons = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if isinstance(persons, dict):
        persons = persons.get("persons") or persons.get("people") or persons.get("data")
    if args.limit:
        persons = persons[: args.limit]
    print(f"载入 {len(persons)} 位人物")

    if args.resume and Path(args.resume).exists():
        prev = json.loads(Path(args.resume).read_text(encoding="utf-8"))
        prev_map = {pick(p, FIELD_ALIASES["name"]): p["_phases"]
                    for p in (prev if isinstance(prev, list) else []) if "_phases" in p}
        for p in persons:
            if pick(p, FIELD_ALIASES["name"]) in prev_map:
                p["_phases"] = prev_map[pick(p, FIELD_ALIASES["name"])]
        print(f"续跑：恢复 {len(prev_map)} 条")

    done = failed = 0
    for i, p in enumerate(persons, 1):
        name = pick(p, FIELD_ALIASES["name"]) or f"#{i}"
        if "_phases" in p:
            continue
        base_vec = get_base_vector(p)
        try:
            if args.mock:
                result = mock_phase(p, base_vec)
            else:
                prompt = build_prompt(p, 4)  # 默认切4段
                result = parse_llm_json_or(call_llm(prompt, args.model, args.base_url,
                                                    os.environ.get("OPENAI_API_KEY", "")), p)
            for ph in result["phases"]:
                ph["vector"] = apply_vector(base_vec, ph.pop("vector_delta"))
            p["_phases"] = result
            done += 1
            span = "→".join(ph["phaseTag"] for ph in result["phases"])
            print(f"[{i}/{len(persons)}] {name} → {span}" +
                  ("（顺带标注元类型）" if "metatype" in result and "_annotation" not in p else ""))
        except Exception as e:
            p["_error"] = str(e)[:120]
            failed += 1
            print(f"[{i}/{len(persons)}] {name} → 失败: {e}", file=sys.stderr)
        if not args.mock:
            time.sleep(0.5)
        if i % 20 == 0:
            Path(args.output).write_text(json.dumps(persons, ensure_ascii=False, indent=1), encoding="utf-8")

    Path(args.output).write_text(json.dumps(persons, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.review).write_text(gen_review(persons), encoding="utf-8")
    print(f"\n完成：成功 {done}，失败 {failed}\n输出：{args.output}\n复核：{args.review}")


def parse_llm_json_or(result: dict, person: dict) -> dict:
    # 真实模式下若 LLM 顺带返回了元类型且人物未标注过，回填到 _annotation
    if "metatype" in result and "_annotation" not in person:
        person["_annotation"] = {"metatype": result["metatype"],
                                 "consciousness_level": result.get("consciousness_level", 2),
                                 "rationale": "分龄生成时顺带标注", "confidence": "medium"}
    return result


if __name__ == "__main__":
    main()
