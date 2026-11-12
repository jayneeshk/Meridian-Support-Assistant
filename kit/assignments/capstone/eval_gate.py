"""CI quality gate. Usage:
    python eval_gate.py reports/eval_after.json --min faithfulness=0.7 --min context_recall=0.8 --max latency_p95_ms=2000 --max sim_cost_usd=0.05
Reads a run_eval() result JSON. Exit code 0 when every threshold holds, 1 when any is violated, 2 on usage/file errors.
Metric names: any key in results["metrics"], plus latency_p50_ms, latency_p95_ms, sim_cost_usd. Print a readable PASS/FAIL line per threshold.
"""
import json
import sys
from pathlib import Path


def _parse_thresholds(argv):
    if not argv:
        raise ValueError("usage: eval_gate.py REPORT.json [--min metric=value ...] [--max metric=value ...]")

    report_path = Path(argv[0])
    thresholds = {"min": {}, "max": {}}
    i = 1
    while i < len(argv):
        token = argv[i]
        if token in {"--min", "--max"}:
            if i + 1 >= len(argv):
                raise ValueError(f"missing value for {token}")
            raw = argv[i + 1]
            i += 2
        else:
            raw = token
            if "=" not in raw or not raw.startswith(("--min=", "--max=")):
                raise ValueError(f"invalid threshold {token!r}")
            if raw.startswith("--min="):
                token = "--min"
                raw = raw[len("--min=") :]
            elif raw.startswith("--max="):
                token = "--max"
                raw = raw[len("--max=") :]
            i += 1
        if "=" not in raw:
            raise ValueError(f"invalid threshold value {raw!r}")
        key, value = raw.split("=", 1)
        thresholds[token[2:]][key.strip()] = float(value)
    return report_path, thresholds


def _resolve_metric(report, metric_name):
    if metric_name in report.get("metrics", {}):
        return report["metrics"][metric_name]
    if metric_name in {"latency_p50_ms", "latency_p95_ms"}:
        return report.get("latency_ms", {}).get(metric_name.replace("latency_", "").replace("_ms", ""), None)
    if metric_name in {"sim_cost_usd"}:
        return report.get("sim_cost_usd")
    return report.get(metric_name)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        report_path, thresholds = _parse_thresholds(argv)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not report_path.exists():
        print(f"ERROR: file not found: {report_path}", file=sys.stderr)
        return 2

    try:
        report = json.loads(report_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        print(f"ERROR: invalid JSON in {report_path}: {exc}", file=sys.stderr)
        return 2

    failures = []
    all_thresholds = []
    for direction, mapping in thresholds.items():
        for metric_name, limit in mapping.items():
            value = _resolve_metric(report, metric_name)
            if value is None:
                failures.append(f"{direction} {metric_name}={limit}: metric not present in report")
                continue
            if direction == "min" and value < limit:
                failures.append(f"FAIL: {metric_name}={value} < {limit}")
            elif direction == "max" and value > limit:
                failures.append(f"FAIL: {metric_name}={value} > {limit}")
            else:
                status = "PASS" if direction == "min" else "PASS"
                all_thresholds.append(f"{status}: {metric_name}={value} {direction} {limit}")
    if not failures and not any(thresholds.values()):
        print("PASS: no thresholds specified")
        return 0
    if failures:
        for item in all_thresholds:
            print(item)
        for item in failures:
            print(item)
        return 1

    for item in all_thresholds:
        print(item)
    print("PASS: all thresholds satisfied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
