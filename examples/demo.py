#!/usr/bin/env python3
"""
staff-officer 情绪检测演示脚本

演示如何使用 staff-officer 插件进行情绪状态追踪。
支持多轮对话，实时显示情绪状态变化。
"""

import sys
import os
import json

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from __init__ import (
    EmotionStateMachine,
    detect_signals,
    detect_emotion_detailed,
    EMOTION_STATES,
    EMOTION_GUIDANCE,
)


def print_separator():
    """打印分隔线。"""
    print("-" * 60)


def print_state_transition(previous_state: str, current_state: str):
    """打印状态转移。"""
    if previous_state != current_state:
        prev_label = EMOTION_STATES.get(previous_state, {}).get("label", previous_state)
        curr_label = EMOTION_STATES.get(current_state, {}).get("label", current_state)
        print(f"  状态转移: {prev_label} ({previous_state}) → {curr_label} ({current_state})")
    else:
        label = EMOTION_STATES.get(current_state, {}).get("label", current_state)
        print(f"  状态保持: {label} ({current_state})")


def print_guidance(state: str):
    """打印情绪指导。"""
    guidance = EMOTION_GUIDANCE.get(state, {})
    if guidance.get("do"):
        print(f"  应该做: {'、'.join(guidance['do'])}")
    if guidance.get("dont"):
        print(f"  不要说: {'、'.join(guidance['dont'])}")


def run_demo():
    """运行演示。"""
    print("=" * 60)
    print("staff-officer 情绪检测演示")
    print("=" * 60)
    print()
    print("输入中文文本，观察情绪状态变化。")
    print("输入 'quit' 或 'exit' 退出。")
    print("输入 'demo' 运行预设演示。")
    print()

    sm = EmotionStateMachine()

    # 预设演示对话
    demo_conversation = [
        "帮我看看这个方案",
        "会不会出问题",
        "万一失败了怎么办",
        "算了不想弄了",
        "太麻烦了",
        "好吧继续吧",
        "详细说说怎么做的",
        "太好了搞定了！",
        "漂亮！",
        "要不换一种方案",
        "我也不确定",
        "全部删了一刀切",
        "累了",
        "先到这里吧",
    ]

    while True:
        try:
            user_input = input("User: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n再见！")
            break

        if not user_input:
            continue

        if user_input.lower() in ["quit", "exit"]:
            print("\n再见！")
            break

        if user_input.lower() == "demo":
            print("\n运行预设演示对话：\n")
            for text in demo_conversation:
                print(f"User: {text}")
                process_input(sm, text)
                print()
            continue

        process_input(sm, user_input)
        print()


def process_input(sm: EmotionStateMachine, text: str):
    """处理单条输入。"""
    # 保存前一状态
    previous_state = sm.state

    # 检测信号
    signals = detect_signals(text)

    # 更新状态机
    for signal_name, target_state, confidence in signals:
        sm.update(signal_name, target_state, confidence, text)

    # 如果没有信号，执行衰减
    if not signals:
        sm.decay()

    # 获取详细结果
    result = detect_emotion_detailed(text, previous_state)

    # 打印检测到的信号
    if result["signals"]:
        print(f"  检测到的信号: {', '.join(result['matched_rules'])}")
    else:
        print("  检测到的信号: 无")

    # 打印状态转移
    print_state_transition(previous_state, sm.state)

    # 打印置信度
    print(f"  置信度: {result['confidence']}")

    # 打印效价和唤醒度
    print(f"  效价(valence): {result['valence']}, 唤醒度(arousal): {result['arousal']}")

    # 打印解释
    print(f"  解释: {result['explanation']}")

    # 打印情绪指导
    if sm.state != "neutral":
        print_guidance(sm.state)

    # 打印 prompt block（如果有）
    if sm.state != "neutral" or sm.turn_count > 0:
        state_info = EMOTION_STATES.get(sm.state, {})
        guidance = EMOTION_GUIDANCE.get(sm.state, {})
        print(f"\n  Prompt block 注入:")
        print(f"    用户当前情绪：{state_info.get('label', '中性')}（{sm.state}）")
        if guidance.get("do"):
            print(f"    应该做：{'、'.join(guidance['do'])}")


if __name__ == "__main__":
    run_demo()
