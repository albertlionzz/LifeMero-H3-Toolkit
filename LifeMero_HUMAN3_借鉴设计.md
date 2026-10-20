# LifeMero × HUMAN 3.0 借鉴设计文档

> 基于 GitHub 项目 [mike7seven/Human](https://github.com/mike7seven/Human)（HUMAN 3.0 框架的架构化实现）与 LifeMero（life-mirror 虚拟人生经历体验平台）的对比分析，提炼 4 个可直接落地的功能设计。
> 技术栈约束：Flutter/Dart + Hive 持久化，现有数据集 116 位人物（96 历史 + 20 当代）× 22 行业，六维向量匹配引擎。

---

## 0. 结论先行

| 借鉴点 | 价值 | 改动量 | 优先级 |
|---|---|---|---|
| ① 人生版本号（时间轴分段） | 高：历史人物可"分龄体验"，叙事感质变 | 中 | **P0** |
| ② Metatype 元类型打标 | 高：匹配多一层"人格类型"召回 | 小（数据标注为主） | **P0** |
| ③ 四象限自评问卷 | 中：先定位自己再匹配，闭环感强 | 中 | P1 |
| ④ Fork 人生分支 | 中高：把"自定义分支"产品化、标准化 | 大 | P2 |

建议按 **② → ① → ③ → ④** 顺序实施：② 只需数据标注、见效最快；① 是叙事体验的核心升级；④ 依赖前两者的数据基础。

---

## 1. 对比分析归档（简版）

### 1.1 相似之处

1. **同一方法论底座**：都以数字孪生为核心方法论。Human System 明确 digital twin 为「表征镜像」而非自主代理，人保留在决策环中——与 LifeMero「只做模拟体验、不做决策代理」的边界设计一致。
2. **人的结构化拆解**：四象限（Mind/Body/Spirit/Vocation，源自 Wilber AQAL）+ 三层架构（Layer 0 生物硬件 / Layer 1 Human OS 认知 / Layer 2 AI 软件）↔ 六维向量。
3. **AI 驱动的匹配/评估**：六维匹配引擎 + 问卷 ↔ AI Assessment Prompt（原型/元类型定位）、AI Quorum 治理。
4. **人生版本化/分支**：语义化版本号 `AGE.QUARTER.BUILD`（如 `human-2.4-2025.0+b47`）+ Fork 个人实例 ↔ 自定义人生分支、孪生模拟。
5. **面向自我认知**：体验他人人生获得对照 ↔ 测评定位自己。

### 1.2 根本差异

- **方向相反**：LifeMero 向外体验别人的人生（内容消费向、轻松亲和）；HUMAN 3.0 向内建模自己（严肃的个人 AI 基础设施规范）。
- **数据形态**：真实人物画像数据集 vs 「如何定义任何人」的规范与提示词。

---

## 2. 功能设计

### 功能① 人生版本号：分龄体验（P0）

**目标**：给每位历史人物建立"分龄时间轴"，用户选择体验"30 岁的曾国藩 / 50 岁的曾国藩"，孪生模拟按人生阶段生成不同分支。

**对应 HUMAN 3.0 设计**：`human-{major}.{quarter}-{year}.{patch}+{build}` 版本串，Layer 0/1 独立语义化版本。

**数据结构（Dart / Hive TypeAdapter）**：

```dart
/// 人物单一年龄段切片
@HiveType(typeId: 21) // 接现有 typeId 序列
class LifePhase {
  @HiveField(0) final int ageFrom;        // 起始年龄
  @HiveField(1) final int ageTo;          // 结束年龄
  @HiveField(2) final String phaseTag;    // 阶段标签：寒窗/崛起/巅峰/困顿/转型
  @HiveField(3) final String summary;     // 该阶段人生概要（300字内）
  @HiveField(4) final List<double> vector;// 该阶段的六维向量（允许偏离全生涯均值）
  @HiveField(5) final List<String> keyEvents;   // 关键事件（3-5条）
  @HiveField(6) final String mentalModel; // 该阶段的思维模式/价值观
  @HiveField(7) final String socialState; // 社会状态：职业、身份、关系网
}

/// 现有 PersonProfile 扩展字段
@HiveField(10) final List<LifePhase> phases;     // 按年龄升序
@HiveField(11) final String versionString;       // 展示用，如 "life-42.3-2026.0"
```

**匹配引擎改动**：`MatchEngine` 支持两档粒度——

- 全生涯匹配（现状，`PersonProfile.vector`）
- **阶段匹配（新增）**：用户问卷结果与 `LifePhase.vector` 匹配，返回「最像你此刻的他们」：比如用户处于职业转型期，匹配出的是各人物"转型期切片"，结果卡片显示"这是他 44 岁时的处境"。

**UI 模块**：

- `phase_timeline.dart`：人物详情页新增横向时间轴组件，节点 = LifePhase，点击进入该阶段模拟
- 模拟入口新增筛选：「全生涯（默认）/ 指定年龄段」
- 分享图模板增加阶段标注：「30 岁的张居正 · 困顿期」

**数据生产方式**：不需要人工重写 116 份档案——用现有 `summary` + 生平年表批量生成 LifePhase（每人物 3~5 段），LLM 批处理 + 人工抽查 20% 校验。向量可由该阶段 `keyEvents` 嵌入后投影到六维。

**工作量估计**：数据管道 2 天，引擎改造 1 天，UI 2 天，测试 1 天 ≈ **1.5 周**。

---

### 功能② Metatype 元类型打标（P0）

**目标**：为 116 位人物增加"元类型/原型"标签，匹配结果多一层人格类型召回与解释。

**对应 HUMAN 3.0 设计**：原型（Archetype）/ 元类型（Metatype）体系；Level 1.0 从众者 / 2.0 个体者 / 3.0 整合者三层意识阶段。

**元类型体系设计**（结合 LifeMero 数据集特点定制，不建议照搬 HUMAN 3.0 全套）：

| 元类型 | 定义 | 数据集示例 |
|---|---|---|
| 开创者 | 从零建立新秩序/新事业 | 创业企业家、开国型人物 |
| 守成者 | 在既有体系内做深做强 | 职业经理人、中兴名臣 |
| 变革者 | 打破旧结构、推动转型 | 改革派人物 |
| 专精者 | 单一领域极致深耕 | 科学家、匠人型人物 |
| 逢源者 | 跨界整合、资源联结 | 商人、外交型人物 |
| 逆命者 | 出身/环境劣势下逆转 | 寒门崛起型人物 |

另附 `consciousnessLevel`（1~3 整数，对应 1.0/2.0/3.0）作为辅助维度，UI 上不强调层级高下（保持轻松亲和风格，避免说教感）。

**数据结构**：

```dart
@HiveField(12) final String metatype;       // 开创者/守成者/变革者/专精者/逢源者/逆命者
@HiveField(13) final int consciousnessLevel; // 1-3，辅助维度
```

**产品化用法**：

- 匹配结果卡片新增徽章：「你们都是【逆命者】」——比六维分数更有叙事性
- 匹配引擎支持双通道召回：向量相似度（现有）+ 元类型同类（新增），按 7:3 混合排序
- 首页新增「按元类型逛」入口：6 个卡片入口，点击看该类型人物群像
- 问卷结果可输出用户的"候选元类型"（为功能③铺路）

**数据生产方式**：116 人 × 1 次标注。LLM 批量标注 + 人工复核全部（一次性工作量约 1 天）。

**工作量估计**：标注 1 天 + 引擎混排 0.5 天 + UI 1 天 ≈ **3 天**。

---

### 功能③ 四象限自评问卷（P1）

**目标**：匹配前置一个 3 分钟自评，用户按 Mind/Body/Spirit/Vocation 四象限定位自己，输出四维雷达图 + 候选元类型，再驱动匹配。

**对应 HUMAN 3.0 设计**：HUMAN 3.0 Assessment Prompt 的四象限测评（Mind/Body/Spirit/Vocation × 三层级），但产品化为轻量问卷而非长对话。

**设计要点**：

- **12 题、3 分钟**：每象限 3 题，5 级量表。题面口语化（亲和风格），例如 Vocation：「你现在的工作，是在攒经验、攒资本，还是攒作品？」
- **输出**：
  - 四维雷达图（分享图素材，天然适配现有分享模块）
  - 四象限「最短板」提示 + 匹配方向：短板象限最像谁（成长对照）、长板象限最像谁（共鸣认同）
- **与六维的映射**：定义固定映射表——Mind→认知维度，Vocation→事业维度，Spirit→关系维度，Body→生活方式维度（按现有六维实际定义微调），问卷结果作为匹配输入而非独立体系

**数据结构**：

```dart
@HiveType(typeId: 22)
class SelfAssessment {
  @HiveField(0) final DateTime takenAt;
  @HiveField(1) final Map<String, int> scores;   // {mind:3, body:4, spirit:2, vocation:3}
  @HiveField(2) final String suggestedMetatype;  // 候选元类型
  @HiveField(3) final String matchedPersonId;    // 本次匹配的主人物
  @HiveField(4) final String assessmentId;
}
```

**Flutter 模块**：`features/assessment/`（question_flow、radar_chart、result_summary），问卷结果持久化到 Hive，支持多次测评对比（"三个月前的你"）。

**工作量估计**：题库设计 1 天 + UI 2 天 + 映射与匹配接入 1 天 ≈ **1 周**。

---

### 功能④ Fork 人生分支（P2）

**目标**：用户 Fork 任意人物的人生，从某个 LifePhase 节点开始改写决策，生成"如果当时……"的平行人生。这是"自定义分支"的标准化、产品化形态。

**对应 HUMAN 3.0 设计**：Fork Pattern——`Human-[YourName]` 个人实例继承上游规范、独立演化、定期合并上游变更。

**交互流程**：

1. 人物详情页 → 选一个 LifePhase 节点 → 「Fork 这个节点」
2. 展示该节点的关键决策点（`keyEvents` 中 AI 提炼的 decision point），用户选择自己的替代决策（2~3 选项，或自由输入）
3. LLM 基于人物性格向量 + 替代决策生成分支叙事（分段推进，每段结束再给决策点，类互动小说）
4. 分支可保存、命名、分享（分享图标注「Fork 自：张居正 · 44 岁 · 转型节点」）

**数据结构**：

```dart
@HiveType(typeId: 23)
class LifeFork {
  @HiveField(0) final String forkId;
  @HiveField(1) final String personId;
  @HiveField(2) final int phaseIndex;          // 起始 LifePhase
  @HiveField(3) final List<ForkDecision> decisions; // 用户的选择序列
  @HiveField(4) final List<String> narrative;  // 分支叙事（分章节缓存）
  @HiveField(5) final DateTime createdAt;
  @HiveField(6) final String name;             // 分支名
}

@HiveType(typeId: 24)
class ForkDecision {
  @HiveField(0) final String decisionPoint;
  @HiveField(1) final String chosenOption;
  @HiveField(2) final String rationale; // AI 生成：该选择在人物性格下的合理性注解
}
```

**与 HUMAN 3.0 Fork 模式的对齐**：`personId + phaseIndex` 相当于它的上游继承，`decisions` 相当于个人实例的差异化配置；未来可加「合并回主线」——把分支里用户认可的洞察沉淀到个人成长记录（对接你 life-mirror 的自我认知定位）。

**依赖与成本**：强依赖功能①（LifePhase 节点）与 LLM 生成接口；生成长度需限流（每段 300 字内）控制成本。

**工作量估计**：数据结构 0.5 天 + 生成管道 2 天 + 交互 UI 3 天 + 分享图 1 天 ≈ **2 周**。

---

## 3. 实施路线图

```
第 1 周      功能② 元类型打标        （数据标注 → 引擎混排 → UI 徽章）
第 2-3 周    功能① 分龄版本号        （数据管道 → 引擎 → 时间轴 UI）
第 4 周      功能③ 四象限问卷        （题库 → UI → 匹配接入）
第 5-6 周    功能④ Fork 分支         （依赖①③的节点与画像数据）
持续         数据维护                （新人物入库时同步产出 phases + metatype）
```

## 4. 风险与注意事项

1. **风格守护**：HUMAN 3.0 的层级话语（1.0 从众者/NPC 等）带有评判色彩，移植时全部转译为轻松亲和的表达，`consciousnessLevel` 不在 UI 强调高低。
2. **数据一致性**：LifePhase 的阶段向量会与全生涯向量冲突，需明确匹配入口用哪一档，避免两套结果打架（建议默认全生涯，阶段匹配作为"深度模式"）。
3. **历史人物当代性**：Fork 分支生成涉及历史人物"改写人生"，内容审核需守住真实历史与虚构叙事的边界提示（页脚固定「本分支为模拟推演，非史实」）。
4. **成本控制**：Fork 的 LLM 生成分段限流 + 本地缓存叙事，Hive 存文本即可，不引入额外后端依赖。

---

*文档生成：2026-10-20 · 参考仓库：mike7seven/Human（MIT License）· 已克隆至本地可随时复查*
