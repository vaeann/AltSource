#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_app.py — 给 AltGen 自动生成一份 config.toml

用法:
    python add_app.py owner/repo
    python add_app.py owner/repo --name 我的App --include-prereleases
    python add_app.py owner/repo --dir apps/MyApp

它会做三件事:
    1. 调 GitHub Releases 接口，找到最近一个带 .ipa 的发行版
    2. 下载那个 IPA，解开读 Info.plist，拿到真实 bundle id / 最低系统版本
    3. 写出 apps/<AppName>/config.toml，直接可以喂给 altgen

为什么要干第 2 步: bundle id 必须和 IPA 里一字不差（大小写敏感），
抄错的话 AltStore 会拒绝安装，LiveContainer 里也会对不上号。
"""
import argparse
import json
import os
import plistlib
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = {"User-Agent": "add-app/1.0", "Accept": "application/vnd.github+json"}


def _request(url, token=None, direct=False, timeout=60):
    """direct=True 时绕开系统代理。本机代理会拦 GitHub 的 CDN 下载。"""
    opener = urllib.request.build_opener(
        *([urllib.request.ProxyHandler({})] if direct else [])
    )
    req = urllib.request.Request(url, headers=dict(UA))
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return opener.open(req, timeout=timeout)


def _get_json(url, token=None):
    for direct in (False, True):
        try:
            with _request(url, token, direct=direct) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if direct:
                raise
    raise RuntimeError("unreachable")


MIRRORS = ("https://gh-proxy.com/",)


def _download(url, dest, token=None):
    """依次尝试: 绕代理直连 → 系统代理 → 镜像站。国内直连 GitHub CDN 基本必挂。"""
    attempts = [(url, True), (url, False)] + [(m + url, True) for m in MIRRORS]
    last = None
    for target, direct in attempts:
        try:
            with _request(target, token, direct=direct, timeout=300) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 16)
            if os.path.getsize(dest) > 4096:
                return target
        except Exception as e:
            last = e
            if os.path.exists(dest):
                os.remove(dest)
    raise RuntimeError(f"IPA 下载失败（直连和镜像都没通）: {last}")


def list_releases(repo, token=None, include_pre=False, asset_re=r"\.ipa$"):
    releases = _get_json(
        f"https://api.github.com/repos/{repo}/releases?per_page=30", token
    )
    out = []
    for rel in releases:
        if rel.get("draft"):
            continue
        if rel.get("prerelease") and not include_pre:
            continue
        assets = [
            a for a in rel.get("assets", [])
            if re.search(asset_re, a.get("name", ""), re.I)
        ]
        if assets:
            out.append((rel, assets))
    return out


def read_ipa_meta(ipa_path):
    """从 IPA 主 App 的 Info.plist 里读关键信息。"""
    with zipfile.ZipFile(ipa_path) as z:
        names = z.namelist()
        cands = [
            n for n in names
            if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n)
        ]
        if not cands:
            raise RuntimeError("IPA 里找不到 Payload/*.app/Info.plist")
        with z.open(cands[0]) as fp:
            pl = plistlib.load(fp)
    return {
        "bundle_id": pl.get("CFBundleIdentifier", ""),
        "version": pl.get("CFBundleShortVersionString", ""),
        "build": str(pl.get("CFBundleVersion", "")),
        "min_os": pl.get("MinimumOSVersion", ""),
        "display_name": pl.get("CFBundleDisplayName") or pl.get("CFBundleName") or "",
    }


def q(s):
    """TOML 基本字符串转义。"""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="owner/repo，例如 Kianuni/Camlo")
    ap.add_argument("--name", help="源 / App 显示名，默认取仓库名")
    ap.add_argument("--bundle-id", help="跳过下载解析，直接指定 bundle id")
    ap.add_argument("--min-os", help="最低系统版本，例如 15.0；跳过下载时用它补")
    ap.add_argument("--dir", help="输出目录，默认 apps/<name>")
    ap.add_argument("--include-prereleases", action="store_true")
    ap.add_argument("--asset", default=r"\.ipa$", help="匹配 IPA 文件名的正则")
    ap.add_argument("--max-versions", type=int, default=10, help="保留多少个历史版本")
    ap.add_argument("--tint", default="#6B4EFF", help="主题色 #RRGGBB")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = args.repo.strip().strip("/")
    if "/" not in repo:
        sys.exit("仓库要写成 owner/repo 的形式")
    owner, rname = repo.split("/", 1)
    name = args.name or rname

    print(f"· 读取 {repo} 的发行版…")
    rels = list_releases(repo, token, args.include_prereleases, args.asset)
    if not rels:
        sys.exit("没有找到带 IPA 的发行版")
    rel, assets = rels[0]
    asset = assets[0]
    print(f"· 命中 {rel['tag_name']} → {asset['name']}")

    bundle_id, min_os, dev, ver = args.bundle_id, (args.min_os or ""), owner, rel["tag_name"]
    if not bundle_id:
        tmp = os.path.join(tempfile.gettempdir(), "add_app_" + asset["name"])
        print(f"· 下载 IPA 解析真实信息（{asset['size'] / 1048576:.1f} MB）…")
        _download(asset["browser_download_url"], tmp, token)
        try:
            meta = read_ipa_meta(tmp)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        bundle_id = meta["bundle_id"]
        min_os = meta["min_os"]
        ver = meta["version"] or ver
        print(f"  bundle id = {bundle_id}，最低系统 = {min_os or '未声明'}，版本 = {ver}")
        if not bundle_id:
            sys.exit("IPA 里没读到 CFBundleIdentifier，请用 --bundle-id 手动指定")

    # 从资源文件名里找构建号，例如 App_v1.2.3_45.ipa
    build_pat = ""
    m = re.search(r"[_+.](\d{1,5})\.ipa$", asset["name"], re.I)
    if m:
        build_pat = r"[_+.](\d{1,5})\.ipa$"

    # 简介优先用仓库的 description；release 正文是更新日志，不能当简介
    repo_info = {}
    try:
        repo_info = _get_json(f"https://api.github.com/repos/{repo}", token) or {}
    except Exception:
        pass
    desc = (repo_info.get("description") or "").strip() or name
    desc = re.sub(r"\s+", " ", desc)

    outdir = args.dir or os.path.join("apps", re.sub(r"[^A-Za-z0-9_.-]", "_", name))
    os.makedirs(outdir, exist_ok=True)
    cfg = os.path.join(outdir, "config.toml")
    icon = f"https://github.com/{owner}.png?size=256"

    lines = [
        f"# 由 add_app.py 生成于 {repo}",
        f"# 重新生成: python add_app.py {repo}" + (f" --name {name}" if args.name else ""),
        "",
        "[github]",
        f"repo = {q(repo)}",
        "",
        "[source]",
        f"name = {q(name)}",
        f"subtitle = {q(desc[:80])}",
        f"description = {q(desc)}",
        f"icon_url = {q(icon)}",
        f"website = {q(f'https://github.com/{repo}')}",
        f"tint_color = {q(args.tint)}",
        "",
        "[app]",
        f"name = {q(name)}",
        f"bundle_identifier = {q(bundle_id)}",
        f"developer_name = {q(dev)}",
        f"subtitle = {q(desc[:80])}",
        f"description = {q(desc)}",
        f"icon_url = {q(icon)}",
    ]
    if min_os:
        lines.append(f"min_os_version = {q(min_os)}")
    lines += [
        "",
        "[versions]",
        "strip_v_prefix = true",
        f"include_prereleases = {'true' if args.include_prereleases else 'false'}",
        f"asset_pattern = {q(args.asset)}",
    ]
    if build_pat:
        lines.append(f"build_version_pattern = {q(build_pat)}")
    lines += [
        f"max_versions = {args.max_versions}",
        "",
        "[news]",
        "enabled = true",
        "",
        "[output]",
        'path = "apps.json"',
        "",
    ]
    with open(cfg, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    print(f"✓ 写好 {cfg}")
    print(f"  下一步:  python -m altgen -c {cfg}")


if __name__ == "__main__":
    main()
