# LifeMero × HUMAN 3.0 Toolkit

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/)

> 元类型标注 + 分龄切片 + 双通道匹配引擎 + UI 视觉稿，配套设计文档。

## 目录结构

```
LifeMero-H3-Toolkit/
├── LifeMero_HUMAN3_借鉴设计.md      # 总设计文档（4个功能 + 数据结构 + 路线图）
├── LICENSE                          # MIT
├── requirements.txt                 # 仅真实模式需要 requests（mock 零依赖）
└── tools/
    ├── annotate_metatype.py         # 功能② 元类型批量标注（LLM + mock/续跑/复核报告）
    ├── phase_pipeline.py            # 功能① LifePhase 分龄生成（Δ偏移量方案）
    ├── simulate_blend.py            # 双通道混排算法模拟验证（向量70% + 元类型30%）
    ├── persons_sample.json          # 10人示例数据集
    ├── ui_mockup.html               # UI 视觉稿（浏览器直接打开）
    └── lib/matching/
        └── metatype_engine.dart     # Flutter 双通道匹配引擎模块
```

## 快速开始

**零依赖跑通全流程**（mock 模式不调 API、不需要 requests，用于验证管道）：

```bash
cd tools

# 1) 元类型标注（mock）
python annotate_metatype.py --input persons_sample.json --mock

# 2) 分龄切片（mock，吃上一步的输出）
python phase_pipeline.py --input persons_annotated.json --mock

# 3) 双通道混排效果模拟
python simulate_blend.py --input persons_annotated.json
```

**真实标注**（任选 OpenAI 兼容 API：DeepSeek/通义/本地 llama-server 均可）：

```bash
pip install -r requirements.txt

export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 可选，默认 OpenAI

# 116人全量标注约几分钱；失败自动重试，中断后用 --resume 续跑
python annotate_metatype.py --input persons.json --model deepseek-chat
python phase_pipeline.py   --input persons_annotated.json --model deepseek-chat

# 断点续跑（只补缺失条目）
python annotate_metatype.py --input persons.json --resume persons_annotated.json
python phase_pipeline.py   --input persons.json --resume persons_phased.json
```

> API Key 只走环境变量，切勿写进代码提交；仓库 `.gitignore` 已屏蔽 `.env` 与管道输出文件。

## 数据流水线

```
persons.json（你的116人数据集）
    ↓ annotate_metatype.py
persons_annotated.json（+元类型）→ review_report.md（人工复核🔴项）
    ↓ phase_pipeline.py
persons_phased.json（+分龄切片）→ phase_review.md（人工复核待确认项）
    ↓ simulate_blend.py 验证排序策略
    ↓ 接入 Flutter 工程
metatype_engine.dart（双通道混排）+ ui_mockup.html 对应的 UI 组件
```

## 在笔记本上推送到远程仓库

### 方式一：PowerShell（推荐）

```powershell
cd LifeMero-H3-Toolkit
.\push_to_remote.ps1 -RemoteUrl https://github.com/你的用户名/LifeMero-H3-Toolkit.git
```

### 方式二：手动 git

```bash
cd LifeMero-H3-Toolkit
git remote add origin https://github.com/你的用户名/LifeMero-H3-Toolkit.git
git push -u origin master
```

> 远程仓库先在 GitHub/Gitee 网页上创建（**不要**勾选初始化 README，保持空仓库）。
> Gitee 示例：`https://gitee.com/你的用户名/lifemero-h3-toolkit.git`
> 推送时按提示登录即可（或配置 Personal Access Token / SSH 密钥）。
