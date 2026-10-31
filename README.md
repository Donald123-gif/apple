# Apple 全系机型深度对比中心 — 方案 C (自动爬虫 + 云端同步套件)

本套件包含完整的 **前端对比网站 (`index.html`)**、**外置实时数据源 (`data/models.json`)**、**Apple 官网自动抓取脚本 (`apple_scraper.py`)** 以及 **GitHub Actions 每日定时任务 (`.github/workflows/update_models.yml`)**。

---

## 目录结构

```text
apple_realtime_sync_suite/
├── index.html                        # 主网站（支持自动拉取 ./data/models.json，断网时自动回退内置快照）
├── data/
│   └── models.json                   # 20 款 Apple 机型的全量规格、包装清单及 RMB/HKD/USD 三币种价格
├── apple_scraper.py                  # Python 爬虫：抓取 Apple 官网最新价格/重量与实时汇率并更新 models.json
├── requirements.txt                  # Python 依赖清单 (requests, beautifulsoup4)
└── .github/
    └── workflows/
        └── update_models.yml         # GitHub Actions 配置文件（每日自动运行爬虫并推送更新）
```

---

## 方式一：在你自己的电脑上运行与实时更新

1. **安装 Python 依赖**（只需执行一次）：
   ```bash
   pip install -r requirements.txt
   ```
2. **运行爬虫脚本抓取最新数据**：
   ```bash
   python3 apple_scraper.py --input data/models.json --output data/models.json
   ```
3. **启动本地轻量静态服务器打开网站**：
   ```bash
   python3 -m http.server 8080
   ```
   然后在浏览器访问 `http://localhost:8080`，网页会自动读取 `data/models.json`。
   *(注：如果你直接双击 `index.html`，也可切到网站第 5 页「实时同步 (方案C)」，点击 **上传本地 models.json** 手动载入刚生成的 JSON 文件)*。

---

## 方式二：部署到 GitHub 开启全自动云端定时更新（零服务器成本）

1. 在 GitHub 新建一个公开仓库，将本文件夹内的所有文件上传上去。
2. 进入仓库 **Settings → Pages**，将 Source 设置为 `Deploy from a branch` (`main` 分支 `/root` 目录)。
3. GitHub Actions 会每天自动运行 `.github/workflows/update_models.yml`，访问 Apple 官网抓取最新价格和实时汇率并更新 `data/models.json`，你的在线网站无需人工维护即可永久保持最新！
