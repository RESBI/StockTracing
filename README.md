# StockTracing — 智能股票追踪分析系统

> 本项目由本人使用 [OpenCode](https://github.com/anomalyco/opencode) 基于 DeepSeek V4 Pro 生成。本人仅负责项目大致结构设计与网页画面调整。

![Demo](images/GIF%2003-06-2026%2018-43-00.gif)

实时追踪股票行情与加密货币，技术指标计算，AI 分析总结，机构评级整合，交易记录管理，持仓盈亏分析，多市场狩猎扫描。

---

## 快速开始

```bash
pip install -r requirements.txt
python run.py
# 访问 http://localhost:8000
```

### LLM 配置（可选）

编辑 `data/config.json`：

```json
{
    "llm": {
        "api_key": "sk-xxx",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1"
    }
}
```

支持 OpenAI / DeepSeek / Ollama 等兼容 API。

### 代理配置（可选）

```json
{
    "proxy": {
        "enabled": true,
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }
}
```

保存后即时生效，支持 `PUT /api/config` 在线修改。

---

## 功能模块

### 📊 仪表盘

- 自选股/加密货币实时价格横条
- **走势图**：当日 5 分钟迷你走势（SVG，涨绿跌红）
- **价格动画**：变化时背景闪烁 + 新数字部分字符滑入
- **多周期**：今日 / 5m / D / W / M / Y 涨跌 + B/S/N 信号
- **盘前盘后**：非交易时段显示盘前/盘后价格
- **指标**：PE / 目标价 / 上涨空间
- **1 秒轮询**：后台缓存防限流
- **自适应宽度**：宽屏撑满，窄屏横向滚动

### 📈 个股详情（7 Tab）

| Tab | 内容 |
|-----|------|
| 概览 | 价格/涨跌/市值/PE/EPS/Beta + 综合建议 |
| 图表 | Chart.js（1月/3月/6月/1年） |
| 技术指标 | SMA/EMA/MACD/RSI/Bollinger/ATR/OBV/Stochastic + 买卖信号 |
| 机构评级 | 3×2 目标价网格 + 调级 + 近期评级 |
| 财报 | 利润表/负债表/现金流（年度+季度） |
| 资讯 | 点击加载，yfinance+DuckDuckGo |
| AI 分析 | 最新分析 + 历史记录，可手动刷新 |

### 🔎 技术扫描

- 自选股信号矩阵表：代码/价格/涨跌/PE/RSI/MACD/Bollinger/Stoch/MA交叉/量/综合
- 偏多→偏空排序，顶部统计汇总

### 🎯 狩猎

按大盘+领域扫描交易所成分股，四维评分推荐。

| 维度 | 分值 | 评分规则 |
|------|------|---------|
| 价值 | 30 | PE<15 +10, PEG<1 +5 |
| 机构 | 25 | 目标空间>30% +12, 买入评级 +5 |
| 技术 | 25 | 买入信号+2/个, 卖出-2/个 |
| 财务 | 20 | 股息+3, 低Beta+2 |

- 数据源：Wikipedia 实时成分股（S&P 500 / CSI 300 / 恒生 / 日经）
- 结果写入数据库，可回查历史

### 📒 交易记录

- 做多/做空开平仓，开/平时间与价格（可留空）
- 自动盈亏计算（金额 + 百分比）
- 统计：总记录/持仓中/已实现/浮盈/胜率
- 明文存储 `data/trades.json`

### 📈 持仓分析

- 统计：持仓成本 / 总值 / 总浮盈（含%）/ 标的总数
- 饼图（标的占比 + 领域占比，右侧 legend 带百分比）
- 收益曲线（日线/小时），基于真实历史价格
- 持仓明细卡片：代码/股数/成本/现值/涨跌%

### ₿ 加密货币

- 30+ USDT 交易对，四层回退（ccxt Binance→OKX→HTTP Binance→HTTP OKX）
- 实时价格/K线/技术指标/周期分析/走势图
- 存储为 `CRYPTO:BTC-USDT` 避免与股票冲突

### 🕐 时刻表

- 北京时间时钟 + 五地股市开闭盘状态
- 24h 刻度条（每小时 12 根 5 分钟短线）
- 彩色条带标注开市时段，重叠时分层堆叠
- 灰色蒙板覆盖已过时间，白色竖线当前时刻

---

## 目录结构

```
StockTracing/
├── run.py
├── requirements.txt
├── README.md / ARCHITECTURE.md / LICENSE
├── data/                          # 运行时数据
│   ├── config.json                # LLM + 代理
│   ├── watchlist.json             # 自选股
│   ├── trades.json                # 交易记录
│   ├── stocktracing.db            # SQLite
│   └── stock_universe.json        # 狩猎标的库
├── backend/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 配置 + 重试装饰器
│   ├── database/models.py         # 5 张表
│   ├── services/                  # 10 个服务模块
│   ├── routers/                   # API + 页面路由
│   └── utils/                     # watchlist + proxy
├── frontend/templates/            # 7 个页面模板
└── images/                        # 演示 GIF
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python / FastAPI / SQLAlchemy / SQLite |
| 股票数据 | yfinance |
| 加密货币 | ccxt + Binance/OKX HTTP API |
| 前端 | Jinja2 + Tailwind CSS CDN + Chart.js |
| AI | OpenAI 兼容 API |
| 资讯 | DuckDuckGo |

---

## 数据缓存

| 数据 | 存储 | 更新 |
|------|------|------|
| 股价/估值 | StockCache (SQLite) | 后台线程 1s 循环 |
| K线/指标 | AnalysisCache (SQLite) | 10min TTL |
| AI 分析 | LLMCache (SQLite) | 永久 |
| Tick 价格 | 内存 dict | 120s TTL |
| 成分股 | 文件缓存 | 24h |

---

## 支持市场

| 市场 | 代码示例 | 成分股 |
|------|---------|--------|
| 美股 | AAPL, TSLA | S&P 500 + NASDAQ 100 + Russell 1000 |
| A股 | 600519.SS | CSI 300 + CSI 500（纯数字自动补后缀） |
| 港股 | 0700.HK | 恒生 + HSCEI |
| 日股 | 7203.T | 日经 225 + TOPIX |
| 加密货币 | BTC, ETH | Binance/OKX 30+ 交易对 |

---

## 免责声明

本系统仅供学习与研究目的使用。

- 所有数据来源于第三方公开 API，AI 分析仅供参考，不构成投资建议
- 本系统未经过安全审计，部署公网需自行承担安全风险
- 作者不对任何投资损失、安全事件或数据损坏负责

---

## 许可

[MIT License](LICENSE)

[详细架构文档 → ARCHITECTURE.md](ARCHITECTURE.md)
