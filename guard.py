#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
guard.py — 提交前校验，防止坏数据把好数据覆盖掉

背景：多个 Actions 任务并发时，后跑的任务可能检出旧代码、生成旧数据，
把前一个任务刚提交的新数据打回去。这个脚本在提交前拿「仓库里现有的 apps.json」
和「刚生成的 apps.json」对比，发现异常就中止。

检查项:
    1. 应用数量骤减（少于现有 95%）
    2. 大量应用的版本日期倒退（超过 3 个）
"""
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
new_path = os.path.join(ROOT, "apps.json")

try:
    old_raw = subprocess.run(
        ["git", "show", "HEAD:apps.json"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    ).stdout
    old = json.loads(old_raw) if old_raw.strip() else {"apps": []}
except Exception as e:
    print(f"读不到仓库里的旧 apps.json（{e}），跳过校验")
    sys.exit(0)

new = json.load(open(new_path, encoding="utf-8"))
oa, na = old.get("apps") or [], new.get("apps") or []

if not oa:
    print("旧源没有应用记录，跳过校验")
    sys.exit(0)

if len(na) < len(oa) * 0.95:
    print(f"✗ 应用数从 {len(oa)} 掉到 {len(na)}，疑似数据异常，中止提交")
    sys.exit(1)

oldest = {}
for a in oa:
    vs = a.get("versions") or []
    bid = a.get("bundleIdentifier")
    if bid and vs:
        oldest[bid] = (a.get("name"), str(vs[0].get("date") or ""))

regress = []
for a in na:
    bid = a.get("bundleIdentifier")
    vs = a.get("versions") or []
    if bid in oldest and vs:
        od = oldest[bid][1]
        nd = str(vs[0].get("date") or "")
        if od and nd and nd < od:
            regress.append((a.get("name"), od[:10], nd[:10]))

if len(regress) > 3:
    print(f"✗ {len(regress)} 个应用的版本日期倒退，中止提交：")
    for n, o, x in regress[:8]:
        print(f"   {n}: {o} → {x}")
    sys.exit(1)

print(f"✓ 校验通过：{len(oa)} → {len(na)} 个应用，版本倒退 {len(regress)} 个")
