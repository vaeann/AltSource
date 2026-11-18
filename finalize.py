#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize.py — 收尾处理：给副标题加更新日期、按更新时间排序

放在 build.py 和 sync_repo.py 之后跑，因为它依赖最终确定下来的版本日期。

为什么加在副标题：LiveContainer 的源列表每一项只显示三行 —— 应用名、
「版本 (构建号) • bundle id」、副标题。日期没有任何独立位置可放，
塞进副标题是唯一能让用户在列表里直接看到的地方。

为什么排序有效：客户端就是按 apps 数组的先后顺序渲染的，不做二次排序。
所以把数组按最新版本日期倒序，列表就自动是「最近更新的在前」。
"""
import datetime
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
# 兼容两种旧前缀：带时间的和不带时间的，都能剥掉
PREFIX = re.compile(r"^\d{2,4}-\d{2}(?:-\d{2})?(?: \d{2}:\d{2})? · ")
CN = datetime.timezone(datetime.timedelta(hours=8))


def date_prefix(iso):
    """统一转成北京时间显示：今年内 MM-DD HH:MM，跨年 YY-MM-DD HH:MM。"""
    if not iso:
        return ""
    try:
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    d = d.astimezone(CN)
    now = datetime.datetime.now(CN)
    return d.strftime("%m-%d %H:%M") if d.year == now.year else d.strftime("%y-%m-%d %H:%M")


def main():
    path = os.path.join(ROOT, "apps.json")
    doc = json.load(open(path, encoding="utf-8"))
    apps = doc.get("apps") or []

    for a in apps:
        vs = a.get("versions") or []
        p = date_prefix(vs[0].get("date") if vs else "")
        base = PREFIX.sub("", a.get("subtitle") or "")
        a["subtitle"] = f"{p} · {base}" if p and base else base or a.get("name", "")

    # 先按名字排一遍（稳定排序作兜底），再按日期倒序，同一天内保持名称顺序
    apps.sort(key=lambda x: (x.get("name") or "").casefold())
    apps.sort(key=lambda x: str((x.get("versions") or [{}])[0].get("date") or ""), reverse=True)
    doc["apps"] = apps

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print(f"✓ 已加日期前缀并排序：{len(apps)} 个应用")
    for a in apps[:6]:
        print(f"   {a['subtitle'][:44]}")
    if len(apps) > 6:
        print(f"   … 最后一位：{apps[-1]['subtitle'][:44]}")


if __name__ == "__main__":
    main()
