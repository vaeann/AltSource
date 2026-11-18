#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize.py — 收尾处理：副标题加「更新时间 + 包大小」，并按更新时间排序

放在 build.py 和 sync_repo.py 之后跑，因为它依赖最终确定下来的版本数据。

为什么都塞进副标题：LiveContainer 的源列表每一项只显示三行 —— 应用名、
「版本 (构建号) • bundle id」、副标题。日期和体积在它源码里只被解析、
从不渲染，副标题是唯一能让用户在列表里直接看到的地方。

格式：`MM-DD HH:MM · 6.6M · 应用简介`（时间为北京时间，体积超 1G 用 G）

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
# 兼容各种旧前缀：带日期、带时间、带体积的都能剥干净
PREFIX = re.compile(r"^\d{2,4}-\d{2}(?:-\d{2})?(?: \d{2}:\d{2})?(?: · [\d.]+[KMG])? · ")
# 应用名尾部可能残留上一轮加的日期，重新生成前先剥掉
NAME_TAIL = re.compile(r" \d{2,4}-\d{2}(?:-\d{2})?$")
# 副标题尾部可能残留上一轮加的体积
TAIL_SIZE = re.compile(r" · [\d.]+[KMG]$")
CN = datetime.timezone(datetime.timedelta(hours=8))


def date_prefix(iso):
    """简报只留日期：带时分太占位置（整行可用宽度只有 216pt）"""
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
    return d.strftime("%m-%d") if d.year == now.year else d.strftime("%y-%m-%d")


def text_width(s):
    """估算渲染宽度（pt）：中文 11pt/字，英文数字 6pt/字"""
    return sum(11 if ord(c) > 0x2E80 else 6 for c in s)


def trim_to_width(s, limit):
    """把文字按渲染宽度截断，超出的用省略号收尾"""
    if limit <= 0:
        return ""
    if text_width(s) <= limit:
        return s
    out, w = "", 0
    for c in s:
        cw = 11 if ord(c) > 0x2E80 else 6
        if w + cw > limit - 11:
            break
        out += c
        w += cw
    return (out.rstrip(" ·,") + "…") if out else ""


def fit_subtitle(day, base, size):
    """拼第三行：体积 + 简介（日期已经挪到第二行的构建号位置了）"""
    LIMIT = 210
    head = f"{size} · " if size else ""
    avail = LIMIT - text_width(head)
    body = trim_to_width(base, avail)
    return head + body if body else (size or base)


def size_text(n):
    """把字节数变成 6.6M / 1.2G 这种短写法"""
    if not isinstance(n, (int, float)) or n <= 0:
        return ""
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f}G"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f}M"
    return f"{n / 1024:.0f}K"


def main():
    path = os.path.join(ROOT, "apps.json")
    doc = json.load(open(path, encoding="utf-8"))
    apps = doc.get("apps") or []

    # 原始副标题优先从 zh.json 取，避免反复在前缀上叠前缀
    zh = {}
    zh_path = os.path.join(ROOT, "zh.json")
    if os.path.exists(zh_path):
        try:
            zh = json.load(open(zh_path, encoding="utf-8"))
        except Exception:
            zh = {}

    for a in apps:
        vs = a.get("versions") or []
        bid = a.get("bundleIdentifier", "")
        day = date_prefix(vs[0].get("date") if vs else "")   # 11-18
        s = size_text(vs[0].get("size") if vs else None)
        base = (zh.get(bid) or {}).get("subtitle") or PREFIX.sub("", a.get("subtitle") or "")
        base = TAIL_SIZE.sub("", base)

        # 名字保持干净（只有 210pt 宽，约 13 个中文字，加日期会被截）
        a["name"] = NAME_TAIL.sub("", a.get("name") or "")

        # 把「月-日」塞进构建号的位置：第二行会渲染成
        #   2.2.0 (11-17) • com.xxx.yyy
        # 这样第三行就腾出来放「体积 + 简介」。
        # 代价：真实构建号被替换掉（LiveContainer 只显示不比对这个字段；
        # AltStore / SideStore 会比对，那两个客户端用这个源时构建号是不准的）。
        if day and vs:
            vs[0]["buildVersion"] = day
            vs[0]["buildNumber"] = day

        a["subtitle"] = fit_subtitle(day, base, s)

    # 先按名字排一遍（稳定排序作兜底），再按日期倒序，同一天内保持名称顺序
    apps.sort(key=lambda x: (x.get("name") or "").casefold())
    apps.sort(key=lambda x: str((x.get("versions") or [{}])[0].get("date") or ""), reverse=True)
    doc["apps"] = apps

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print(f"✓ 按宽度自适应拼副标题：{len(apps)} 个应用")
    for a in apps[:8]:
        tag = "" if text_width(a["subtitle"]) <= 210 else "  ← 仍超宽"
        print(f"   {a['name'][:18]:<20}{a['subtitle'][:46]}{tag}")


if __name__ == "__main__":
    main()
