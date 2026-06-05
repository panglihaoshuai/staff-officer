# staff-officer 🎯

**参谋助手论情绪追踪插件** — 基于规则引擎的用户情绪状态机，配合 `ai-staff-officer` skill 使用。

> 基于王怀志/郭政《参谋助手论——为首长服务的艺术》（西北大学出版社1994）实现。

## ✨ 功能特性

### 情绪检测
- **8种情绪状态**：中性、高兴、烦躁、焦虑、疲惫、犹豫、投入、冲动
- **纯规则引擎**：零延迟、零token消耗、可预测
- **信号冲突解决**：自动处理矛盾情绪信号（positive优先于negative）
- **置信度分级**：high/medium/low 三级，高置信度直接转移，低置信度只记录不转移

### 状态机
- **跨轮次追踪**：维护当前状态、效价(valence)、唤醒度(arousal)
- **智能衰减**：3轮无信号后自动衰减到neutral
- **快照持久化**：支持保存/恢复状态，跨会话连续
- **历史记录**：保留最近20条信号、50条状态变更历史

### Hooks集成
- `sync_turn()` — 每轮对话后检测情绪信号
- `system_prompt_block()` — 注入情绪档案到system prompt
- `prefetch()` — 会话启动时加载历史情绪模式
- `on_pre_compress()` — 压缩前保存情绪快照
- `on_memory_write()` — 监听memory写入，同步情绪状态
- `on_session_end()` — 会话结束时保存最终状态

### 输出指导
每种情绪都有明确的行为指导：

| 情绪 | 应该做 | 不要说 |
|------|--------|--------|
| 烦躁 | 先共情1句，暂停建议，转移到可执行的事 | "别着急""冷静一下" |
| 焦虑 | 拆解问题为2-3步，给出明确下一步 | "你想太多了" |
| 疲惫 | 缩短回复，给结论不给过程 | 长篇大论 |
| 犹豫 | 列出2-3个选项+代价收益，给你的倾向 | "你随便选" |
| 高兴 | 共庆+趁机提建设性意见 | 扫兴 |
| 冲动 | 缓办/补充信息/反向假设 | 火上浇油 |
| 投入 | 匹配他的深度，不打断节奏 | "差不多行了" |

## 🚀 安装

### 前置条件
- Python 3.9+
- Hermes Agent（已配置）

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/panglihaoshuai/staff-officer.git
cd staff-officer
```

2. **复制到Hermes插件目录**
```bash
cp -r . ~/.hermes/plugins/staff-officer/
```

3. **启用插件**
```bash
hermes plugins enable staff-officer
```

4. **重启Hermes会话**
插件会在下次会话时自动加载。

## 📖 使用方法

### 自动运行
插件启用后，会自动：
1. 每轮对话检测用户情绪信号
2. 更新情绪状态机
3. 在system prompt中注入情绪档案
4. 根据情绪状态调整回应风格

### 手动查看情绪状态
在对话中调用 `emotion_status` 工具：
```json
{
  "name": "emotion_status",
  "args": {}
}
```

返回示例：
```json
{
  "state": "frustrated",
  "label": "烦躁",
  "valence": -1,
  "arousal": 2,
  "turn_count": 5,
  "recent_signals": [...],
  "guidance": {
    "do": ["先共情1句", "暂停建议", "转移到可执行的事"],
    "dont": ["别着急", "冷静一下", "你这样不对"]
  }
}
```

## ⚙️ 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENTMEMORY_URL` | `http://localhost:3111` | agentmemory服务地址 |

### 情绪状态定义

```python
EMOTION_STATES = {
    "neutral":    {"valence": 0,    "arousal": 0,   "label": "中性"},
    "happy":      {"valence": 1,    "arousal": 1,   "label": "高兴"},
    "frustrated": {"valence": -1,   "arousal": 2,   "label": "烦躁"},
    "anxious":    {"valence": -1,   "arousal": 1,   "label": "焦虑"},
    "tired":      {"valence": -0.5, "arousal": -1,  "label": "疲惫"},
    "hesitant":   {"valence": -0.5, "arousal": 0,   "label": "犹豫"},
    "invested":   {"valence": 0.5,  "arousal": 1,   "label": "投入"},
    "impulsive":  {"valence": -1,   "arousal": 3,   "label": "冲动"},
}
```

### 信号规则

规则引擎使用正则表达式匹配用户消息，支持：
- **高置信度信号**：直接触发状态转移（如"算了""气死了"）
- **中置信度信号**：需要连续2轮相同状态才转移（如"不错""可以"）
- **低置信度信号**：只记录不转移（如"嗯""哦"）

### 冲突解决机制

当检测到多个冲突信号时：
1. **高置信度优先**：high > medium > low
2. **positive优先**：当置信度相同时，positive情绪优先于negative
3. **取第一个**：仍然冲突时，取排序后的第一个信号

## 🧪 测试

运行完整测试套件：
```bash
cd ~/.hermes/plugins/staff-officer
python3 test_plugin.py
```

测试覆盖：
- ✅ 规则引擎：17个测试用例（含确认词误判防护）
- ✅ 状态机：高/中/低置信度转移、衰减、快照恢复
- ✅ 情绪指导：8种状态的do/dont指导
- ✅ 多轮模拟：9轮对话状态转移
- ✅ 信号冲突解决：5个冲突场景

## 🏗️ 架构设计

```
staff-officer/
├── __init__.py          # 主插件代码
│   ├── EmotionStateMachine  # 情绪状态机
│   ├── detect_signals()     # 规则引擎
│   ├── EMOTION_GUIDANCE     # 输出指导
│   └── StaffOfficerProvider # 插件主类
├── test_plugin.py       # 测试脚本
├── plugin.yaml          # 插件元数据
└── README.md            # 本文档
```

### 核心流程

```
用户消息 → 规则引擎检测信号 → 冲突解决 → 状态机更新 → 情绪档案注入system prompt
     ↓
会话结束 → 保存快照到agentmemory → 下次会话恢复
```

## 📊 性能指标

- **检测延迟**：<1ms（纯正则匹配）
- **内存占用**：<1MB（状态机+信号历史）
- **token消耗**：0（不依赖LLM）
- **准确率**：17/17测试用例通过（100%）

## 🤝 配合使用

### ai-staff-officer skill
本插件配合 `ai-staff-officer` skill 使用效果最佳：
- **skill** 提供行为准则（领会意图、辅助决策、纠偏护航）
- **plugin** 提供情绪数据（状态、信号、指导）

安装skill：
```bash
# skill已内置，无需额外安装
```

### agentmemory
插件可选集成agentmemory，实现：
- 跨会话情绪模式持久化
- 历史情绪快照恢复
- 情绪趋势分析

## 🐛 已知问题

1. **中置信度累积逻辑**：连续2轮相同状态才转移，可能导致频繁切换情绪时反应迟钝
2. **衰减过于激进**：3轮无信号即衰减，长对话中可能过早重置
3. **快照截断**：只保留最近5条信号/历史，长对话中早期信号会丢失

## 🔧 开发计划

- [ ] P1：调整衰减机制（3轮→5轮，或渐进衰减）
- [ ] P1：扩大快照保留范围（5条→20条）
- [ ] P2：添加assistant消息分析（辅助信号）
- [ ] P2：优化中置信度累积逻辑
- [ ] P2：添加长对话测试（50+轮）

## 📝 更新日志

### v0.1.1 (2026-06-05)
- ✅ 修复brevity规则误判（删除`^.{1,6}$`，改为`^.{1,3}$`）
- ✅ 添加信号冲突解决机制（positive优先、高置信度优先）
- ✅ 添加极性(polarity)到情绪状态定义
- ✅ 更新测试用例（17个规则引擎测试、5个冲突解决测试）
- ✅ 清理敏感信息（硬编码路径改为动态获取）

### v0.1.0 (2026-06-05)
- 初始版本
- 实现情绪状态机、规则引擎、Hooks集成
- 支持8种情绪状态、3级置信度、冲突解决

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