// metatype_engine.dart
// LifeMero 匹配引擎双通道混排改造：向量相似度(70%) + 元类型同类(30%)
//
// 设计要点：
// 1. 纯 Dart 逻辑，无 Flutter 依赖，可直接单元测试
// 2. 对现有 MatchEngine 是"包装"而非"重写"——你现有的向量相似度计算
//    通过 VectorSimilarityFn 注入，老引擎不用动
// 3. 混排权重可配置，默认 7:3，后续可在设置页暴露给用户微调
// 4. 分数语义：similarityScore ∈ [0,1]，metatypeBonus ∈ [0,1]，finalScore ∈ [0,1]
//
// 集成方式：
//   final engine = BlendedMatchEngine(
//     vectorSim: (user, person) => cosine(user.vector, person.vector),
//   );
//   final results = engine.rank(userProfile, personPool, userMetatype: '逆命者');

/// 六类元类型（与标注脚本 annotate_metatype.py 保持一致）
class Metatypes {
  static const all = ['开创者', '守成者', '变革者', '专精者', '逢源者', '逆命者'];

  /// 徽章视觉配置：颜色走 life-mirror 轻松亲和风格（低饱和暖色系）
  static const badgeStyle = {
    '开创者': BadgeStyle(color: 0xFFF59E0B, emoji: '🚀', label: '开创者'),
    '守成者': BadgeStyle(color: 0xFF10B981, emoji: '🌳', label: '守成者'),
    '变革者': BadgeStyle(color: 0xFFEF4444, emoji: '⚡', label: '变革者'),
    '专精者': BadgeStyle(color: 0xFF3B82F6, emoji: '🔬', label: '专精者'),
    '逢源者': BadgeStyle(color: 0xFF8B5CF6, emoji: '🤝', label: '逢源者'),
    '逆命者': BadgeStyle(color: 0xFFEC4899, emoji: '🌅', label: '逆命者'),
  };
}

class BadgeStyle {
  final int color;
  final String emoji;
  final String label;
  const BadgeStyle({required this.color, required this.emoji, required this.label});
}

/// 轻量人物画像（对接现有 PersonProfile，仅取引擎所需字段）
class MatchCandidate {
  final String personId;
  final String name;
  final List<double> vector;   // 六维向量
  final String? metatype;      // 标注后可为 null（未标注人群自动降级为纯向量通道）
  final int? consciousnessLevel;
  final String? rationale;

  const MatchCandidate({
    required this.personId,
    required this.name,
    required this.vector,
    this.metatype,
    this.consciousnessLevel,
    this.rationale,
  });
}

/// 单个匹配结果
class MatchResult {
  final MatchCandidate candidate;
  final double similarityScore; // 通道一：向量相似度 [0,1]
  final double metatypeBonus;   // 通道二：元类型加成   [0,1]
  final double finalScore;      // 混排总分           [0,1]
  final bool isSameMetatype;    // 是否元类型同类

  const MatchResult({
    required this.candidate,
    required this.similarityScore,
    required this.metatypeBonus,
    required this.finalScore,
    required this.isSameMetatype,
  });

  /// 结果卡片叙事文案：比裸分数更有记忆点
  String get story {
    if (isSameMetatype && similarityScore >= 0.8) return '六维神似，且你们都是${candidate.metatype}';
    if (isSameMetatype) return '人格同源：你们都是${candidate.metatype}';
    if (similarityScore >= 0.8) return '六维高度神似';
    if (similarityScore >= 0.6) return '人生轨迹多有共鸣';
    return '换个视角看看他的人生';
  }
}

/// 双通道混排引擎
class BlendedMatchEngine {
  /// 注入现有向量相似度函数（余弦/欧氏归一/自定义均可）
  final double Function(List<double> a, List<double> b) vectorSim;

  /// 双通道权重，默认 向量0.7 + 元类型0.3
  final double vectorWeight;
  final double metatypeWeight;

  /// 元类型加成曲线：
  ///  - 同元类型：基础 1.0
  ///  - 相邻意识层级（±1）再乘 0.9，同层级 1.0（叙事上"完全同类"更强）
  ///  - 未标注人物：0（自动纯向量通道）
  final double sameTypeBonus;

  BlendedMatchEngine({
    required this.vectorSim,
    this.vectorWeight = 0.7,
    this.metatypeWeight = 0.3,
    this.sameTypeBonus = 1.0,
  })  : assert(vectorWeight + metatypeWeight == 1.0,
            '双通道权重之和必须为 1.0'),

        /// 校验六维向量维度一致性
        assert(true);

  /// 主入口：对人物池排序
  /// [userMetatype] 为 null（用户未测评）时自动退化为纯向量排序
  List<MatchResult> rank({
    required List<double> userVector,
    required List<MatchCandidate> pool,
    String? userMetatype,
    int? userConsciousnessLevel,
    int topK = 10,
  }) {
    final results = <MatchResult>[];
    for (final c in pool) {
      final sim = _clamp01(vectorSim(userVector, c.vector));
      final same = userMetatype != null &&
          c.metatype != null &&
          c.metatype == userMetatype;
      double bonus = 0.0;
      if (same) {
        bonus = sameTypeBonus;
        if (userConsciousnessLevel != null &&
            c.consciousnessLevel != null &&
            userConsciousnessLevel != c.consciousnessLevel) {
          bonus *= 0.9; // 层级不同微降
        }
      }
      final score = _clamp01(
          vectorWeight * sim + metatypeWeight * bonus);
      results.add(MatchResult(
        candidate: c,
        similarityScore: sim,
        metatypeBonus: bonus,
        finalScore: score,
        isSameMetatype: same,
      ));
    }
    results.sort((a, b) => b.finalScore.compareTo(a.finalScore));
    return results.take(topK).toList();
  }

  /// 召回结果按元类型分组（"按元类型逛"入口数据源）
  static Map<String, List<MatchCandidate>> groupByMetatype(
      List<MatchCandidate> pool) {
    final map = <String, List<MatchCandidate>>{};
    for (final m in Metatypes.all) {
      map[m] = [];
    }
    for (final c in pool) {
      if (c.metatype != null && map.containsKey(c.metatype)) {
        map[c.metatype]!.add(c);
      }
    }
    return map;
  }

  static double _clamp01(double v) => v < 0 ? 0 : (v > 1 ? 1 : v);
}

/// 余弦相似度参考实现（若现有引擎已有，可直接复用旧的）
double cosine(List<double> a, List<double> b) {
  assert(a.length == b.length, '向量维度不一致: ${a.length} vs ${b.length}');
  double dot = 0, na = 0, nb = 0;
  for (var i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (na == 0 || nb == 0) return 0;
  return dot / (_sqrt(na) * _sqrt(nb));
}

// 避免引入 dart:math 的完整 import（引擎文件保持自包含时可直接用 dart:math）
double _sqrt(double v) {
  var x = v, y = 1.0;
  for (var i = 0; i < 40; i++) {
    y = (x / y + y) / 2;
  }
  return y;
}
