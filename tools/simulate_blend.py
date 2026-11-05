#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双通道混排算法效果模拟：验证 向量70% + 元类型30% 的排序变化"""
import argparse
import json
import math
import sys
from pathlib import Path

W_VEC, W_META = 0.7, 0.3

def cosine(a, b):
    dot = sum(x*y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x*x for x in a)), math.sqrt(sum(x*x for x in b))
    return dot/(na*nb) if na and nb else 0.0

def rank(user_vec, user_meta, pool, same_bonus=1.0, level_diff=0.9):
    """user_meta: (元类型, 层级) 元组或 None"""
    meta_name, meta_level = (user_meta or (None, None))
    out = []
    for p in pool:
        sim = max(0.0, min(1.0, cosine(user_vec, p["vector"])))
        same = bool(meta_name and p.get("metatype") == meta_name)
        bonus = same_bonus if same else 0.0
        if same and meta_level and p.get("consciousness_level") and \
           p["consciousness_level"] != meta_level:
            bonus *= level_diff
        score = W_VEC*sim + W_META*bonus
        out.append({**p, "sim": round(sim, 3), "same": bool(same), "score": round(score, 3)})
    return sorted(out, key=lambda x: -x["score"])

ap = argparse.ArgumentParser(description="双通道混排算法效果模拟：向量70% + 元类型30%")
ap.add_argument("--input", default="persons_annotated.json",
                help="annotate_metatype.py 的输出文件（含 _annotation 字段）")
args = ap.parse_args()

path = Path(args.input)
if not path.exists():
    sys.exit(f"输入文件不存在: {args.input}\n"
             f"请先运行: python annotate_metatype.py --input persons.json --mock "
             f"--output persons_annotated.json")
persons = json.loads(path.read_text(encoding="utf-8"))
pool = [{"name": p.get("name", "?"), "vector": p.get("vector") or [0.5] * 6,
         "metatype": p["_annotation"]["metatype"],
         "consciousness_level": p["_annotation"]["consciousness_level"]}
        for p in persons if "_annotation" in p]

if not pool:
    sys.exit(f"{args.input} 中没有带 _annotation 的人物，请先运行 annotate_metatype.py 标注")

# 模拟用户：一位处于逆境逆转期的科技创业者（六维偏向：开创性高、逆商高、关系一般）
user_vec = [0.85, 0.75, 0.5, 0.7, 0.6, 0.95]
user_meta = ("逆命者", 2)  # 用户候选元类型：逆命者，层级2

pure = rank(user_vec, None, pool)          # 旧引擎：纯向量
blend = rank(user_vec, user_meta, pool)    # 新引擎：双通道

print("=" * 62)
print("模拟用户画像：逆境逆转期科技创业者（元类型=逆命者·Lv2）")
print("=" * 62)
print(f"\n【旧引擎·纯向量Top5】")
for i, p in enumerate(pure[:5], 1):
    print(f"  {i}. {p['name']:<5} 相似度={p['sim']:.3f}")
print(f"\n【新引擎·双通道Top5】")
for i, p in enumerate(blend[:5], 1):
    tag = "⚡同类" if p["same"] else "    "
    print(f"  {i}. {p['name']:<5} 相似度={p['sim']:.3f} {tag} 总分={p['score']:.3f}")

# 效果指标：同类人物在新引擎下的排名提升
print("\n【元类型同类排名提升】")
old_rank = {p["name"]: i+1 for i, p in enumerate(pure)}
for i, p in enumerate(blend, 1):
    if p["same"]:
        print(f"  {p['name']}: 第{old_rank[p['name']]}名 → 第{i}名 (↑{old_rank[p['name']]-i})")

# 分布健康度：检查是否元类型通道"绑架"排序（同类全靠前=权重过大信号）
same_scores = [p["score"] for p in blend if p["same"]]
diff_scores = [p["score"] for p in blend if not p["same"]]
overlap = bool(diff_scores and same_scores and
               max(diff_scores) > min(same_scores))
print(f"\n【健康度检查】同类最高分={max(same_scores):.3f}，异类最高分={max(diff_scores):.3f}")
print("  ✓ 交错分布：异类高分人物仍能进入前列，元类型通道未绑架排序" if overlap
      else "  ⚠ 排序被元类型通道主导，建议把权重调至 8:2")
