# staff-officer 🎯

**参谋助手论情绪追踪插件** — 基于规则引擎的用户情绪状态机，配合 `ai-staff-officer` skill 使用。

> 基于王怀志/郭政《参谋助手论——为首长服务的艺术》（西北大学出版社1994）实现。

## 项目简介

staff-officer 是一个轻量级、可解释的情绪状态追踪插件，用于 Hermes Agent 智能体框架。它通过规则引擎检测用户消息中的情绪信号，维护跨轮次的情绪状态机，并在 system prompt 中注入情绪档案，帮助 AI 更好地理解和回应用户情绪。

**核心特点**：
- **基于规则**：纯正则表达式匹配，不依赖 LLM，零 token 消耗
- **可解释**：每条检测结果都包含命中规则、信号来源、状态转移说明
- **轻量级**：<1ms 检测延迟，<1MB 内存占用
- **插件化设计**：无缝集成 Hermes Agent 框架

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    staff-officer 插件                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  规则引擎     │    │  状态机      │    │  输出指导    │  │
│  │  (正则匹配)   │ →  │  (状态转移)   │ →  │  (行为建议)   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         ↓                   ↓                   ↓           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Hermes Agent 框架                        │  │
│  │  - sync_turn()      每轮对话后检测情绪                │  │
│  │  - system_prompt_block()  注入情绪档案                │  │
│  │  - prefetch()       会话启动时加载历史                │  │
│  │  - on_pre_compress() 压缩前保存快照                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 状态机说明

### 情绪状态定义

| 状态 | 标签 | 效价(valence) | 唤醒度(arousal) | 极性(polarity) |
|------|------|--------------|----------------|----------------|
| neutral | 中性 | 0 | 0 | neutral |
| happy | 高兴 | 1 | 1 | positive |
| frustrated | 烦躁 | -1 | 2 | negative |
| anxious | 焦虑 | -1 | 1 | negative |
| tired | 疲惫 | -0.5 | -1 | negative |
| hesitant | 犹豫 | -0.5 | 0 | negative |
| invested | 投入 | 0.5 | 1 | positive |
| impulsive | 冲动 | -1 | 3 | negative |

### 状态转移规则

1. **高置信度信号**：直接触发状态转移
2. **中置信度信号**：需要累积（5轮内3+个相同极性信号，或2个完全相同信号）
3. **低置信度信号**：只记录，不转移状态

### 衰减机制

- **3轮无信号**：高唤醒状态（frustrated, impulsive）衰减到中等唤醒状态（anxious, hesitant）
- **5轮无信号**：任意状态衰减到 neutral

## 规则引擎说明

### 信号检测

规则引擎使用正则表达式匹配用户消息中的情绪信号。每个规则包含：
- **正则模式**：匹配文本的正则表达式
- **信号名称**：匹配到的信号标识
- **目标状态**：信号指向的情绪状态
- **置信度**：high / medium / low

### 冲突解决

当检测到多个冲突信号时：
1. **高置信度优先**：high > medium > low
2. **positive 优先**：置信度相同时，positive 极性优先于 negative
3. **取第一个**：仍然冲突时，取排序后的第一个信号

### 规则示例

```python
# 烦躁/愤怒
(r"算了|无所谓|随便|不想[聊弄搞干]", "give_up", "frustrated", "high")
(r"烦[死透了]|气死|受不了|忍不了", "anger_explicit", "frustrated", "high")

# 高兴/得意
(r"哈哈|笑死|😄|👍|太好了|漂亮|牛[逼批]", "delight", "happy", "high")
(r"搞定了|完成了|解决了|成功|过了", "achievement", "happy", "high")
```

## 项目结构

```
staff-officer/
├── __init__.py              # 主插件代码（状态机、规则引擎、Hooks）
├── test_plugin.py           # 单元测试脚本
├── plugin.yaml              # 插件元数据（版本、hooks）
├── README.md                # 本文档
├── examples/
│   ├── demo.py              # 交互式演示脚本
│   └── evaluate.py          # 评估脚本（输出 Accuracy/Precision/Recall/F1）
└── data/
    ├── sample_eval.jsonl    # 评估数据集（40 条标注样本）
    └── eval_results.json    # 评估结果（由 evaluate.py 生成）
```

## 安装方式

### 前置条件
- Python 3.9+
- Hermes Agent（已配置）

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/panglihaoshuai/staff-officer.git
cd staff-officer
```

2. **复制到 Hermes 插件目录**
```bash
cp -r . ~/.hermes/plugins/staff-officer/
```

3. **启用插件**
```bash
hermes plugins enable staff-officer
```

4. **重启 Hermes 会话**
插件会在下次会话时自动加载。

## Demo 运行方式

### 交互式演示

```bash
cd ~/.hermes/plugins/staff-officer
python3 examples/demo.py
```

演示支持：
- 输入中文文本，实时观察情绪状态变化
- 输入 `demo` 运行预设演示对话
- 输入 `quit` 或 `exit` 退出

### 示例输出

```
User: 算了不想弄了
  检测到的信号: give_up
  状态转移: 中性 (neutral) → 烦躁 (frustrated)
  置信度: high
  效价(valence): -1, 唤醒度(arousal): 2
  解释: 检测到信号：give_up，状态从 neutral 变为 frustrated。
  应该做: 先共情1句、暂停建议、转移到可执行的事
  不要说: 别着急、冷静一下、你这样不对

  Prompt block 注入:
    用户当前情绪：烦躁（frustrated）
    应该做：先共情1句、暂停建议、转移到可执行的事
```

## 测试方式

### 运行单元测试

```bash
cd ~/.hermes/plugins/staff-officer
python3 test_plugin.py
```

### 测试覆盖

- **规则引擎测试**：35 个测试用例（含确认词、超短消息、中性文本）
- **反例测试**：13 个测试用例（防止普通/负面文本误判为 happy）
- **状态机测试**：高/中/低置信度转移、渐进衰减、快照恢复
- **情绪指导测试**：8 种状态的 do/dont 指导
- **多轮模拟测试**：9 轮对话状态转移
- **信号冲突解决测试**：5 个冲突场景
- **长对话测试**：50+ 轮对话，验证状态机稳定性

### 测试说明

当前单元测试用例通过率为 100%，该结果仅说明规则逻辑在既定测试样例中运行正常，不代表真实场景下的情绪识别准确率。

## 评估方式

### 运行评估脚本

```bash
cd ~/.hermes/plugins/staff-officer
python3 examples/evaluate.py
```

### 评估数据集

评估使用 `data/sample_eval.jsonl`，包含 40 条标注样本，覆盖 8 种情绪状态。

**注意**：这是一个小样本 smoke evaluation，仅用于验证评估脚本和规则引擎的基本功能，不代表真实场景下的情绪识别准确率。如需更准确的评估，需要更大规模的独立标注数据集。

每行格式：
```json
{"text": "算了不想弄了", "label": "frustrated"}
```

### 评估指标

评估脚本输出：
- **Accuracy**：总体准确率
- **per-class Precision**：每个类别的精确率
- **per-class Recall**：每个类别的召回率
- **per-class F1-score**：每个类别的 F1 分数
- **Confusion Matrix**：混淆矩阵

### 示例评估结果

```
评估结果
============================================================

总体准确率 (Accuracy): 100.00%

各类别指标:
类别            Precision    Recall       F1-score     Support
------------------------------------------------------------
anxious         100.00%      100.00%      100.00%      5
frustrated      100.00%      100.00%      100.00%      5
happy           100.00%      100.00%      100.00%      7
hesitant        100.00%      100.00%      100.00%      5
impulsive       100.00%      100.00%      100.00%      5
invested        100.00%      100.00%      100.00%      5
neutral         100.00%      100.00%      100.00%      3
tired           100.00%      100.00%      100.00%      5
```

**注意**：以上结果基于 40 条小样本 smoke evaluation，不代表真实场景下的情绪识别准确率。

## 示例输出

### detect_emotion_detailed() 返回结构

```python
{
    "text": "算了不想弄了",
    "current_state": "frustrated",
    "previous_state": "neutral",
    "changed": true,
    "valence": -1,
    "arousal": 2,
    "confidence": "high",
    "signals": [
        {
            "signal": "give_up",
            "target_state": "frustrated",
            "confidence": "high"
        }
    ],
    "matched_rules": ["give_up"],
    "explanation": "检测到信号：give_up，状态从 neutral 变为 frustrated。"
}
```

### system_prompt_block() 注入内容

```
## 参谋助手·情绪雷达
用户当前情绪：烦躁（frustrated）
效价：-1  唤醒度：2
已对话轮次：5
最近信号：
  - [high] give_up: "算了不想弄了"
应该做：先共情1句、暂停建议、转移到可执行的事
不要说：别着急、冷静一下、你这样不对
⚠️ 用户可能处于冲动状态，考虑缓办或补充信息。
```

## 当前局限性

1. **规则覆盖率有限**：当前规则库仅覆盖常见情绪表达，对隐晦、反讽、双关等复杂语言现象处理不足
2. **缺乏上下文理解**：规则引擎只看当前消息，不考虑对话历史和语境
3. **文化差异**：情绪表达方式因文化、年龄、个人习惯而异，当前规则主要针对中文网络用语
4. **无机器学习**：纯规则方法无法从数据中自动学习和优化
5. **评估数据集小**：当前评估仅基于 40 条样本，不足以全面评估真实场景性能

## 后续计划

- [ ] 扩大评估数据集，建立标准 benchmark
- [ ] 引入机器学习方法，提升识别准确率
- [ ] 支持多语言情绪检测
- [ ] 添加情绪强度评估
- [ ] 优化规则冲突解决算法
- [ ] 添加用户个性化规则配置

## 技术说明

### 项目定位

本项目是一个**基于规则的情绪状态追踪工具**，适用于插件化智能体场景。它具有以下特点：

- **可解释**：每条检测结果都包含完整的推理链路
- **轻量级**：零依赖、零 token 消耗、毫秒级响应
- **可配置**：规则库可扩展，支持自定义情绪状态
- **适合集成**：标准化的插件接口，易于集成到现有系统

### 适用场景

- 智能客服系统中的用户情绪监测
- AI 助手的情感交互优化
- 对话系统的情绪状态追踪
- 用户体验研究中的情绪分析

### 不适用场景

- 需要高精度情绪识别的医疗/心理诊断
- 需要理解复杂语境的文学分析
- 需要跨文化支持的国际化应用
- 需要实时学习的大规模生产系统

## 📝 更新日志

### v0.2.0 (2026-06-05)
**规则引擎加固**：
- ✅ 修复正则表达式问题（compile-time validation，启动时检查空分支和空匹配）
- ✅ 修复 happy 规则空分支（`|||` → 清理为合法 alternation）
- ✅ 增加反例测试（38+ 条，覆盖确认词、引用情绪词、技术命令、流程命令）
- ✅ 信号断言从子集检查改为精确匹配

**状态机优化**：
- ✅ 调整衰减机制：3轮高→中唤醒衰减，5轮→neutral
- ✅ 扩大快照保留范围：20条信号，50条状态历史
- ✅ 添加 assistant 消息分析
- ✅ 优化中置信度累积逻辑（5轮窗口，3+同极性阈值）

**可解释性**：
- ✅ 新增 detect_emotion_detailed()，返回 valence/arousal/explanation
- ✅ 统一版本号（plugin.yaml = README = 0.2.0）

**评估与演示**：
- ✅ 创建 demo 脚本（examples/demo.py）
- ✅ 创建评估脚本（examples/evaluate.py）和数据集（data/sample_eval.jsonl）
- ✅ 全面更新 README（项目定位、局限性说明、小样本 smoke evaluation 声明）

### v0.1.1 (2026-06-05)
- ✅ 修复 brevity 规则误判
- ✅ 添加信号冲突解决机制
- ✅ 清理敏感信息

### v0.1.0 (2026-06-05)
- 初始版本
- 实现情绪状态机、规则引擎、Hooks 集成

## 📄 许可证

MIT License

## 🙏 致谢

- 王怀志、郭政，《参谋助手论——为首长服务的艺术》，西北大学出版社，1994
- Hermes Agent 插件架构
- agentmemory 持久化方案

---

**作者**：songshiyao  
**仓库**：https://github.com/panglihaoshuai/staff-officer  
**问题反馈**：https://github.com/panglihaoshuai/staff-officer/issues
