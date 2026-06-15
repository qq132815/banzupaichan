"""批量测试MES同步脚本 — 重复执行N次，评估成功率和稳定性"""
import os, sys, subprocess, time, json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPEAT = 3  # 每个脚本跑几次
TIMEOUT = 300

SCRIPTS = {
    "work_orders": os.path.join(BASE_DIR, "scripts", "sync_work_orders.py"),
    "reports": os.path.join(BASE_DIR, "scripts", "sync_reports.py"),
}

def run_one(name, path):
    print(f"\n{'='*60}")
    print(f"[{name}] 第 ? 次 — 请等待 (超时={TIMEOUT}s)...")
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, "-u", path],
            capture_output=True, text=True, timeout=TIMEOUT,
            cwd=BASE_DIR,
        )
        elapsed = time.time() - t0
        # 从输出提取关键行
        important = [l for l in result.stdout.split("\n") if any(
            kw in l for kw in ("插入", "更新", "总计", "完成", "ERROR", "错误", "跳过", "insert", "update", "skip")
        )]
        return {
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "elapsed_s": round(elapsed, 1),
            "key_lines": important[-5:],  # 最后5行关键信息
            "stderr_tail": result.stderr.strip()[-300:] if result.stderr.strip() else "",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "elapsed_s": TIMEOUT, "key_lines": [], "stderr_tail": "超时 (>300s)"}
    except Exception as e:
        return {"ok": False, "exit_code": None, "elapsed_s": time.time() - t0, "key_lines": [], "stderr_tail": str(e)}

def main():
    print("=" * 60)
    print("MES 同步稳定性测试 — 每个脚本跑 {} 次".format(REPEAT))
    print("=" * 60)

    all_results = {}

    for name, path in SCRIPTS.items():
        runs = []
        for i in range(REPEAT):
            print(f"\n>>> [{name}] 第 {i+1}/{REPEAT} 次...")
            r = run_one(name, path)
            runs.append(r)
            status = "OK" if r["ok"] else "FAIL"
            print(f"<<< [{name}] 第 {i+1}/{REPEAT} 次: {status} | 耗时={r['elapsed_s']}s | exit={r['exit_code']}")
            if r["key_lines"]:
                for l in r["key_lines"]:
                    print(f"    {l.strip()}")
            if r["stderr_tail"]:
                print(f"    stderr: {r['stderr_tail'][:200]}")

        ok_count = sum(1 for r in runs if r["ok"])
        all_results[name] = {
            "total": REPEAT,
            "ok": ok_count,
            "fail": REPEAT - ok_count,
            "success_rate": f"{ok_count / REPEAT * 100:.0f}%",
            "avg_time": f"{sum(r['elapsed_s'] for r in runs) / len(runs):.1f}s",
            "runs": runs,
        }

    # 汇总
    print("\n" + "=" * 60)
    print("汇总报告")
    print("=" * 60)
    for name, summary in all_results.items():
        print(f"\n[{name}]")
        print(f"  成功率: {summary['success_rate']} ({summary['ok']}/{summary['total']})")
        print(f"  平均耗时: {summary['avg_time']}")
        for i, r in enumerate(summary["runs"]):
            print(f"  第{i+1}次: {'PASS' if r['ok'] else 'FAIL'} | {r['elapsed_s']}s | exit={r['exit_code']}")

    # 存 JSON
    log_path = os.path.join(BASE_DIR, "downloads", "sync_test_result.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n详细日志: {log_path}")

    # 返回退出码：全部通过为0，否则为1
    total_fail = sum(s["fail"] for s in all_results.values())
    if total_fail == 0:
        print("\n全部通过!")
    else:
        print(f"\n有 {total_fail} 次失败!")
    return 0 if total_fail == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
