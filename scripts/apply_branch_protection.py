#!/usr/bin/env python3
"""分支保护漂移检测 / 幂等应用（单一来源 docs/ci/branch-protection.json）。

    python scripts/apply_branch_protection.py            # 只读漂移检测
    python scripts/apply_branch_protection.py --apply     # 幂等写入
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(os.path.dirname(HERE), "docs", "ci", "branch-protection.json")


def gh(args):
    r = subprocess.run(["gh", "api"] + args, capture_output=True, text=True)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def body(cfg):
    p, r = cfg["policy"], cfg
    return {
        "required_status_checks": {"strict": p["strict"], "contexts": r["contexts"]},
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": p["dismiss_stale_reviews"],
            "require_code_owner_reviews": p["require_code_owner_reviews"],
            "required_approving_review_count": p["required_approving_review_count"],
            "require_last_push_approval": p["require_last_push_approval"],
        },
        "required_signatures": p["required_signatures"],
        "enforce_admins": p["enforce_admins"],
        "required_linear_history": p["required_linear_history"],
        "allow_force_pushes": p["allow_force_pushes"],
        "allow_deletions": p["allow_deletions"],
        "block_creations": p["block_creations"],
        "required_conversation_resolution": r["required_conversation_resolution"],
        "lock_branch": p["lock_branch"],
        "allow_fork_syncing": p["allow_fork_syncing"],
        "restrictions": p["restrictions"],
    }


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(CFG, encoding="utf-8"))
    slug = f"{cfg['owner']}/{cfg['repo']}"
    want = body(cfg)
    code, out, err = gh([f"repos/{slug}/branches/main/protection"])
    if code != 0:
        print(f"[FAIL] 读取保护失败: {err[:200]}"); sys.exit(1)
    cur = json.loads(out)
    d = []
    pr = cur.get("required_pull_request_reviews") or {}
    if pr.get("required_approving_review_count") != want["required_pull_request_reviews"]["required_approving_review_count"]:
        d.append("review")
    rsc = cur.get("required_status_checks") or {}
    if bool(rsc.get("strict")) != want["required_status_checks"]["strict"]:
        d.append("strict")
    if set(rsc.get("contexts") or []) != set(want["required_status_checks"]["contexts"]):
        d.append("contexts")
    if bool((cur.get("enforce_admins") or {}).get("enabled")) != want["enforce_admins"]:
        d.append("enforce_admins")
    if bool((cur.get("required_conversation_resolution") or {}).get("enabled")) != want["required_conversation_resolution"]:
        d.append("conv_res")
    _, am, _ = gh([f"repos/{slug}", "--jq", ".allow_auto_merge"])
    if (am.strip() == "true") != bool(cfg["policy"]["allow_auto_merge"]):
        d.append("allow_auto_merge")
    if not d:
        print("[OK] 无漂移"); return
    print(f"[DRIFT] {', '.join(d)}")
    if a.apply:
        tmp = os.path.join(HERE, "_body.json")
        json.dump(want, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        c, o, e = gh(["-X", "PUT", f"repos/{slug}/branches/main/protection", "--input", tmp])
        print("apply ->", "OK" if c == 0 else e[:200])
        if cfg["policy"]["allow_auto_merge"]:
            gh(["-X", "PATCH", f"repos/{slug}", "-F", "allow_auto_merge=true"])
        sys.exit(1)
    sys.exit(1)


if __name__ == "__main__":
    main()
