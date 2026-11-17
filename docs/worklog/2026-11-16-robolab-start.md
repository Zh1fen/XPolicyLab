# 2026-11-16：RoboLab 命名与一键启动

## 目标与变更

用户要求根目录简单脚本启动，并希望项目拥有独立名称。
在尚未提交的控制台改动基础上增加可执行 start.sh，自动选择配置，支持任意调用目录与参数转发。
页面、CLI、项目发行名称和主要文档统一为 RoboLab，控制台页面名称保持“控制台”。
根 README 改为简洁项目入口；详细兼容接口文档移到 reference，原锚点保留。
上游来源与原引用信息集中在 UPSTREAM.md；LICENSE、模型版权头和兼容导入路径不改。

## 验证

| 检查 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_start.py -v` | 五项通过：其他调用目录、含空格路径、默认/本地配置选择、参数转发、缺失 Python 提示、实际 HTTP 启动及品牌输出 |
| `policy/Pi_05/openpi/.venv/bin/python -m unittest discover -s tests -q` | 65 项通过，无跳过 |
| `python3 scripts/check_workspace.py` | 39 份文档、八个 adapter、56 个 Python 文件、62 个 shell 文件检查通过；旧锚点仍有效 |
| `node --check web/static/app.js` / `git diff --check` | 通过 |
| Playwright / Chromium | 通过根 start.sh 启动，标题与页面为 RoboLab，创建 CPU 任务成功，无页面脚本错误；截图在 artifacts/robolab-qa/console.png |
| 离线 wheel 构建 | 生成 robolab-infra，保留 XPolicyLab 兼容模块；包内 LICENSE 与原文件逐字一致 |

检查只使用 CPU/mock 与临时历史目录，未启动真实 GPU 模型或硬件，浏览器预览服务已关闭。

## 交接

使用 `./start.sh`。本轮不修改 Git 托管名称或 remote，不搬移数据、权重和历史数据库。
仍处于 infra 阶段，不加入 Harness 或采集实现。

## 追加：远程访问与启动输出

用户通过 SSH 使用服务器，原回环监听无法直接使用服务器 IP。默认改为 IPv4 全接口监听，
启动时列出实际网卡地址与带随机密钥的完整链接。远程首页验证密钥后建立会话，
刷新使用 Cookie；页面随后清除地址栏密钥，保留 Host 校验和修改请求专用令牌。
`--host 127.0.0.1` 可恢复回环监听并使用 SSH 转发。

启动输出补充 Python、仓库/配置/历史路径、监听地址、活动策略数与各评测入口配置状态，
明确模型/仿真在任务提交后加载；启动失败和退出也有文字输出。

验证：`python3 -m unittest discover -s tests -p test_web.py -q` 16 项通过；
`python3 -m unittest discover -s tests -p test_start.py -q` 五项通过。
完整依赖环境 `policy/Pi_05/openpi/.venv/bin/python -m unittest discover -s tests -q` 66 项通过。
`python3 scripts/check_workspace.py`、`node --check web/static/app.js`、`git diff --check` 通过。
启动测试追加验证 Python/配置/历史/监听/就绪与退出输出，五项重跑通过。

真实服务器 IPv4 HTTP 直连检查通过：无密钥 403，带密钥首页、Cookie 刷新、catalog 和历史 API 均为 200。
Chromium 通过回环访问验证页面就绪、地址栏清除密钥、刷新与 API，无脚本错误；
该浏览器的直接 IPv4 请求受本机代理影响返回 407，因此浏览器结果不作为直连证据，直连由禁用代理的 HTTP 客户端验证。
用户电脑至服务器的实际网络连通性尚需用户打开链接确认。

已启动控制台供用户访问，监听 0.0.0.0:8765，运行日志在忽略目录 artifacts/web/server.log；
未启动 GPU 模型或仿真。访问密钥只放启动输出，不写入文档。

## 修正：直接打开 IP 地址

用户反馈带密钥的入口增加了不必要的操作。移除远程首页的 URL 密钥门槛，
启动日志和 README 改为普通 `http://<服务器IP>:8765/`。
首页自动建立会话，保留 API 会话、Host 和修改请求令牌检查；这些是防跨站请求措施，
不是用户登录。使用范围是可信内网；需要隔离时仍可使用回环监听和 SSH 转发。
已运行的用户进程不会热加载 Python 改动，需要用户自行 Ctrl+C 后重新执行 `./start.sh`。

验证：完整依赖环境 66 项测试通过；工作区检查、前端语法与 diff 检查通过。
临时全接口实例通过真实服务器 IPv4 验证普通首页与会话 API 均为 200，不传 URL 密钥；
该测试实例已关闭，未操作用户启动的控制台。
