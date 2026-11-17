# 我的软件源

把多个上游软件源**去重合并**成一个自己的 AltStore 源。共 **94 个应用**，全部中文简介，自动同步上游更新。

其中 **24 个应用直接用各自项目的官方源数据**，其余用聚合源补齐。

## 订阅地址

```
https://raw.githubusercontent.com/vaeann/AltSource/main/apps.json
```

支持 **LiveContainer / Feather / SideStore / AltStore**。

国内直连不稳时用镜像（下载慢一点但能通）：

```
https://gh-proxy.com/https://raw.githubusercontent.com/vaeann/AltSource/main/apps.json
```

## 数据从哪来

**版本数据一律直接从各项目的官方 GitHub 仓库拉**，不走第三方聚合源。

流程是两步：

1. `build.py` 合并上游源，拿到 **静态信息**：bundle id、应用名、图标、中文简介、主题色；
2. `sync_repo.py` 拿着每个应用的 GitHub 仓库地址，去拉它的 Release 列表，把 **版本号、发布日期、下载地址、包体积、更新说明**全换成官方数据。

所以只要作者在自己的仓库发了新版，下一次构建就是最新的。

**上游源（23 个官方 + 3 个兜底）**：只用来提供上面那些静态信息，以及给少数不在 GitHub 发布的应用（如 Delta、Clip 走 `cdn.altstore.io`）提供数据。

原始 133 条 → 按 bundle id 去重 99 → 按名称去重 **94**。

## 目录说明

| 文件 | 作用 |
|---|---|
| `apps.json` | **最终产物**，客户端拉的就是这个 |
| `sources.toml` | 上游源列表 + 源本身的信息 |
| `zh.json` | bundle id → 中文简介 / 副标题 |
| `build.py` | 合并引擎：抓取 → 去重 → 中文化 → 配主题色 |
| `sync_repo.py` | 用各项目官方仓库的 Release 覆盖版本数据 |
| `_incoming/` | 上游源缓存，供离线构建 |
| `add_app.py` | 可选：单独给某个 GitHub 仓库生成配置文件（见下） |
| `.github/workflows/update.yml` | 每 6 小时自动跑一次 |

## 自动更新怎么跑

Actions **每 6 小时**跑一次：

1. `build.py --refresh`：重新抓上游源，去重合并，保证应用清单完整；
2. `sync_repo.py`：逐个访问每个应用的官方仓库，把版本数据换成 Release 里的真实值；
3. 有变化才提交，没变化什么都不做。

想立刻更新：仓库页 → **Actions → 更新软件源 → Run workflow**。

## 加一个新源

在 `sources.toml` 末尾加一段，然后重跑 `python build.py --refresh`：

```toml
[[upstream]]
label = "某个源"
url = "https://raw.githubusercontent.com/xxx/yyy/main/apps.json"
tier = 0    # 0 = 官方源，1 = 聚合源（不写默认 1）
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

## 处理规则

**build.py（合并阶段）**

| 环节 | 规则 |
|---|---|
| 去重 | 先按 bundle id，再按名称（忽略空格、连字符、大小写） |
| 选正式版 | 版本号带 beta / alpha / nightly 的条目降权，能不用就不用 |
| 选新旧 | 比较最新版本的发布日期，新的优先（官方源更新滞后时不会被旧数据顶掉） |
| 官方优先 | 日期相同或缺失时，官方源压过聚合源 |
| 同名不同 id | 视为分支，保留版本更全的那个（如 TiebaPure） |
| 版本数量 | 每个应用最多留 3 个最新版本（改 `keep_versions` 可调） |
| 中文简介 | 优先用 `zh.json`；没收录的用原文兜底，构建日志会列出来 |
| 主题色 | 按 bundle id 哈希生成，同一个应用每次颜色固定，互不重复 |
| 描述截断 | 单个版本更新说明最多 600 字，控制文件体积 |

**sync_repo.py（官方仓库阶段）**

| 环节 | 规则 |
|---|---|
| 版本号 | 先从 IPA 资源文件名里找 `x.y.z`，找不到再用 tag；两边都提取不出就**跳过不动** |
| 何时覆盖 | 只有官方 Release 的发布日期晚于现有数据才覆盖，避免版本倒退 |
| 构建号 | 从资源文件名或 tag 里的 `+123` / `-123` 提取，同时写 `buildVersion` 和 `buildNumber` |
| 最低系统 | Release 里没这信息，从旧数据按版本号沿用 |
| 预发布版 | 默认收录（`include_prerelease = true`）。作者发 `v2.2.0-pre.1` 时能第一时间拿到，tag 后缀不影响真实版本号 |
| 失败处理 | 拉不到的（如 `nightly` 这种没有数字版本号的）保留原数据，日志里列出来 |

## 已知限制

- **构建号在 LiveContainer 里不显示**：源里字段叫 `buildVersion`，LiveContainer 读的是 `buildNumber`（老名字）。不影响安装。
- **最低系统版本对 LiveContainer 无效**：它不筛系统版本，装完打不开才知道。装之前自己看一眼要求。
- **权限声明（appPermissions）不全**：上游源带过来的才有。LiveContainer / Feather 不看这个；AltStore / SideStore 装包时会比对 entitlements，报权限不匹配就是这个原因。
- **部分下载地址走 `gh-proxy.com` 镜像**（JiPengLin 那三个应用，在还没被官方仓库覆盖时）。官方仓库同步成功后会换回 GitHub 原始地址。
- **本源只做汇总，不签名、不修改安装包**，所有应用版权归各自作者。

## 免责

源里收录的是公开渠道发布的开源项目或官方安装包。请自行确认所在地区的法律法规与年龄限制，使用风险自负。
