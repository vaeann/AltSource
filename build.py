#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — 把 sources.toml 里的多个上游源合并成一个干净的 AltStore 源

做事顺序:
    1. 抓每个上游的 apps.json（缓存到 _incoming/，--refresh 强制重抓）
    2. 合并所有 App，按 bundle id 去重，再按名字去重（处理同名不同 id 的分支）
    3. 套中文简介（zh.json）、配主题色、裁剪版本数量
    4. 写出 apps.json

用法:
    python build.py              # 用缓存 + 增量抓取
    python build.py --refresh    # 全部重抓
    python build.py --report     # 只打印统计，不写文件
"""
import argparse
import colorsys
import hashlib
import json
import os
import re
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import tomllib
except ImportError:
    sys.exit("需要 Python 3.11 以上（用到 tomllib）")

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "_incoming")
MIRRORS = ("https://gh-proxy.com/",)
MAX_DESC = 600


def fetch(url, timeout=60):
    """直连失败就套镜像。国内访问 raw.githubusercontent 不稳。"""
    last = None
    for target in (url,) + tuple(m + url for m in MIRRORS):
        try:
            req = urllib.request.Request(target, headers={"User-Agent": "ipa-source-build/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
    raise RuntimeError(f"{url} 抓取失败: {last}")


def tint_for(bundle_id):
    """按 bundle id 生成稳定的随机色。同一个 App 每次颜色一样。"""
    h = int(hashlib.md5(bundle_id.encode("utf-8")).hexdigest()[:8], 16) % 360 / 360.0
    s = 0.58 + (int(hashlib.md5(bundle_id.encode("utf-8")).hexdigest()[8:10], 16) % 12) / 100.0
    l = 0.44 + (int(hashlib.md5(bundle_id.encode("utf-8")).hexdigest()[10:12], 16) % 9) / 100.0
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


def norm_versions(app):
    """把老格式（顶层 version/downloadURL）也统一成 versions 数组。"""
    out = []
    for v in app.get("versions") or []:
        if not v.get("downloadURL") or not v.get("version"):
            continue
        item = {
            "version": str(v.get("version")),
            "buildVersion": str(v["buildVersion"]) if v.get("buildVersion") else None,
            "date": v.get("date") or v.get("versionDate"),
            "localizedDescription": (v.get("localizedDescription") or "")[:MAX_DESC] or None,
            "downloadURL": v["downloadURL"],
            "size": v.get("size"),
            "minOSVersion": v.get("minOSVersion"),
            "sha256": v.get("sha256"),
        }
        out.append({k: val for k, val in item.items() if val not in (None, "")})
    # LiveContainer 读的是老键名 buildNumber，AltStore 读 buildVersion，两个都写才都能显示
    for v in out:
        if "buildVersion" in v and "buildNumber" not in v:
            v["buildNumber"] = v["buildVersion"]
    if not out and app.get("downloadURL") and app.get("version"):
        item = {
            "version": str(app["version"]),
            "date": app.get("versionDate"),
            "downloadURL": app["downloadURL"],
            "size": app.get("size"),
            "localizedDescription": (app.get("versionDescription") or "")[:MAX_DESC] or None,
        }
        out.append({k: val for k, val in item.items() if val not in (None, "")})
    return out


def sort_key(v):
    return (v.get("date") or "", v.get("version") or "")


def name_key(name):
    return re.sub(r"[\s\-_·.]", "", (name or "").lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="强制重抓所有上游")
    ap.add_argument("--report", action="store_true", help="只打印统计")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "sources.toml"), "rb") as f:
        cfg = tomllib.load(f)
    with open(os.path.join(ROOT, "zh.json"), "r", encoding="utf-8") as f:
        zh = json.load(f)

    src = cfg["source"]
    keep = int(cfg.get("keep_versions", 3))
    exclude_beta = bool(cfg.get("exclude_beta", False))
    excluded = set(cfg.get("exclude") or [])
    os.makedirs(CACHE, exist_ok=True)

    # ---------- 1. 抓取 ----------
    collected = []  # (tier, 上游序号, 来源名, app)

    def collect(data, tier, prio, label):
        n = 0
        for a in data.get("apps", []):
            bid = a.get("bundleIdentifier")
            if not bid or bid in excluded:
                continue
            if exclude_beta and re.search(r"beta", a.get("name") or "", re.I):
                continue
            collected.append((tier, prio, label, a))
            n += 1
        return n

    for prio, up in enumerate(cfg.get("upstream", [])):
        label = up["label"]
        tier = int(up.get("tier", 1))
        # 本地源：先用 add_app.py + altgen 生成到 apps/xxx/apps.json，再在这里引用
        if up.get("path"):
            p = os.path.join(ROOT, up["path"])
            try:
                data = json.load(open(p, encoding="utf-8"))
                print(f"· 读本地 {label}：{collect(data, tier, prio, label)} 个应用")
            except Exception as e:
                print(f"! 本地文件读不了 {label}：{e}")
            continue

        url = up["url"]
        cache_file = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9]+", "_", label) + ".json")
        data = None
        if os.path.exists(cache_file) and not args.refresh:
            try:
                data = json.load(open(cache_file, encoding="utf-8"))
            except Exception:
                data = None
        if data is None:
            try:
                data = fetch(url)
                json.dump(data, open(cache_file, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"· 抓取 {label}：{collect(data, tier, prio, label)} 个应用")
            except Exception as e:
                print(f"! {label} 抓取失败，尝试用缓存：{e}")
                data = json.load(open(cache_file, encoding="utf-8")) if os.path.exists(cache_file) else None
                if data:
                    collect(data, tier, prio, label)
        else:
            print(f"· 读缓存 {label}：{collect(data, tier, prio, label)} 个应用")

    raw_total = len(collected)

    # ---------- 2. 去重 ----------
    BETA_RE = re.compile(r"(beta|alpha|nightly|\bbc\d*\b|\d+b\d*$)", re.I)

    def is_beta(item):
        # 版本号带预发布标记，或 bundle id 本身就是 beta 通道
        if re.search(r"beta|nightly", item[3]["bundleIdentifier"], re.I):
            return True
        vs = item[3].get("versions") or []
        return bool(vs) and bool(BETA_RE.search(str(vs[0].get("version", ""))))

    def newest(item):
        vs = item[3].get("versions") or []
        return max((str(v.get("date") or "") for v in vs), default="")

    def better(cur, new):
        """正式版优先 > 发布日期新的优先 > 官方源优先 > 版本多者优先 > 上游排序靠前。"""
        if is_beta(cur) != is_beta(new):
            return not is_beta(new)
        dc, dn = newest(cur), newest(new)
        if bool(dc) != bool(dn):
            return bool(dn)
        if dc and dn and dc != dn:
            return dn > dc
        if cur[0] != new[0]:
            return new[0] < cur[0]
        if len(new[3].get("versions") or []) != len(cur[3].get("versions") or []):
            return len(new[3].get("versions") or []) > len(cur[3].get("versions") or [])
        return new[1] < cur[1]

    by_id = {}
    for item in collected:
        bid = item[3]["bundleIdentifier"]
        if bid not in by_id or better(by_id[bid], item):
            by_id[bid] = item

    by_name = {}
    dropped = []

    def better_name(cur, new):
        """同名但 bundle id 不同 = 不同分支。优先版本更全的那个，再比日期。"""
        if is_beta(cur) != is_beta(new):
            return not is_beta(new)
        if len(new[3].get("versions") or []) != len(cur[3].get("versions") or []):
            return len(new[3].get("versions") or []) > len(cur[3].get("versions") or [])
        dc, dn = newest(cur), newest(new)
        if dc and dn and dc != dn:
            return dn > dc
        return new[0] < cur[0]

    for bid, item in by_id.items():
        nk = name_key(item[3].get("name"))
        if nk not in by_name or better_name(by_name[nk], item):
            if nk in by_name:
                dropped.append((by_name[nk][3].get("name"), by_name[nk][3]["bundleIdentifier"],
                                item[3]["bundleIdentifier"]))
            by_name[nk] = item
        else:
            dropped.append((item[3].get("name"), bid, by_name[nk][3]["bundleIdentifier"]))

    # ---------- 3. 整理 ----------
    apps = []
    missing_zh = []
    official_n = 0
    for nk, (tier, prio, label, a) in by_name.items():
        bid = a["bundleIdentifier"]
        versions = norm_versions(a)
        if not versions:
            continue
        if tier == 0:
            official_n += 1
        versions.sort(key=sort_key, reverse=True)
        versions = versions[:keep]

        name = a.get("name") or bid
        meta = zh.get(bid) or {}
        if not meta:
            missing_zh.append((name, bid))
        sub = meta.get("subtitle") or (a.get("subtitle") or "")[:80] or name
        desc = meta.get("description") or (a.get("localizedDescription") or "")[:MAX_DESC] or name

        entry = {
            "name": name,
            "bundleIdentifier": bid,
            "developerName": a.get("developerName") or "",
            "subtitle": sub,
            "localizedDescription": desc,
            "iconURL": a.get("iconURL") or "",
            "tintColor": tint_for(bid),
            "category": a.get("category") or "other",
            "versions": versions,
        }
        if a.get("appPermissions"):
            entry["appPermissions"] = a["appPermissions"]
        if a.get("screenshots"):
            entry["screenshots"] = a["screenshots"]
        apps.append(entry)

    apps.sort(key=lambda x: x["name"].casefold())

    doc = {
        "name": src["name"],
        "subtitle": src.get("subtitle", ""),
        "description": src.get("description", ""),
        "identifier": src["identifier"],
        "iconURL": src.get("icon_url", ""),
        "website": src.get("website", ""),
        "tintColor": src.get("tint_color", "#6B4EFF"),
        "featuredApps": [a["bundleIdentifier"] for a in apps[:5]],
        "apps": apps,
        "news": [],
    }
    doc = {k: v for k, v in doc.items() if v not in ("", [], None)} | {"apps": apps}
    doc.setdefault("news", [])

    # ---------- 4. 输出 ----------
    print()
    print(f"上游条目   {raw_total}")
    print(f"按 id 去重 {len(by_id)}")
    print(f"按名去重   {len(apps)}")
    print(f"官方源覆盖 {official_n} 个 / 聚合源补 {len(apps) - official_n} 个")
    if dropped:
        print(f"丢弃同名   {len(dropped)} 组")
        for n, old_id, new_id in dropped[:8]:
            print(f"   · {n}: 采用 {new_id}，丢弃 {old_id}")
    if missing_zh:
        print(f"缺中文简介 {len(missing_zh)} 个（已用原文兜底）")
        for n, b in missing_zh[:10]:
            print(f"   · {n} ({b})")

    if args.report:
        return

    out = os.path.join(ROOT, "apps.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(out)
    print()
    print(f"✓ 写出 apps.json：{len(apps)} 个应用，{size / 1024:.0f} KB")
    print(f"  版本总数 {sum(len(a['versions']) for a in apps)}")


if __name__ == "__main__":
    main()
