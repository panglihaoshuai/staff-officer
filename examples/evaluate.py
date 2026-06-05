#!/usr/bin/env python3
"""
staff-officer 情绪识别评估脚本

使用小型样例数据集评估情绪识别的准确性。
输出：Accuracy、per-class Precision、Recall、F1-score、Confusion Matrix。
"""

import sys
import os
import json
from collections import defaultdict

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from __init__ import detect_signals, EMOTION_STATES


def load_dataset(filepath: str) -> list[dict]:
    """加载 JSONL 格式的数据集。"""
    data = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def predict(text: str) -> str:
    """预测文本的情绪状态。"""
    signals = detect_signals(text)
    if signals:
        # 取第一个信号的目标状态
        _, target_state, _ = signals[0]
        return target_state
    return "neutral"


def compute_metrics(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    """计算评估指标。"""
    # 初始化混淆矩阵
    confusion = defaultdict(lambda: defaultdict(int))
    for true, pred in zip(y_true, y_pred):
        confusion[true][pred] += 1

    # 计算每个类别的指标
    metrics = {}
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label][other] for other in labels if other != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        metrics[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(confusion[label].values()),
        }

    # 计算总体准确率
    correct = sum(confusion[label][label] for label in labels)
    total = len(y_true)
    accuracy = correct / total if total > 0 else 0

    return {
        "accuracy": accuracy,
        "per_class": metrics,
        "confusion": dict(confusion),
    }


def print_confusion_matrix(confusion: dict, labels: list[str]):
    """打印混淆矩阵。"""
    print("\n混淆矩阵:")
    # 表头
    label_str = "真实\\预测".ljust(15)
    for label in labels:
        label_str += label.ljust(12)
    print(label_str)

    for true_label in labels:
        row = true_label.ljust(15)
        for pred_label in labels:
            count = confusion.get(true_label, {}).get(pred_label, 0)
            row += str(count).ljust(12)
        print(row)


def main():
    """主函数。"""
    # 数据集路径
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    dataset_path = os.path.join(data_dir, "sample_eval.jsonl")

    if not os.path.exists(dataset_path):
        print(f"错误：数据集文件不存在：{dataset_path}")
        sys.exit(1)

    # 加载数据集
    print(f"加载数据集：{dataset_path}")
    dataset = load_dataset(dataset_path)
    print(f"样本数量：{len(dataset)}")

    # 获取所有标签
    labels = sorted(EMOTION_STATES.keys())

    # 预测
    y_true = []
    y_pred = []
    errors = []

    for item in dataset:
        text = item["text"]
        true_label = item["label"]
        pred_label = predict(text)

        y_true.append(true_label)
        y_pred.append(pred_label)

        if true_label != pred_label:
            errors.append({
                "text": text,
                "true": true_label,
                "pred": pred_label,
            })

    # 计算指标
    results = compute_metrics(y_true, y_pred, labels)

    # 打印结果
    print("\n" + "=" * 60)
    print("评估结果")
    print("=" * 60)

    print(f"\n总体准确率 (Accuracy): {results['accuracy']:.2%}")

    print("\n各类别指标:")
    print(f"{'类别':<15} {'Precision':<12} {'Recall':<12} {'F1-score':<12} {'Support':<10}")
    print("-" * 60)

    for label in labels:
        if label in results["per_class"]:
            m = results["per_class"][label]
            print(f"{label:<15} {m['precision']:<12.2%} {m['recall']:<12.2%} {m['f1']:<12.2%} {m['support']:<10}")

    # 打印混淆矩阵
    print_confusion_matrix(results["confusion"], labels)

    # 打印错误样本
    if errors:
        print(f"\n错误样本 ({len(errors)} 个):")
        print("-" * 60)
        for err in errors[:10]:  # 只显示前10个
            print(f"  文本: {err['text']}")
            print(f"  真实: {err['true']}, 预测: {err['pred']}")
            print()

    # 保存结果
    output_path = os.path.join(data_dir, "eval_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到：{output_path}")


if __name__ == "__main__":
    main()
