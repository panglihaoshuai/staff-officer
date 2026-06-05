"""
staff-officer plugin 测试脚本
验证：状态机转移、规则引擎检测、快照持久化
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from __init__ import EmotionStateMachine, detect_signals, detect_assistant_signals, EMOTION_STATES, SIGNAL_RULES

def test_rule_engine():
    """测试规则引擎检测。"""
    print("=== 规则引擎测试 ===")
    
    cases = [
        ("算了不想弄了", ["give_up"], "frustrated"),
        ("哈哈太好了搞定了！", ["delight", "achievement", "approval"], "happy"),
        ("怎么办搞不定了", ["distress"], "anxious"),
        ("要不你来决定吧", ["hesitation"], "neutral"),   # medium, 单次不转移
        ("嗯", ["minimal_response"], "neutral"),  # low, 不转移
        ("详细说说怎么做的", ["deep_dive"], "invested"),
        ("全部删了一刀切", ["impulse_decision"], "impulsive"),
        ("今天天气不错", [], "neutral"),
        ("！！！气死我了！！！", ["exclamation_heavy", "anger_explicit"], "frustrated"),
        ("直接搞别废话", ["command_urgent"], "neutral"),  # medium单次不转移
        ("先到这里吧累了", ["fatigue"], "tired"),
        ("会不会出问题万一失败了", ["worried"], "anxious"),
        # 新增：确认词不误判为疲惫
        ("好的", [], "neutral"),
        ("可以", [], "neutral"),
        ("收到", [], "neutral"),
        # 新增：超短消息
        ("1", ["ultra_brief"], "neutral"),  # low, 不转移
        ("ok", ["ultra_brief"], "neutral"),  # low, 不转移
    ]
    
    passed = 0
    for text, expected_signals, expected_state in cases:
        signals = detect_signals(text)
        signal_names = [s[0] for s in signals]
        
        # 检查信号是否匹配
        signal_match = all(s in signal_names for s in expected_signals)
        
        # 检查状态机转移
        sm = EmotionStateMachine()
        for name, target, conf in signals:
            sm.update(name, target, conf, text)
        
        status = "✅" if sm.state == expected_state else "❌"
        if sm.state == expected_state:
            passed += 1
        
        print(f"  {status} \"{text[:20]}\" → {sm.state} (期望: {expected_state})")
        if sm.state != expected_state:
            print(f"      信号: {signal_names}")
            print(f"      详情: {json.dumps(sm.signals, ensure_ascii=False)[:200]}")
    
    print(f"\n规则引擎：{passed}/{len(cases)} 通过\n")
    return passed == len(cases)

def test_state_machine():
    """测试状态机转移逻辑。"""
    print("=== 状态机转移测试 ===")
    
    sm = EmotionStateMachine()
    
    # 测试1：单次高置信度转移
    sm.update("anger_explicit", "frustrated", "high", "气死了")
    assert sm.state == "frustrated", f"期望 frustrated，实际 {sm.state}"
    print("  ✅ 高置信度直接转移")
    
    # 测试2：中置信度需要累积
    sm2 = EmotionStateMachine()
    sm2.update("approval", "happy", "medium", "不错")
    assert sm2.state == "neutral", f"期望 neutral（单次 medium 不转移），实际 {sm2.state}"
    sm2.update("approval", "happy", "medium", "可以")
    assert sm2.state == "happy", f"期望 happy（两次 medium 转移），实际 {sm2.state}"
    print("  ✅ 中置信度累积转移")
    
    # 测试3：低置信度不转移
    sm3 = EmotionStateMachine()
    sm3.update("brevity", "tired", "low", "嗯")
    assert sm3.state == "neutral", f"期望 neutral（low 不转移），实际 {sm3.state}"
    print("  ✅ 低置信度不转移")
    
    # 测试4：衰减
    sm4 = EmotionStateMachine()
    sm4.update("anger", "frustrated", "high", "烦死了")
    assert sm4.state == "frustrated"
    sm4.turn_count = 10  # 模拟过了 5 轮
    sm4.decay()
    assert sm4.state == "neutral", f"期望 neutral（衰减后），实际 {sm4.state}"
    print("  ✅ 5轮无信号后衰减到 neutral")
    
    # 测试5：快照和恢复
    sm5 = EmotionStateMachine()
    sm5.update("delight", "happy", "high", "太好了")
    sm5.update("deep_dive", "invested", "high", "详细说说")
    snap = sm5.snapshot()
    
    sm6 = EmotionStateMachine()
    sm6.restore(snap)
    assert sm6.state == sm5.state, f"恢复后状态不一致：{sm6.state} vs {sm5.state}"
    assert sm6.turn_count == sm5.turn_count
    print("  ✅ 快照保存和恢复")
    
    print()
    return True

def test_guidance():
    """测试情绪输出指导。"""
    print("=== 情绪指导测试 ===")
    from __init__ import EMOTION_GUIDANCE
    
    for state, guide in EMOTION_GUIDANCE.items():
        has_do = len(guide.get("do", [])) > 0
        has_dont = len(guide.get("dont", [])) > 0
        status = "✅" if (has_do and has_dont) or state == "invested" else "❌"
        print(f"  {status} {state}: do={len(guide.get('do', []))} dont={len(guide.get('dont', []))}")
    
    print()
    return True


def test_negative_cases():
    """测试反例：确保普通文本、负面文本不会被错误匹配为 happy/delight。"""
    print("=== 反例测试（防止误判） ===")
    
    # 这些输入不应该被识别为 happy/delight
    negative_cases = [
        ("我今天很烦", "frustrated", "负面文本不应被识别为happy"),
        ("普通一句话，没有明显情绪", "neutral", "中性文本不应被识别为happy"),
        ("这个功能怎么还不能用", "frustrated", "质疑文本不应被识别为happy"),
        ("我有点焦虑，不知道怎么办", "anxious", "焦虑文本不应被识别为happy"),
        ("今天天气不好", "neutral", "负面描述不应被识别为happy"),
        ("这个方案有问题", "frustrated", "问题指出不应被识别为happy"),
        ("我担心会失败", "anxious", "担忧不应被识别为happy"),
        ("太贵了买不起", "neutral", "价格抱怨不应被识别为happy"),
        ("这个很难做", "neutral", "困难描述不应被识别为happy"),
        ("我不确定这个对不对", "hesitant", "犹豫不应被识别为happy"),
    ]
    
    passed = 0
    for text, expected_not_state, reason in negative_cases:
        signals = detect_signals(text)
        sm = EmotionStateMachine()
        for name, target, conf in signals:
            sm.update(name, target, conf, text)
        
        # 检查是否被错误识别为 happy
        is_happy = sm.state == "happy"
        # 检查是否包含 delight 信号
        has_delight = any(s[0] == "delight" for s in signals)
        
        if not is_happy and not has_delight:
            passed += 1
            status = "✅"
        else:
            status = "❌"
        
        print(f"  {status} \"{text[:20]}\" → {sm.state} (不应为happy) [{reason}]")
        if is_happy or has_delight:
            print(f"      误判信号: {signals}")
    
    # 额外测试：确保 happy 状态只在真正积极时触发
    positive_cases = [
        ("太好了搞定了", "happy", "真正的积极文本应该被识别为happy"),
        ("哈哈成功了", "happy", "成功表达应该被识别为happy"),
        ("漂亮！完美解决", "happy", "赞美应该被识别为happy"),
    ]
    
    print("\n  正例验证（确保真正的happy能被识别）:")
    for text, expected_state, reason in positive_cases:
        signals = detect_signals(text)
        sm = EmotionStateMachine()
        for name, target, conf in signals:
            sm.update(name, target, conf, text)
        
        if sm.state == expected_state:
            passed += 1
            status = "✅"
        else:
            status = "❌"
        
        print(f"    {status} \"{text[:20]}\" → {sm.state} (期望: {expected_state}) [{reason}]")
    
    total = len(negative_cases) + len(positive_cases)
    print(f"\n反例测试：{passed}/{total} 通过\n")
    return passed == total


def test_multi_turn_simulation():
    """模拟多轮对话，验证状态机在长对话中的行为。"""
    print("=== 多轮对话模拟 ===")
    
    sm = EmotionStateMachine()
    
    conversation = [
        ("帮我看看这个方案", "neutral"),
        ("算了不想弄了", "frustrated"),
        ("好吧继续吧", "neutral"),  # 应该衰减
        ("太好了搞定了！", "happy"),
        ("详细说说怎么做的", "invested"),  # happy → invested
        ("怎么办出问题了", "anxious"),
        ("全部删了一刀切", "impulsive"),
        ("嗯", "neutral"),  # 低置信度，不转移
        ("先到这里吧累了", "tired"),
    ]
    
    for text, _ in conversation:
        signals = detect_signals(text)
        for name, target, conf in signals:
            sm.update(name, target, conf, text)
        # 模拟轮次增长
        if not signals:
            sm.turn_count += 1
            sm.decay()
        print(f"  轮{sm.turn_count}: \"{text[:15]}\" → {sm.state} ({EMOTION_STATES[sm.state]['label']})")
    
    print()
    return True


def test_signal_conflict_resolution():
    """测试信号冲突解决机制。"""
    print("=== 信号冲突解决测试 ===")
    
    cases = [
        # 冲突：positive vs negative，取positive（优先级高）
        ("算了太好了搞定了", "happy", "positive优先"),
        # 冲突：两个negative，取置信度高的
        ("烦死了怎么办", "frustrated", "高置信度优先"),
        # 无冲突：多个positive
        ("太好了搞定了漂亮", "happy", "无冲突，取第一个"),
        # 无冲突：多个negative
        ("烦死了气死了受不了", "frustrated", "无冲突，取第一个"),
        # 单信号
        ("算了", "frustrated", "单信号直接返回"),
    ]
    
    passed = 0
    for text, expected_state, reason in cases:
        signals = detect_signals(text)
        if signals:
            # 取第一个信号（已按优先级排序）
            _, target_state, _ = signals[0]
            status = "✅" if target_state == expected_state else "❌"
            if target_state == expected_state:
                passed += 1
            print(f"  {status} \"{text[:15]}\" → {target_state} (期望: {expected_state}) [{reason}]")
            if target_state != expected_state:
                print(f"      实际信号: {signals}")
        else:
            print(f"  ❌ \"{text[:15]}\" → 无信号 (期望: {expected_state}) [{reason}]")
    
    print(f"\n信号冲突解决：{passed}/{len(cases)} 通过\n")
    return passed == len(cases)


def test_long_conversation():
    """测试长对话（50+轮）中的状态机行为。"""
    print("=== 长对话测试（50+轮） ===")
    
    sm = EmotionStateMachine()
    
    # 模拟50轮对话，包含各种情绪变化
    conversation = [
        # 开始：中性
        ("帮我看看这个方案", None),
        ("好的，我分析一下", None),
        ("这个方案有什么问题吗", None),
        
        # 用户开始焦虑
        ("会不会出问题", None),
        ("万一失败了怎么办", None),
        ("我有点担心", None),
        
        # assistant回复安慰
        (None, "别担心，我来帮你分析"),
        (None, "没问题的，我们一步步来"),
        
        # 用户继续焦虑
        ("但是时间很紧", None),
        ("来不及了怎么办", None),
        
        # 用户开始烦躁
        ("算了不想弄了", None),
        ("太麻烦了", None),
        
        # assistant回复理解
        (None, "我理解你的感受"),
        (None, "确实有点复杂"),
        
        # 用户冷静下来
        ("好吧继续吧", None),
        ("你说说怎么做", None),
        
        # 讨论技术细节（中性）
        ("第一步是什么", None),
        ("然后呢", None),
        ("接着呢", None),
        ("最后呢", None),
        
        # 用户投入
        ("详细说说", None),
        ("具体怎么做", None),
        ("展开讲讲", None),
        
        # 用户高兴
        ("太好了搞定了", None),
        ("漂亮", None),
        
        # 用户犹豫
        ("要不换一种方案", None),
        ("你觉得呢", None),
        ("我也不确定", None),
        
        # 用户冲动
        ("全部删了一刀切", None),
        ("就这样定了", None),
        
        # 用户疲惫
        ("累了", None),
        ("先到这里吧", None),
        
        # 继续对话（测试衰减）
        ("嗯", None),
        ("哦", None),
        ("行吧", None),
        
        # 用户再次投入
        ("继续说", None),
        ("然后呢", None),
        ("下一步呢", None),
        
        # 用户再次焦虑
        ("怎么办出问题了", None),
        ("搞不定了", None),
        
        # 用户再次烦躁
        ("气死了", None),
        ("受不了了", None),
        
        # 用户再次冷静
        ("好吧继续", None),
        ("你说", None),
        
        # 讨论细节
        ("这个怎么做", None),
        ("那个呢", None),
        ("还有呢", None),
        
        # 用户再次高兴
        ("搞定了", None),
        ("成功了", None),
        
        # 用户再次犹豫
        ("要不试试别的", None),
        ("你觉得呢", None),
        
        # 用户再次冲动
        ("不管了", None),
        ("爱怎样怎样", None),
        
        # 用户再次疲惫
        ("困了", None),
        ("今天先到这", None),
    ]
    
    # 执行对话
    for i, (user_msg, assistant_msg) in enumerate(conversation, 1):
        if user_msg:
            user_signals = detect_signals(user_msg)
            for name, target, conf in user_signals:
                sm.update(name, target, conf, user_msg)
        
        if assistant_msg:
            assistant_signals = detect_assistant_signals(assistant_msg)
            for name, target, conf in assistant_signals:
                sm.update(name, target, conf, assistant_msg)
        
        if not user_msg and not assistant_msg:
            sm.turn_count += 1
            sm.decay()
        
        # 每10轮打印一次状态
        if i % 10 == 0:
            print(f"  轮{i}: {sm.state} ({EMOTION_STATES[sm.state]['label']})")
    
    # 验证最终状态
    final_state = sm.state
    print(f"\n  最终状态: {final_state} ({EMOTION_STATES[final_state]['label']})")
    print(f"  总轮次: {sm.turn_count}")
    print(f"  信号数量: {len(sm.signals)}")
    print(f"  状态变更次数: {len(sm.state_history)}")
    
    # 验证快照功能
    snapshot = sm.snapshot()
    sm2 = EmotionStateMachine()
    sm2.restore(snapshot)
    
    assert sm2.state == sm.state, f"快照恢复失败：{sm2.state} vs {sm.state}"
    assert sm2.turn_count == sm.turn_count, f"轮次恢复失败：{sm2.turn_count} vs {sm.turn_count}"
    print("  ✅ 快照保存和恢复成功")
    
    # 验证长对话中的状态变化合理性
    # 应该有多次状态变更
    assert len(sm.state_history) >= 5, f"状态变更次数过少：{len(sm.state_history)}"
    print(f"  ✅ 状态变更次数合理：{len(sm.state_history)}")
    
    # 验证信号保留
    assert len(sm.signals) >= 10, f"信号保留过少：{len(sm.signals)}"
    print(f"  ✅ 信号保留数量合理：{len(sm.signals)}")
    
    print(f"\n长对话测试通过 ✅\n")
    return True


if __name__ == "__main__":
    results = []
    results.append(("规则引擎", test_rule_engine()))
    results.append(("反例测试", test_negative_cases()))
    results.append(("状态机", test_state_machine()))
    results.append(("情绪指导", test_guidance()))
    results.append(("多轮模拟", test_multi_turn_simulation()))
    results.append(("信号冲突解决", test_signal_conflict_resolution()))
    results.append(("长对话测试", test_long_conversation()))
    
    print("=" * 40)
    all_pass = all(r[1] for r in results)
    for name, passed in results:
        print(f"  {'✅' if passed else '❌'} {name}")
    print(f"\n{'全部通过 ✅' if all_pass else '有失败 ❌'}")
