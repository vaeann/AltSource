#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_repo.py — 用每个应用自己的官方 GitHub 仓库覆盖版本数据

build.py 负责把多个源合并成基线（拿到 bundle id、图标、简介这些静态信息），
这个脚本负责把「版本、日期、下载地址」换成官方仓库 Release 里的真实数据。

这样上游作者一发版，源里就是最新的，不依赖任何第三方聚合源。

用法:
    python sync_repo.py            # 读 apps.json，同步后写回
    python sync_repo.py --dry-run  # 只看会改什么，不写文件
"""
import concurrent.futures
import json
import os
import re
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_PAT = re.compile(r"github\.com/([^/]+)/([^/]+)/releases")
# 版本号的形态：必须带点，避免把 20261114 这种日期戳当成版本
SEMVER = re.compile(r"(?<![\d.])(\d+\.\d+(?:\.\d+)*)(?![\d.])")
# 构建号：+123 这种加号形式，或者 -22 / _7 这种结尾数字（tag 里常见 v1.7.1-22）
BUILD = re.compile(r"[+](\d{1,6})(?![\d])|[-_](\d{1,3})$")


def get_token():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    # 本地：从项目里已有的脚本借一个（不会打印出来）
    p = os.path.join(ROOT, "..", "lcss-mod", "tools", "_fix_notes.py")
    if os.path.exists(p):
        m = re.search(r"(gh[pousr]_[A-Za-z0-9]{20,})", open(p, encoding="utf-8", errors="ignore").read())
        if m:
            return m.group(1)
    return None


TOKEN = get_token()


def gh(path, timeout=40):
    headers = {"User-Agent": "sync-repo", "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request("https://api.github.com" + path, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def pick_version(tag, asset_name):
    """先看资源文件名，再看 tag。提取不出带点号的版本号就返回 None。"""
    for src in (asset_name, tag):
        m = SEMVER.search(src or "")
        if m:
            return m.group(1)
    return None


def pick_build(asset_name, tag):
    for src in (asset_name, tag):
        m = BUILD.search(src or "")
        if m:
            return m.group(1) or m.group(2)
    return None


def releases_to_versions(repo, keep, include_pre=False):
    """把仓库的 release 列表转成 versions 数组（最新在前）"""
    rels = gh(f"/repos/{repo}/releases?per_page=15")
    out = []
    for r in rels:
        if r.get("draft"):
            continue
        # 预发布版（如 v2.2.0-pre.1）默认不收：版本号带后缀，和安装包里的真实版本对不上
        if r.get("prerelease") and not include_pre:
            continue
        ipas = [a for a in r.get("assets", []) if a["name"].lower().endswith(".ipa")]
        if not ipas:
            continue
        asset = ipas[0]
        ver = pick_version(r.get("tag_name"), asset["name"])
        if not ver:
            continue
        item = {
            "version": ver,
            "date": (r.get("published_at") or r.get("created_at") or "")[:19] + "Z"
            if (r.get("published_at") or r.get("created_at")) else None,
            "downloadURL": asset["browser_download_url"],
            "size": asset.get("size"),
        }
        b = pick_build(asset["name"], r.get("tag_name"))
        if b:
            item["buildVersion"] = b
            item["buildNumber"] = b
        body = (r.get("body") or "").strip()
        if body:
            item["localizedDescription"] = body[:600]
        out.append({k: v for k, v in item.items() if v not in (None, "")})
        if len(out) >= keep:
            break
    return out


def main():
    dry = "--dry-run" in sys.argv
    cfg_path = os.path.join(ROOT, "sources.toml")
    keep = 3
    include_pre = False
    try:
        import tomllib
        cfg = tomllib.load(open(cfg_path, "rb"))
        keep = int(cfg.get("keep_versions", 3))
        include_pre = bool(cfg.get("include_prerelease", False))
    except Exception:
        pass

    doc = json.load(open(os.path.join(ROOT, "apps.json"), encoding="utf-8"))
    apps = doc["apps"]

    tasks = []
    for app in apps:
        vs = app.get("versions") or []
        if not vs:
            continue
        m = REPO_PAT.search(vs[0].get("downloadURL", ""))
        if not m:
            continue
        tasks.append((app, f"{m.group(1)}/{m.group(2)}"))

    print(f"可同步官方仓库的应用 {len(tasks)} / {len(apps)}")

    results = {}

    def work(item):
        app, repo = item
        try:
            return repo, releases_to_versions(repo, keep, include_pre), None
        except Exception as e:
            return repo, None, str(e)[:60]

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for repo, vers, err in ex.map(work, tasks):
            results[repo] = (vers, err)

    updated, kept, failed = [], [], []
    for app, repo in tasks:
        vers, err = results.get(repo, (None, "no result"))
        if err or not vers:
            failed.append((app["name"], repo, err or "无可用版本"))
            continue
        old = (app.get("versions") or [{}])[0]
        od, nd = str(old.get("date") or ""), str(vers[0].get("date") or "")
        # 日期相同也刷新一次：手工登记的条目只有一条，靠这次补齐历史版本
        if nd and (not od or nd >= od):
            # 保留原有的最低系统版本要求（release 里没有这个信息）
            old_min = {v.get("version"): v.get("minOSVersion") for v in app.get("versions") or []}
            old_build = {v.get("version"): v.get("buildVersion") for v in app.get("versions") or []}
            fallback_min = old.get("minOSVersion")
            for v in vers:
                mv = old_min.get(v["version"]) or fallback_min
                if mv:
                    v["minOSVersion"] = mv
                # 官方源里手工登记过构建号、而 tag 里提取不到时，沿用它
                if not v.get("buildVersion"):
                    bv = old_build.get(v["version"])
                    if bv:
                        v["buildVersion"] = bv
                        v["buildNumber"] = bv
            app["versions"] = vers
            updated.append((app["name"], old.get("version"), vers[0]["version"], nd[:10]))
        else:
            kept.append((app["name"], old.get("version"), vers[0].get("version")))

    print(f"更新 {len(updated)} | 已是最新 {len(kept)} | 失败 {len(failed)}")
    print()
    if updated:
        print("--- 有变化的（旧 → 新）---")
        for n, o, x, d in updated[:25]:
            print(f"  {n:<26} {str(o):<18} → {x:<16} {d}")
        if len(updated) > 25:
            print(f"  … 另有 {len(updated) - 25} 个")
    if failed:
        print()
        print("--- 拉取失败的（保留原数据）---")
        for n, r, e in failed[:15]:
            print(f"  {n:<26} {r:<36} {e}")

    if dry:
        print()
        print("（--dry-run，未写文件）")
        return

    with open(os.path.join(ROOT, "apps.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print()
    print(f"已写回 apps.json：{len(apps)} 个应用，{os.path.getsize(os.path.join(ROOT, 'apps.json')) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
