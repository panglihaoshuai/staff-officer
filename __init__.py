"""
staff-officer — 参谋助手论情绪追踪插件

基于王怀志/郭政《参谋助手论——为首长服务的艺术》（西北大学出版社1994）
实现情绪状态机、规则引擎、跨会话记忆持久化。

Plugin 架构：
- sync_turn(): 每轮用规则引擎检测情绪信号，更新状态机
- system_prompt_block(): 注入当前情绪档案到 system prompt
- prefetch(): 会话启动时从 memory 加载历史情绪模式
- on_pre_compress(): 压缩前保存情绪快照
- on_memory_write(): 监听 memory 写入，同步到状态

不依赖 LLM 做情绪分类——纯规则引擎，零延迟，零 token 消耗。
"""

import json
import os
import re
import time
from typing import Any

# ── Hermes Plugin Interface ──────────────────────────────────────────────
try:
    from agent.memory_provider import MemoryProvider
except ImportError:
    from abc import ABC, abstractmethod
    from typing import Any

    class MemoryProvider(ABC):  # type: ignore[no-redef]
        @property
        @abstractmethod
        def name(self) -> str: ...
        @abstractmethod
        def is_available(self) -> bool: ...
        @abstractmethod
        def initialize(self, session_id: str, **kwargs: Any) -> None: ...
        @abstractmethod
        def get_tool_schemas(self) -> list[dict]: ...
        @abstractmethod
        def handle_tool_call(self, name: str, args: dict) -> str: ...
        def system_prompt_block(self) -> str: return ""
        def prefetch(self, query: str, **kwargs: Any) -> str: return ""
        def sync_turn(self, user: str, assistant: str, **kwargs: Any) -> None: pass
        def on_session_end(self, messages: list, **kwargs: Any) -> None: pass
        def on_pre_compress(self, messages: list, **kwargs: Any) -> None: pass
        def on_memory_write(self, action: str, target: str, content: str, **kwargs: Any) -> None: pass
        def shutdown(self, **kwargs: Any) -> None: pass


# ── 情绪状态定义 ─────────────────────────────────────────────────────────

EMOTION_STATES = {
    "neutral":    {"valence": 0,    "arousal": 0,   "label": "中性",    "polarity": "neutral"},
    "happy":      {"valence": 1,    "arousal": 1,   "label": "高兴",    "polarity": "positive"},
    "frustrated": {"valence": -1,   "arousal": 2,   "label": "烦躁",    "polarity": "negative"},
    "anxious":    {"valence": -1,   "arousal": 1,   "label": "焦虑",    "polarity": "negative"},
    "tired":      {"valence": -0.5, "arousal": -1,  "label": "疲惫",    "polarity": "negative"},
    "hesitant":   {"valence": -0.5, "arousal": 0,   "label": "犹豫",    "polarity": "negative"},
    "invested":   {"valence": 0.5,  "arousal": 1,   "label": "投入",    "polarity": "positive"},
    "impulsive":  {"valence": -1,   "arousal": 3,   "label": "冲动",    "polarity": "negative"},
}

# ── 规则引擎：信号 → 状态转移 ─────────────────────────────────────────────
# (正则模式, 信号名称, 目标状态, 置信度)

SIGNAL_RULES: list[tuple[str, str, str, str]] = [
    # 烦躁/愤怒
    (r"[！!]{2,}",                        "exclamation_heavy",  "frustrated", "high"),
    (r"算了|无所谓|随便|不想[聊弄搞干]",    "give_up",            "frustrated", "high"),
    (r"烦[死透了]|气死|受不了|忍不了",      "anger_explicit",     "frustrated", "high"),
    (r"你[怎搞]这[个么]|你搞[错了]|不对",   "reject_direct",      "frustrated", "medium"),

    # 高兴/得意
    (r"哈哈|笑死|😄|👍|太好了|漂亮|牛[逼批]", "delight",          "happy",      "high"),
    (r"搞定了|完成了|解决了|成功|过了",       "achievement",        "happy",      "high"),
    (r"不错|可以|好的|行[啊吧]",             "approval",           "happy",      "medium"),

    # 焦虑/不确定
    (r"怎么办|不知道[怎咋]|搞不定|失败了",   "distress",           "anxious",    "high"),
    (r"会不会|万一|如果.*怎么办",            "worried",            "anxious",    "medium"),
    (r"急|赶[紧时间]|来不及|快[点要]",       "urgency",            "anxious",    "medium"),

    # 犹豫/纠结
    (r"要不|可能|你觉得呢|我也不确定",       "hesitation",         "hesitant",   "medium"),
    (r"犹豫|纠结|不知道选|两[个难]",         "deliberation",       "hesitant",   "medium"),

    # 疲惫/兴趣下降（排除正常确认词）
    (r"先[到这这样吧]|今天先|累了|困了",     "fatigue",            "tired",      "high"),
    (r"嗯|哦|行吧",                         "minimal_response",   "tired",      "low"),
    (r"^.{1,3}$",                           "ultra_brief",        "tired",      "low"),  # 仅1-3字符，排除"好的""可以"等

    # 投入/认真
    (r"然后呢|继续|接着|下一步",             "engagement",         "invested",   "medium"),
    (r"详细说|展开讲|具体.*怎么做",          "deep_dive",          "invested",   "high"),

    # 冲动决策
    (r"再也不|全部删|一刀切|就这样定了",      "impulse_decision",   "impulsive",  "high"),
    (r"别废话|直接搞|让.*干|马上[搞做弄]",   "command_urgent",     "impulsive",  "medium"),
    (r"不管了|无所谓了|爱[怎咋]样.*怎样",    "resignation",        "impulsive",  "medium"),
]


# ── 情绪状态机 ───────────────────────────────────────────────────────────

class EmotionStateMachine:
    """跨轮次情绪状态机，维护当前状态和历史信号。"""

    def __init__(self) -> None:
        self.state: str = "neutral"
        self.valence: float = 0.0
        self.arousal: float = 0.0
        self.turn_count: int = 0
        self.signals: list[dict] = []       # 最近信号（最多保留 20 条）
        self.state_history: list[dict] = []  # 状态变更历史（最多保留 50 条）
        self.created_at: float = time.time()

    def update(self, signal_name: str, target_state: str, confidence: str, source_text: str) -> None:
        """根据检测到的信号更新状态。"""
        old_state = self.state
        self.turn_count += 1

        # 记录信号
        entry = {
            "turn": self.turn_count,
            "signal": signal_name,
            "from": old_state,
            "to": target_state,
            "confidence": confidence,
            "text": source_text[:100],
            "ts": time.time(),
        }
        self.signals.append(entry)
        if len(self.signals) > 20:
            self.signals = self.signals[-20:]

        # 状态转移（高置信度直接转移，中/低置信度需要累积）
        if confidence == "high":
            self._transition(target_state)
        elif confidence == "medium":
            # 如果最近 3 轮有 2+ 个相同目标信号，转移
            recent_to_same = sum(
                1 for s in self.signals[-3:]
                if s["to"] == target_state
            )
            if recent_to_same >= 2:
                self._transition(target_state)
        # low 置信度：只记录信号，不转移状态

    def _transition(self, new_state: str) -> None:
        """执行状态转移。"""
        if new_state == self.state:
            return  # 已经在目标状态
        old_state = self.state
        self.state = new_state
        info = EMOTION_STATES.get(new_state, EMOTION_STATES["neutral"])
        self.valence = info["valence"]
        self.arousal = info["arousal"]
        self.state_history.append({
            "from": old_state,
            "to": new_state,
            "turn": self.turn_count,
            "ts": time.time(),
        })
        if len(self.state_history) > 50:
            self.state_history = self.state_history[-50:]

    def decay(self) -> None:
        """每轮结束时，如果最近 5 轮没有新信号，状态向 neutral 衰减。"""
        if not self.signals:
            return
        recent = self.signals[-1]
        age = self.turn_count - recent["turn"]
        if age >= 3 and self.state != "neutral":
            self._transition("neutral")

    def snapshot(self) -> dict:
        """导出当前状态快照（用于持久化和压缩前保存）。"""
        return {
            "state": self.state,
            "valence": self.valence,
            "arousal": self.arousal,
            "turn_count": self.turn_count,
            "recent_signals": self.signals[-5:],
            "state_history": self.state_history[-5:],
            "created_at": self.created_at,
            "snapshot_at": time.time(),
        }

    def restore(self, data: dict) -> None:
        """从快照恢复状态。"""
        self.state = data.get("state", "neutral")
        self.valence = data.get("valence", 0)
        self.arousal = data.get("arousal", 0)
        self.turn_count = data.get("turn_count", 0)
        self.signals = data.get("recent_signals", [])
        self.state_history = data.get("state_history", [])
        self.created_at = data.get("created_at", time.time())


# ── 规则引擎 ─────────────────────────────────────────────────────────────

# 信号优先级：positive > neutral > negative（当置信度相同时）
POLARITY_PRIORITY = {"positive": 3, "neutral": 2, "negative": 1}

# 置信度权重
CONFIDENCE_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def detect_signals(text: str) -> list[tuple[str, str, str]]:
    """用规则引擎检测文本中的情绪信号，自动解决冲突。

    返回: [(signal_name, target_state, confidence), ...]
    冲突解决规则：
    1. 高置信度信号优先
    2. 置信度相同时，positive信号优先
    3. 仍然冲突时，取最后一个信号
    """
    if not text or len(text.strip()) == 0:
        return []

    results = []
    text_stripped = text.strip()

    for pattern, signal_name, target_state, confidence in SIGNAL_RULES:
        try:
            if re.search(pattern, text_stripped, re.IGNORECASE):
                results.append((signal_name, target_state, confidence))
        except re.error:
            continue

    if len(results) <= 1:
        return results

    # 冲突解决：按置信度和极性排序，取最优信号
    def signal_priority(sig):
        _, target_state, confidence = sig
        polarity = EMOTION_STATES.get(target_state, {}).get("polarity", "neutral")
        return (CONFIDENCE_WEIGHT.get(confidence, 0), POLARITY_PRIORITY.get(polarity, 0))

    results.sort(key=signal_priority, reverse=True)

    # 检查是否有真正的冲突（不同极性的高置信度信号）
    high_conf = [s for s in results if s[2] == "high"]
    if len(high_conf) >= 2:
        polarities = set(EMOTION_STATES.get(s[1], {}).get("polarity", "neutral") for s in high_conf)
        if "positive" in polarities and "negative" in polarities:
            # 真正的冲突：取极性优先级最高的
            return [results[0]]

    # 无真正冲突，返回所有信号（按优先级排序）
    return results


# ── 情绪价值输出指导 ─────────────────────────────────────────────────────

EMOTION_GUIDANCE = {
    "frustrated": {
        "do": ["先共情1句", "暂停建议", "转移到可执行的事"],
        "say": "这个确实{感受}。我先帮你处理{具体事项}，你缓一下。",
        "dont": ["别着急", "冷静一下", "你这样不对"],
    },
    "anxious": {
        "do": ["拆解问题为2-3步", "给出明确下一步", "降低首步难度"],
        "say": "我帮你理了一下，其实分三步：1...2...3...。先从1开始，我来搞。",
        "dont": ["你想太多了", "这有什么好担心的"],
    },
    "tired": {
        "do": ["缩短回复", "给结论不给过程", "主动问要不要先到这"],
        "say": "核心结论：{X}。要不要先到这，剩下的明天继续？",
        "dont": ["长篇大论", "追问你还在吗"],
    },
    "hesitant": {
        "do": ["列出2-3个选项", "每个选项的代价和收益", "给出你的倾向但不替他选"],
        "say": "你现在其实就三条路：A...B...C...。如果是我，我会选B，因为{X}。但你最了解情况。",
        "dont": ["你随便选", "都行"],
    },
    "happy": {
        "do": ["共庆1句", "趁机回顾来之不易的过程", "提一个建设性意见", "汇报之前积压的小事"],
        "say": "这个确实漂亮。回头看，当时那个决定是对的。另外有个小事正好趁现在说一下...",
        "dont": ["扫兴", "提之前的失误"],
    },
    "impulsive": {
        "do": ["缓办", "补充信息", "反向假设", "给回旋余地"],
        "say": "好，我先记下来。有件事你可能还不知道：{Y}。知道了这个，你还这么定吗？",
        "dont": ["立刻执行", "火上浇油"],
    },
    "invested": {
        "do": ["匹配他的深度", "主动补充细节", "不打断节奏"],
        "say": "",  # 跟着他的节奏走
        "dont": ["催促", "打断", "差不多行了"],
    },
    "neutral": {
        "do": ["常规流程", "先结论后步骤"],
        "say": "",
        "dont": [],
    },
}

# ── 冲动判断清单 ─────────────────────────────────────────────────────────

IMPULSE_CHECKLIST = [
    (r"再也不|永远不|全部删|一刀切",   "绝对化措辞"),
    (r"就这样定了|就这么干|别说了",    "异常快速决策"),
    (r"[！!]{3,}|[？?]{3,}",         "语气激烈"),
]


# ── Plugin 主类 ──────────────────────────────────────────────────────────

class StaffOfficerProvider(MemoryProvider):
    """参谋助手论情绪追踪插件。"""

    @property
    def name(self) -> str:
        return "staff-officer"

    def is_available(self) -> bool:
        return True  # 无外部依赖，始终可用

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = session_id
        self._emotion = EmotionStateMachine()
        self._snapshot_loaded = False
        self._agentmemory_base = os.environ.get("AGENTMEMORY_URL", "http://localhost:3111")

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "emotion_status",
                "description": "查看当前情绪状态和历史信号（参谋助手论插件）",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    def handle_tool_call(self, name: str, args: dict) -> str:
        if name == "emotion_status":
            snap = self._emotion.snapshot()
            state_info = EMOTION_STATES.get(snap["state"], {})
            guidance = EMOTION_GUIDANCE.get(snap["state"], {})
            return json.dumps({
                "state": snap["state"],
                "label": state_info.get("label", "未知"),
                "valence": snap["valence"],
                "arousal": snap["arousal"],
                "turn_count": snap["turn_count"],
                "recent_signals": snap["recent_signals"][-3:],
                "guidance": {
                    "do": guidance.get("do", []),
                    "dont": guidance.get("dont", []),
                },
            }, ensure_ascii=False)
        return json.dumps({"error": f"Unknown tool: {name}"})

    # ── 核心 Hook：每轮情绪分析 ──────────────────────────────────────

    def sync_turn(self, user: str, assistant: str, **kwargs: Any) -> None:
        """每轮对话后调用。用规则引擎检测情绪信号，更新状态机。"""
        # 检测用户消息中的情绪信号
        user_signals = detect_signals(user)
        for signal_name, target_state, confidence in user_signals:
            self._emotion.update(signal_name, target_state, confidence, user)

        # 检测 assistant 回复中的反馈信号（用户可能在 assistant 回复中隐含情绪）
        # 但主要关注用户消息，assistant 消息只做辅助
        if not user_signals:
            # 没有检测到信号，执行衰减
            self._emotion.decay()

        # 每 5 轮保存一次情绪模式到 memory（通过 on_memory_write 机制）
        if self._emotion.turn_count % 5 == 0 and self._emotion.state != "neutral":
            self._save_emotion_pattern()

    # ── 系统提示注入 ─────────────────────────────────────────────────

    def system_prompt_block(self) -> str:
        """注入当前情绪档案到 system prompt。"""
        state = self._emotion.state
        info = EMOTION_STATES.get(state, EMOTION_STATES["neutral"])
        guidance = EMOTION_GUIDANCE.get(state, {})

        if state == "neutral" and self._emotion.turn_count == 0:
            return ""  # 首轮中性状态不注入

        lines = [
            "## 参谋助手·情绪雷达",
            f"用户当前情绪：{info['label']}（{state}）",
            f"效价：{info['valence']}  唤醒度：{info['arousal']}",
            f"已对话轮次：{self._emotion.turn_count}",
        ]

        # 最近信号
        if self._emotion.signals:
            recent = self._emotion.signals[-3:]
            lines.append("最近信号：")
            for s in recent:
                lines.append(f"  - [{s['confidence']}] {s['signal']}: \"{s['text']}\"")

        # 输出指导
        if guidance.get("do"):
            lines.append(f"应该做：{'、'.join(guidance['do'])}")
        if guidance.get("dont"):
            lines.append(f"不要说：{'、'.join(guidance['dont'])}")

        # 冲动检测
        if state == "impulsive":
            lines.append("⚠️ 用户可能处于冲动状态，考虑缓办或补充信息。")

        return "\n".join(lines)

    # ── 会话启动：加载历史情绪模式 ──────────────────────────────────

    def prefetch(self, query: str, **kwargs: Any) -> str:
        """会话启动时调用，加载历史情绪模式。"""
        if self._snapshot_loaded:
            return ""

        # 尝试从 agentmemory 加载最近的情绪快照
        try:
            import urllib.request
            url = f"{self._agentmemory_base}/agentmemory/search"
            payload = json.dumps({
                "query": "emotion-snapshot emotion pattern 用户情绪",
                "limit": 3,
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                results = data.get("results", [])
                for r in results:
                    obs = r.get("observation", r)
                    narrative = obs.get("narrative", "")
                    if "[emotion-snapshot]" in narrative:
                        try:
                            snapshot_data = json.loads(narrative.replace("[emotion-snapshot] ", ""))
                            self._emotion.restore(snapshot_data)
                            self._snapshot_loaded = True
                            return f"已加载历史情绪档案：{self._emotion.state}"
                        except (json.JSONDecodeError, KeyError):
                            continue
                    if "[emotion-pattern]" in narrative:
                        self._snapshot_loaded = True
                        return f"历史情绪模式：{narrative[:200]}"
        except Exception:
            pass  # agentmemory 不可用时静默失败

        self._snapshot_loaded = True
        return ""

    # ── 压缩前保存情绪快照 ──────────────────────────────────────────

    def on_pre_compress(self, messages: list, **kwargs: Any) -> None:
        """压缩前保存情绪状态快照到 agentmemory。"""
        if self._emotion.state == "neutral" and self._emotion.turn_count == 0:
            return  # 无状态变化，不保存

        snapshot = self._emotion.snapshot()
        self._save_to_agentmemory(
            f"[emotion-snapshot] {json.dumps(snapshot, ensure_ascii=False)}",
            "pattern",
        )

    # ── 监听 memory 写入 ────────────────────────────────────────────

    def on_memory_write(self, action: str, target: str, content: str, **kwargs: Any) -> None:
        """监听内置 memory 写入，如果内容包含情绪相关信息，同步到状态。"""
        if action != "add":
            return
        # 检查是否包含情绪关键词
        emotion_keywords = ["情绪", "心情", "烦躁", "高兴", "焦虑", "疲惫", "冲动", "犹豫"]
        if any(kw in content for kw in emotion_keywords):
            signals = detect_signals(content)
            for signal_name, target_state, confidence in signals:
                self._emotion.update(signal_name, target_state, confidence, content)

    # ── 会话结束 ────────────────────────────────────────────────────

    def on_session_end(self, messages: list, **kwargs: Any) -> None:
        """会话结束时保存最终情绪状态。"""
        if self._emotion.state != "neutral" or self._emotion.turn_count > 0:
            snapshot = self._emotion.snapshot()
            self._save_to_agentmemory(
                f"[emotion-snapshot] {json.dumps(snapshot, ensure_ascii=False)}",
                "pattern",
            )

    def shutdown(self, **kwargs: Any) -> None:
        pass

    # ── 内部方法 ────────────────────────────────────────────────────

    def _save_emotion_pattern(self) -> None:
        """保存当前情绪模式到 agentmemory。"""
        state = self._emotion.state
        info = EMOTION_STATES.get(state, {})
        recent_signals = self._emotion.signals[-3:]
        signal_summary = ", ".join(s["signal"] for s in recent_signals)

        content = (
            f"[emotion-pattern] 用户情绪状态：{info.get('label', state)}，"
            f"近期信号：{signal_summary}，"
            f"轮次：{self._emotion.turn_count}"
        )
        self._save_to_agentmemory(content, "pattern")

    def _save_to_agentmemory(self, content: str, mem_type: str) -> None:
        """调用 agentmemory API 保存记忆。"""
        try:
            import urllib.request
            url = f"{self._agentmemory_base}/agentmemory/remember"
            payload = json.dumps({
                "content": content,
                "type": mem_type,
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass  # 静默失败，不阻塞主流程


# ── Plugin 注册入口 ──────────────────────────────────────────────────────

def register(ctx: Any) -> None:
    """Hermes 插件注册入口。"""
    ctx.register_memory_provider(StaffOfficerProvider())
