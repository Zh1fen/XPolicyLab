"""Evaluation scopes and strict parsing of the existing LIBERO client output."""

import math
import re

LIBERO_STANDARD_SUITES = ("libero_spatial", "libero_object", "libero_goal", "libero_10")
LIBERO_SUITE_TASKS = {**dict.fromkeys(LIBERO_STANDARD_SUITES, 10), "libero_90": 90}
LIBERO_SELECTIONS = [
    {"id": "all", "label": "全部四组 · 40 任务"},
    {"id": "libero_10", "label": "LIBERO-10 / Long · 10 任务"},
    {"id": "libero_spatial", "label": "LIBERO-Spatial · 10 任务"},
    {"id": "libero_object", "label": "LIBERO-Object · 10 任务"},
    {"id": "libero_goal", "label": "LIBERO-Goal · 10 任务"},
    {"id": "all_with_90", "label": "全部五组 · 130 任务（含 90）"},
    {"id": "libero_90", "label": "LIBERO-90 · 90 任务（预训练集）"},
]


def libero_suites(selection):
    if selection == "all":
        return list(LIBERO_STANDARD_SUITES)
    if selection == "all_with_90":
        return list(LIBERO_SUITE_TASKS)
    if selection not in LIBERO_SUITE_TASKS:
        raise ValueError("未知 LIBERO 评测范围")
    return [selection]


def parse_libero_log(text, suite, trials):
    """Require every task and trial, and reconcile integer counts with final rates."""
    if "Caught exception:" in text:
        raise ValueError("LIBERO 客户端报告执行异常；本组不计作完整评测")
    expected = LIBERO_SUITE_TASKS[suite] * trials
    totals = re.findall(r"Total episodes:\s*(\d+)", text)
    rates = re.findall(r"Total success rate:\s*([^\s]+)", text)
    task_rates = re.findall(r"Current task success rate:\s*([^\s]+)", text)
    outcomes = re.findall(r"\bSuccess:\s*(True|False)\b", text)
    if len(totals) != 1 or len(rates) != 1 or len(task_rates) != LIBERO_SUITE_TASKS[suite]:
        raise ValueError("LIBERO 缺少完整的逐任务结果或最终汇总")
    if int(totals[0]) != expected or len(outcomes) != expected:
        raise ValueError(f"LIBERO 评测预算不完整：预期 {expected} episodes，日志报告 {totals[0]}，逐次记录 {len(outcomes)}")
    tasks, pending = [], []
    description = None
    for line in text.splitlines():
        name = re.search(r"\bTask:\s*(.+)", line)
        if name:
            description = name[1]
        outcome = re.search(r"\bSuccess:\s*(True|False)\b", line)
        if outcome:
            pending.append(outcome[1])
        value = re.search(r"Current task success rate:\s*([^\s]+)", line)
        if value is None:
            continue
        if len(pending) != trials:
            raise ValueError("LIBERO 某任务的 episode 数与每任务预算不一致")
        successes = pending.count("True")
        rate = float(value[1])
        if not math.isfinite(rate) or not math.isclose(rate, successes / trials, abs_tol=1e-8):
            raise ValueError("LIBERO 逐任务成功率与 episode 结果不一致")
        tasks.append(dict(task_index=len(tasks), description=description, episodes=trials,
                          successes=successes, success_rate=successes / trials))
        pending = []
    if pending:
        raise ValueError("LIBERO 存在未汇总的 episode 结果")
    successes = sum(task["successes"] for task in tasks)
    rate = float(rates[0])
    if not math.isfinite(rate) or not math.isclose(rate, successes / expected, abs_tol=1e-8):
        raise ValueError("LIBERO 最终成功率与逐任务结果不一致")
    return dict(suite=suite, episodes=expected, successes=successes, success_rate=successes / expected, tasks=tasks)


def libero_metrics(suites, trials, results):
    complete = [result["suite"] for result in results] == list(suites)
    episodes = sum(result["episodes"] for result in results)
    successes = sum(result["successes"] for result in results)
    metrics = dict(source="libero_client_log", real_evaluation=True, complete=complete,
                   expected_suites=list(suites), suites=results, episodes=episodes, successes=successes,
                   expected_episodes=sum(LIBERO_SUITE_TASKS[suite] for suite in suites) * trials,
                   trials_per_task=trials, budget="50_trials_per_task" if trials == 50 else "smoke")
    if complete:
        metrics["success_rate"] = sum(result["success_rate"] for result in results) / len(results)
        metrics["weighted_success_rate"] = successes / episodes
        metrics["aggregation"] = "suite_macro_average"
        if set(suites) == set(LIBERO_STANDARD_SUITES):
            metrics["report_scope"] = "libero_four_suites"
        else:
            metrics["report_scope"] = "extended_with_90" if "libero_90" in suites else "single_suite"
    return metrics
