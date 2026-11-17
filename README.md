# 我的软件源

把多个上游软件源**去重合并**成一个自己的 AltStore 源。共 **87 个应用**，全部中文简介，自动同步上游更新。

## 订阅地址

```
https://raw.githubusercontent.com/vaeann/AltSource/main/apps.json
```

支持 **LiveContainer / Feather / SideStore / AltStore**。

国内直连不稳时用镜像（下载慢一点但能通）：

```
https://gh-proxy.com/https://raw.githubusercontent.com/vaeann/AltSource/main/apps.json
```

## 它合并了哪些源

| 上游 | 应用数 |
|---|---|
| INSAV 官方 | 1 |
| WQ Files 官方 | 1 |
| Camlo 官方 | 1 |
| Laincat 工具箱 | 26 |
| JiPengLin 精选 | 3 |
| AltGallery | 71 |

原始 103 条 → 按 bundle id 去重 88 → 按名称去重 **87**（TiebaPure 有两个分支，保留版本更全的那个）。

## 目录说明

| 文件 | 作用 |
|---|---|
| `apps.json` | **最终产物**，客户端拉的就是这个 |
| `sources.toml` | 上游源列表 + 源本身的信息 |
| `zh.json` | bundle id → 中文简介 / 副标题 |
| `build.py` | 合并引擎：抓取 → 去重 → 中文化 → 配主题色 → 裁剪版本 |
| `_incoming/` | 上游源缓存，供离线构建 |
| `add_app.py` | 可选：单独给某个 GitHub 仓库生成配置文件（见下） |
| `.github/workflows/update.yml` | 每 6 小时自动合并一次 |

## 自动更新怎么跑

推到 GitHub 后，Actions **每 6 小时**跑一次 `build.py --refresh`：

1. 重新抓 6 个上游源；
2. 重新去重合并；
3. 有变化才提交，没变化什么都不做。

想立刻更新：仓库页 → **Actions → 更新软件源 → Run workflow**。

## 加一个新源

在 `sources.toml` 末尾加一段，然后重跑 `python build.py --refresh`：

```toml
[[upstream]]
label = "某个源"
url = "https://raw.githubusercontent.com/xxx/yyy/main/apps.json"
```

## 加一个新 App（只有 GitHub 仓库地址、没有现成源）

```bash
python add_app.py owner/repo --name 应用名
```

它会下载那个仓库最新的 IPA，**解开读真实的 bundle id**（手工抄必错），生成 `apps/<名字>/config.toml`。然后：

```bash
pip install altgen
python -m altgen -c apps/<名字>/config.toml
```

再在 `sources.toml` 里用本地路径引用它：

```toml
[[upstream]]
label = "应用名"
path = "apps/<名字>/apps.json"
```

## 处理规则（build.py 干了什么）

| 环节 | 规则 |
|---|---|
| 去重 | 先按 bundle id，再按名称（忽略空格、连字符、大小写） |
| 保留谁 | 版本数多的优先；版本数相同则 `sources.toml` 里排序靠前的优先 |
| 版本数量 | 每个应用最多留 3 个最新版本（改 `keep_versions` 可调） |
| 中文简介 | 优先用 `zh.json`；没收录的用原文兜底，构建日志会列出来 |
| 主题色 | 按 bundle id 哈希生成，同一个应用每次颜色固定，互不重复 |
| 描述截断 | 单个版本更新说明最多 600 字，控制文件体积 |

## 已知限制

- **构建号在 LiveContainer 里不显示**：源里字段叫 `buildVersion`，LiveContainer 读的是 `buildNumber`（老名字）。不影响安装。
- **最低系统版本对 LiveContainer 无效**：它不筛系统版本，装完打不开才知道。装之前自己看一眼要求。
- **权限声明（appPermissions）不全**：上游源带过来的才有。LiveContainer / Feather 不看这个；AltStore / SideStore 装包时会比对 entitlements，报权限不匹配就是这个原因。
- **部分下载地址走 `gh-proxy.com` 镜像**（JiPengLin 那三个应用）。镜像挂了会下载失败，到时候换掉那条上游即可。
- **本源只做汇总，不签名、不修改安装包**，所有应用版权归各自作者。

## 免责

源里收录的是公开渠道发布的开源项目或官方安装包。请自行确认所在地区的法律法规与年龄限制，使用风险自负。
