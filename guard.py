#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
guard.py — 提交前校验，防止坏数据把好数据覆盖掉

背景：多个 Actions 任务并发时，后跑的任务可能检出旧代码、生成旧数据，
把前一个任务刚提交的新数据打回去。这个脚本在提交前拿「仓库里现有的清单」
和「刚生成的清单」对比，发现异常就中止。

现在源分成两个文件（apps.json 主源 + apps-extra.json 备用源），
所以按两边的应用总数来比。

检查项:
    1. 应用总数骤减（少于现有的 95%）
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
FILES = ("apps.json", "apps-extra.json")


def load_git(name):
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{name}"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        ).stdout
        return json.loads(out) if out.strip() else {}
    except Exception:
        return {}


def load_work(name):
    p = os.path.join(ROOT, name)
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def collect(docs):
    apps = []
    for d in docs:
        apps.extend(d.get("apps") or [])
    return apps


old_apps = collect([load_git(n) for n in FILES])
new_apps = collect([load_work(n) for n in FILES])

if not old_apps:
    print("旧源没有应用记录，跳过校验")
    sys.exit(0)

if len(new_apps) < len(old_apps) * 0.95:
    print(f"✗ 应用总数从 {len(old_apps)} 掉到 {len(new_apps)}，疑似数据异常，中止提交")
    sys.exit(1)

oldest = {}
for a in old_apps:
    vs = a.get("versions") or []
    bid = a.get("bundleIdentifier")
    if bid and vs:
        oldest[bid] = (a.get("name"), str(vs[0].get("date") or ""))

regress = []
for a in new_apps:
    bid = a.get("bundleIdentifier")
    vs = a.get("versions") or []
    if bid in oldest and vs:
        od, nd = oldest[bid][1], str(vs[0].get("date") or "")
        if od and nd and nd < od:
            regress.append((a.get("name"), od[:10], nd[:10]))

if len(regress) > 3:
    print(f"✗ {len(regress)} 个应用的版本日期倒退，中止提交：")
    for n, o, x in regress[:8]:
        print(f"   {n}: {o} → {x}")
    sys.exit(1)

print(f"✓ 校验通过：应用总数 {len(old_apps)} → {len(new_apps)}，版本倒退 {len(regress)} 个")
