#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
split.py — 把应用清单切成若干个订阅源，每个最多 50 个

起因：LiveContainer 的源列表最多只显示 50 个应用，超出的只能靠搜索。
所以按更新时间倒序，每 50 个切一片，每片一个订阅地址。

输出文件:
    apps.json      → 热门应用源①（最近更新的 50 个）
    apps-2.json    → 热门应用源②
    apps-3.json    → 热门应用源③
    ...

应用变多会自动多切一片，不用改配置；不再需要的分片会被删掉。
放在 finalize.py 之后跑，因为依赖已经排好序的 apps 数组。
"""
import glob
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
PER_SOURCE = 50
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def label(i):
    return CIRCLED[i - 1] if i <= len(CIRCLED) else f"({i})"


def list_shards():
    """按序号列出分片文件：apps.json 是第 1 个，apps-2.json 是第 2 个……"""
    out = []
    first = os.path.join(ROOT, "apps.json")
    if os.path.exists(first):
        out.append((1, first))
    for i in range(2, 100):
        p = os.path.join(ROOT, f"apps-{i}.json")
        if os.path.exists(p):
            out.append((i, p))
    return out


def main():
    shards = list_shards()
    if not shards:
        sys.exit("找不到可用的应用清单，先跑 build.py")

    # 把上次切好的分片拼回完整清单（build.py 产出的 apps.json 是完整的，
    # 但 split 跑过之后它就是第 1 片了，所以每次都要先拼回来）
    apps, seen, base = [], set(), None
    for idx, p in shards:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if base is None:
            base = d
        for a in d.get("apps") or []:
            bid = a.get("bundleIdentifier")
            if bid and bid not in seen:
                seen.add(bid)
                apps.append(a)

    if not apps:
        sys.exit("分片里没有应用数据")

    apps.sort(key=lambda x: str((x.get("versions") or [{}])[0].get("date") or ""), reverse=True)
    total = len(apps)
    chunks = [apps[i:i + PER_SOURCE] for i in range(0, total, PER_SOURCE)]

    written = []
    for idx, chunk in enumerate(chunks, 1):
        fn = "apps.json" if idx == 1 else f"apps-{idx}.json"
        doc = {
            "name": f"热门应用源{label(idx)}",
            "subtitle": f"第 {idx} 批 · 按更新时间排序 · 自动同步上游",
            "description": (
                f"精挑细选的 iOS 侧载应用合集，共 {total} 个，按更新频率分成 {len(chunks)} 个源，"
                f"这里是第 {idx} 个（{len(chunk)} 个）。\n\n"
                "版本数据直接从各项目的官方 GitHub 仓库拉取，副标题开头的日期是最近一次发版时间（北京时间）。"
            ),
            "identifier": (base.get("identifier") or "com.vaeann.source") + ("" if idx == 1 else f".{idx}"),
            "iconURL": base.get("iconURL", ""),
            "website": base.get("website", ""),
            "tintColor": "#6B4EFF" if idx == 1 else "#8A8984",
            "featuredApps": [a["bundleIdentifier"] for a in chunk[:5]],
            "apps": chunk,
            "news": [],
        }
        doc = {k: v for k, v in doc.items() if v not in ("", [], None)}
        doc["apps"] = chunk
        doc["news"] = []
        with open(os.path.join(ROOT, fn), "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        written.append(fn)
        print(f"  热门应用源{label(idx)}  {len(chunk):>3} 个  → {fn}")

    # 额外生成一个「完整版」：①②③…全部合在一起，给只想订阅一个地址的场景用
    all_doc = {
        "name": "热门软件合集",
        "subtitle": "热门应用都在这里 · 按更新时间排序",
        "description": (
            f"精挑细选的 iOS 侧载应用合集，{total} 个应用全在这一条源里，按更新时间倒序排列。\n\n"
            f"注意：LiveContainer 的列表最多只显示 50 个，超出部分要搜索才能看到。"
            f"如果只想看最近更新的，用「热门应用源①」；想看全部就用这个。\n\n"
            "版本数据直接从各项目的官方 GitHub 仓库拉取。"
        ),
        "identifier": (base.get("identifier") or "com.vaeann.source") + ".all",
        "iconURL": base.get("iconURL", ""),
        "website": base.get("website", ""),
        "tintColor": "#3D8B7D",
        "featuredApps": [a["bundleIdentifier"] for a in apps[:5]],
        "apps": apps,
        "news": [],
    }
    all_doc = {k: v for k, v in all_doc.items() if v not in ("", [], None)}
    all_doc["apps"] = apps
    all_doc["news"] = []
    with open(os.path.join(ROOT, "apps-all.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(all_doc, f, ensure_ascii=False, indent=2)
    print(f"  热门应用源 · 完整版  {total:>3} 个  → apps-all.json")

    keep_files = set(written) | {"apps-all.json"}
    for p in glob.glob(os.path.join(ROOT, "apps*.json")):
        if os.path.basename(p) not in keep_files:
            os.remove(p)
            print(f"  已删除多余分片 {os.path.basename(p)}")

    print(f"\n合计 {total} 个应用，分 {len(chunks)} 个源 + 1 个完整版")


if __name__ == "__main__":
    main()
