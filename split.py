#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
split.py — 把合并好的应用清单拆成两个订阅源

起因：LiveContainer 的源列表最多只显示 50 个应用，超出的只能靠搜索。
与其删应用，不如拆成两个源，各自都在 50 以内。

分工规则（自动维护，不用人工干预）:
    主源   = 最近 90 天内更新过的，按更新时间倒序，最多 50 个
    备用源 = 其余（停更较久的，以及活跃应用超过 50 个时溢出的部分）

放在 finalize.py 之后跑，因为依赖已经排好序的 apps 数组。
"""
import datetime
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
CN = datetime.timezone(datetime.timedelta(hours=8))
ACTIVE_DAYS = 90
MAX_PRIMARY = 50


def parse(iso):
    if not iso:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None
    return d.replace(tzinfo=datetime.timezone.utc) if d.tzinfo is None else d


def main():
    path = os.path.join(ROOT, "apps.json")
    doc = json.load(open(path, encoding="utf-8"))
    apps = doc.get("apps") or []
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=ACTIVE_DAYS)

    active, dormant = [], []
    for a in apps:
        vs = a.get("versions") or []
        t = parse(vs[0].get("date") if vs else "")
        (active if (t and t >= cutoff) else dormant).append(a)

    # apps 已按时间倒序，活跃的直接取前 50，溢出的归到备用源
    primary = active[:MAX_PRIMARY]
    extra = active[MAX_PRIMARY:] + dormant

    doc["apps"] = primary
    doc["featuredApps"] = [a["bundleIdentifier"] for a in primary[:5]]
    doc["subtitle"] = "持续更新的应用都在这里 · 自动同步上游"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    extra_doc = {
        "name": f"{doc.get('name', '我的软件源')} · 备用",
        "subtitle": "更新较慢或停更的应用，能装能用",
        "description": (
            "主源里放不下、或者上游已经较少更新的应用都收在这里。\n\n"
            "这些应用仍然可用，只是作者最近没发新版。想找就单独订阅这个源。"
        ),
        "identifier": (doc.get("identifier") or "com.vaeann.source") + ".extra",
        "iconURL": doc.get("iconURL", ""),
        "website": doc.get("website", ""),
        "tintColor": "#8A8984",
        "featuredApps": [a["bundleIdentifier"] for a in extra[:5]],
        "apps": extra,
        "news": [],
    }
    extra_doc = {k: v for k, v in extra_doc.items() if v not in ("", [], None)}
    extra_doc["apps"] = extra
    extra_doc["news"] = []
    out_extra = os.path.join(ROOT, "apps-extra.json")
    with open(out_extra, "w", encoding="utf-8", newline="\n") as f:
        json.dump(extra_doc, f, ensure_ascii=False, indent=2)

    print(f"主源   {len(primary):>3} 个（{ACTIVE_DAYS} 天内更新过）→ apps.json")
    print(f"备用源 {len(extra):>3} 个（停更或溢出）→ apps-extra.json")
    print(f"合计   {len(apps):>3} 个")
    if len(primary) > MAX_PRIMARY:
        print("! 主源超过上限，已自动往备用源挤")


if __name__ == "__main__":
    main()
