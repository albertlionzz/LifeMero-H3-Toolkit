#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LifeMero 人物元类型批量标注脚本（功能②）
=========================================
从人物数据集 JSON 读取档案，调用 OpenAI 兼容 LLM 批量标注：
  - metatype（六选一：开创者/守成者/变革者/专精者/逢源者/逆命者）
  - consciousness_level（1-3，辅助维度）
  - rationale（一句话标注理由）
输出：
  - persons_annotated.json  全量标注结果
  - review_report.md        人工复核清单（低置信度/失败项置顶）

用法：
  # 1) 先用 mock 模式验证管道（不调 API，零成本）
  python3 annotate_metatype.py --input persons.json --mock

  # 2) 真实标注（OpenAI 兼容 API：DeepSeek/通义/本地 llama-server 均可）
  export OPENAI_API_KEY=sk-xxx
  export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 可选，默认 OpenAI
  python3 annotate_metatype.py --input persons.json --model deepseek-chat

  # 3) 断点续跑：失败的/跳过的条目重跑时会自动补标
  python3 annotate_metatype.py --input persons.json --resume persons_annotated.json

输入格式兼容：自动识别常见字段名
  名字: name/nickname/title        简介: summary/description/bio/intro
  时代: era/dynasty/period         行业: industry/field/occupation/domain
  已有六维: vector/dimensions/traits（存在则作为参考信息送入 prompt）
"""

import argparse
import json
import os
import re
import sys
import time
import random
from datetime import datetime
from pathlib import Path

# 注意：requests 采用延迟导入（见 call_llm）——mock 模式验证管道零依赖，
# 只有真实调用 LLM 时才需要 pip install requests

METATYPES = ["开创者", "守成者", "变革者", "专精者", "逢源者", "逆命者"]

META_DEFINITIONS = {
    "开创者": "从零建立新秩序、新事业、新范式的人",
    "守成者": "在既有体系内做深做强、巩固与优化的人",
    "变革者": "打破旧结构、推动激烈转型的人",
    "专精者": "在单一领域极致深耕、以专业立身的人",
    "逢源者": "跨界整合资源、连接多方的人",
    "逆命者": "出身或环境存在重大劣势，最终实现逆转的人",
}

FIELD_ALIASES = {
    "name": ["name", "nickname", "title", "姓名", "名字"],
    "summary": ["summary", "description", "bio", "intro", "简介", "描述", "生平"],
    "era": ["era", "dynasty", "period", "时代", "朝代", "年代"],
    "industry": ["industry", "field", "occupation", "domain", "行业", "领域", "职业"],
}


def pick(d: dict, keys: list) -> str:
    for k in keys:
        if k in d and d[k]:
            v = d[k]
            if isinstance(v, str):
                return v
            if isinstance(v, (list, dict)):
                return json.dumps(v, ensure_ascii=False)
    return ""


def build_prompt(person: dict) -> str:
    name = pick(person, FIELD_ALIASES["name"]) or "（无名）"
    summary = (pick(person, FIELD_ALIASES["summary"]) or "")[:600]
    era = pick(person, FIELD_ALIASES["era"])
    industry = pick(person, FIELD_ALIASES["industry"])
    vector = pick(person, ["vector", "dimensions", "traits"])

    meta_lines = "\n".join(f"- {k}：{v}" for k, v in META_DEFINITIONS.items())
    return f"""你是人物画像标注专家。请为以下人物标注元类型。

元类型定义（必须六选一）：
{meta_lines}

人物信息：
- 姓名：{name}
- 时代：{era or '未知'}
- 行业/领域：{industry or '未知'}
- 生平简介：{summary or '无'}
- 六维向量：{vector or '无'}

要求：
1. metatype 从六个选项中选最贴切的一个
2. consciousness_level 填 1/2/3（1=遵循外部规则驱动，2=自我目标驱动，3=整合多重视角、创造新范式；仅作辅助维度）
3. rationale 用一句话（30字内）说明理由
4. confidence 填 high/medium/low：生平信息充分且类型明确=high；信息有限或类型边界模糊=medium；几乎无法判断=low

只输出 JSON，格式：{{"metatype": "...", "consciousness_level": 1, "rationale": "...", "confidence": "high"}}"""


def extract_json(text: str) -> str:
    """从 LLM 回复中提取第一个完整 JSON 对象字符串。

    容忍：markdown 代码块包裹、前后杂讯、JSON 内一级以上嵌套、字符串中的花括号。
    与 phase_pipeline.py 中的同名函数保持一致。
    """
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    start = t.find("{")
    if start < 0:
        raise ValueError("回复中未找到 JSON")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return t[start:i + 1]
    raise ValueError("回复中 JSON 不完整")


def parse_llm_json(text: str) -> dict:
    """从 LLM 回复中稳健提取 JSON（容忍 markdown 代码块/前后缀/嵌套）"""
    obj = json.loads(extract_json(text))
    if obj.get("metatype") not in METATYPES:
        raise ValueError(f"metatype 非法: {obj.get('metatype')}")
    lvl = obj.get("consciousness_level")
    obj["consciousness_level"] = int(lvl) if lvl in (1, 2, 3) or (isinstance(lvl, str) and lvl.isdigit() and int(lvl) in (1, 2, 3)) else 2
    if obj.get("confidence") not in ("high", "medium", "low"):
        obj["confidence"] = "medium"
    obj["rationale"] = str(obj.get("rationale", ""))[:60]
    return obj


def call_llm(prompt: str, model: str, base_url: str, api_key: str, max_retry: int = 3) -> dict:
    try:
        import requests
    except ImportError:
        raise RuntimeError("真实标注模式需要 requests 库，请先: pip install requests（mock 模式无需安装）")
    for attempt in range(max_retry):
        try:
            r = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.1, "max_tokens": 200},
                timeout=60,
            )
            r.raise_for_status()
            return parse_llm_json(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            if attempt == max_retry - 1:
                raise
            wait = 2 ** attempt * 2
            print(f"    重试 {attempt+1}/{max_retry}（{e}），{wait}s 后...", file=sys.stderr)
            time.sleep(wait)


def mock_annotate(person: dict) -> dict:
    """无 Key 演示模式：关键词规则打标，仅用于验证管道，正式数据请用真实 LLM"""
    text = (pick(person, FIELD_ALIASES["summary"]) + pick(person, FIELD_ALIASES["name"]) +
            pick(person, FIELD_ALIASES["industry"]))
    rules = [
        (("逆命者", 1), ["寒门", "出身贫", "逆境", "残疾", "流亡", "逆袭", "平民"]),
        (("变革者", 3), ["改革", "变法", "革命", "转型", "推倒", "颠覆"]),
        (("开创者", 2), ["创办", "创立", "开创", "第一人", "奠基", "发明"]),
        (("专精者", 2), ["深耕", "专注", "研究", "科学", "技艺", "大师"]),
        (("逢源者", 2), ["整合", "外交", "联结", "跨界", "撮合", "斡旋"]),
        (("守成者", 1), ["守成", "巩固", "治理", "管理", "传承", "中兴"]),
    ]
    for (meta, lvl), kws in rules:
        if any(k in text for k in kws):
            return {"metatype": meta, "consciousness_level": lvl,
                    "rationale": f"mock规则命中：{meta}", "confidence": "low"}
    return {"metatype": random.choice(METATYPES), "consciousness_level": 2,
            "rationale": "mock规则未命中，随机", "confidence": "low"}


def gen_review_report(persons: list) -> str:
    from collections import Counter
    stats = Counter(p["_annotation"]["metatype"] for p in persons if "_annotation" in p)
    total = sum(stats.values())
    lines = [
        "# LifeMero 元类型标注复核报告",
        f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "## 一、分布统计\n",
        "| 元类型 | 人数 | 占比 |",
        "|---|---|---|",
    ]
    for meta in METATYPES:
        n = stats.get(meta, 0)
        lines.append(f"| {meta} | {n} | {n/total*100:.1f}% |" if total else f"| {meta} | 0 | - |")
    lines.append(f"| **合计** | **{total}** | |")

    low = [p for p in persons if "_annotation" in p and p["_annotation"].get("confidence") == "low"]
    med = [p for p in persons if "_annotation" in p and p["_annotation"].get("confidence") == "medium"]
    failed = [p for p in persons if "_annotation" not in p]
    lines += ["\n## 二、复核优先级\n",
              f"- 🔴 低置信度（必须人工复核）：**{len(low)}** 人",
              f"- 🟡 中置信度（建议抽查）：**{len(med)}** 人",
              f"- ⚫ 标注失败（需重跑）：**{len(failed)}** 人\n"]

    if low:
        lines.append("## 三、低置信度清单\n\n| 姓名 | 标注 | 理由 |")
        lines.append("|---|---|---|")
        for p in low:
            a = p["_annotation"]
            lines.append(f"| {pick(p, FIELD_ALIASES['name'])} | {a['metatype']} | {a['rationale']} |")
    if failed:
        lines.append("\n## 四、失败清单（用 --resume 重跑）\n\n| 姓名 | 原因 |")
        lines.append("|---|---|---|")
        for p in failed:
            lines.append(f"| {pick(p, FIELD_ALIASES['name'])} | {p.get('_error', '未知')} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="LifeMero 元类型批量标注")
    ap.add_argument("--input", required=True, help="人物数据集 JSON 文件")
    ap.add_argument("--output", default="persons_annotated.json")
    ap.add_argument("--review", default="review_report.md")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    ap.add_argument("--mock", action="store_true", help="无 Key 演示模式")
    ap.add_argument("--resume", help="断点续跑：读取已有标注结果，只补缺")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个（测试用）")
    args = ap.parse_args()

    raw = Path(args.input).read_text(encoding="utf-8")
    data = json.loads(raw)
    persons = data if isinstance(data, list) else data.get("persons") or data.get("people") or data.get("data")
    if not isinstance(persons, list):
        sys.exit("无法识别数据结构：请提供 JSON 数组，或含 persons/people/data 键的对象")
    if args.limit:
        persons = persons[: args.limit]
    print(f"载入 {len(persons)} 位人物")

    # 断点续跑：合并已有标注
    if args.resume and Path(args.resume).exists():
        prev = json.loads(Path(args.resume).read_text(encoding="utf-8"))
        prev_map = {}
        for p in (prev if isinstance(prev, list) else prev.get("persons", [])):
            if "_annotation" in p:
                prev_map[pick(p, FIELD_ALIASES["name"])] = p["_annotation"]
        restored = 0
        for p in persons:
            key = pick(p, FIELD_ALIASES["name"])
            if key in prev_map:
                p["_annotation"] = prev_map[key]
                restored += 1
        print(f"续跑：恢复 {restored} 条已有标注")

    done = failed = 0
    for i, p in enumerate(persons, 1):
        name = pick(p, FIELD_ALIASES["name"]) or f"#{i}"
        if "_annotation" in p:
            continue
        try:
            result = mock_annotate(p) if args.mock else call_llm(
                build_prompt(p), args.model, args.base_url, os.environ.get("OPENAI_API_KEY", ""))
            p["_annotation"] = result
            done += 1
            print(f"[{i}/{len(persons)}] {name} → {result['metatype']} ({result['confidence']})")
        except Exception as e:
            p["_error"] = str(e)[:120]
            failed += 1
            print(f"[{i}/{len(persons)}] {name} → 失败: {e}", file=sys.stderr)
        # 节流：真实 API 模式下每条间隔 0.5s
        if not args.mock:
            time.sleep(0.5)
        # 每 20 条落盘一次，防止中断丢失
        if i % 20 == 0:
            Path(args.output).write_text(json.dumps(persons, ensure_ascii=False, indent=1), encoding="utf-8")

    Path(args.output).write_text(json.dumps(persons, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.review).write_text(gen_review_report(persons), encoding="utf-8")
    print(f"\n完成：成功 {done}，失败 {failed}")
    print(f"输出：{args.output}\n复核清单：{args.review}")


if __name__ == "__main__":
    main()
