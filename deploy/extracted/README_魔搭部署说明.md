# QuantMonitorV6 · 魔搭服务器部署说明（脱离 GitHub Actions 版）

> 部署目标：把「收盘后扫描 → LLM 研判 → PushPlus 微信推送」整套云端链路搬到魔搭服务器，用 crontab 定时驱动，**不再依赖 GitHub Actions**（当前 GitHub 账户级拒启动已不影响本方案）。

## 目录结构（解压后）

```
v6server/
├── scheduler.sh        # 主调度：按北京时间判定槽位并执行（crontab 每10分钟调用）
├── crontab.txt         # 待粘贴到 crontab -e 的配置（含说明）
├── tools/
│   ├── cloud_daily_review.py   # 主入口（唯一需要直接执行的文件）
│   ├── zhu_force_scan.py       # 主力痕迹扫描器（zscan 槽位调用）
│   ├── cloud_llm_gateway.py    # LLM 网关（ModelScope）
│   ├── env.sh                  # ★ 密钥模板（必须修改后使用）
│   └── ...（运行必需 json 资源 + data/ 状态文件）
└── logs/               # 运行时自动生成（scheduler.sh 已建）
```

## 四步部署

### 第 1 步：上传并解压
```bash
# 把 v6server.zip 传到服务器（scp / 宝塔 / 魔搭控制台上传均可），然后：
mkdir -p /opt/v6
unzip v6server.zip -d /opt/v6
cd /opt/v6
chmod +x scheduler.sh
# 确保时区是北京时间
timedatectl set-timezone Asia/Shanghai
```

### 第 2 步：配置密钥
```bash
vi /opt/v6/tools/env.sh   # 填入你的 PUSHPLUS_TOKEN 和 MODELSCOPE_API_KEY
chmod 600 /opt/v6/tools/env.sh
```
> 密钥获取：PushPlus 官网「一对一推送」token；魔搭「个人中心 → 访问令牌」（ms-xxx）。与你现在 GitHub Secrets 里的相同即可（cloud_daily_review.py 只认这两个环境变量，读法完全一致）。

### 第 3 步：验证单次推送（先手动，确认能收到微信）
```bash
cd /opt/v6
# 方式A：强制推送盘前速递（会真实推一张卡到微信）
python3 tools/cloud_daily_review.py --time pre --force pre
# 方式B：演示全部卡（会连续推多张演示卡，适合确认全链路）
python3 tools/cloud_daily_review.py --time demo-all --force demo-all
```
看到微信收到卡片 → 链路 OK；没收到 → 看 logs/push_日期.log 的报错（多为密钥填错或网络）。

### 第 4 步：安装定时任务
```bash
crontab -e    # 粘贴 crontab.txt 内容（路径按你的实际目录改）
crontab -l    # 确认已安装
```
生效后即按原 GitHub 时刻表自动推送：
- 08:20 板块预警 / 08:30 盘前 / 09:20 竞价 / 盘中 hourly / 11:30 午间 / 12:00 news2h /
- 15:00 收盘复盘 / 15:20 主力成本锚 / 15:30 复盘 / 15:35 简报 / 21:38 外盘 / 22:50 晚间 / 周日 20:00 评估

## 与原 GitHub Actions 的差异（已适配）

| 项 | GitHub Actions 版 | 魔搭服务器版 |
|---|---|---|
| 时钟 | 用 UTC 时刻 case 判定 | scheduler.sh 直接用北京时间（同一张表） |
| 密钥 | GitHub Secrets | tools/env.sh（chmod 600） |
| 持久化状态 | git commit/push 到仓库 | 本地 data/ 文件（同目录，效果一致） |
| 兜底触发 | 外部每 10 分钟 dispatch | crontab */10 |
| 去重 | slot_done.json | 同（代码内置，无改动） |

**已知无害提示**：cloud_daily_review.py 内部有一段 git 持久化 subprocess（原 GitHub 环境用）；服务器上没有 git 仓库时它静默失败（check=False），不影响推送，可忽略。如介意可后续注释，但**当前无需改代码**。

## 回滚
- 服务器版与 GitHub 版并行不冲突：GitHub 恢复后可随时停 crontab（`crontab -r`）切回原链路；本部署保留不动即可。
- 卸载：`crontab -r` + 删除 /opt/v6。

## 核对清单
- [ ] 服务器有 python3（无第三方依赖，标准库即可）
- [ ] env.sh 两个密钥已填且 chmod 600
- [ ] 手动跑 pre 已收到微信卡
- [ ] crontab -l 可见 4 组定时行
