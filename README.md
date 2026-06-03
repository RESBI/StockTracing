# StockTracing — 智能股票追踪分析系统

> 本项目由本人使用 [OpenCode](https://github.com/anomalyco/opencode) 基于 DeepSeek V4 Pro 生成。本人仅负责项目大致结构设计与网页画面调整。

![Demo](images/GIF%2003-06-2026%2018-43-00.gif)

实时追踪股票行情，技术指标计算，AI 分析总结，机构评级整合，交易记录管理，多市场狩猎扫描。

## 快速开始

```bash
pip install -r requirements.txt
python run.py
```

访问 http://localhost:8000

## LLM 配置

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

## 代理配置

```json
{
    "proxy": {
        "enabled": true,
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }
}
```

保存后即时生效，无需重启。

## 功能概览

| 模块 | 说明 |
|------|------|
| 仪表盘 | 自选股实时价格、走势图、D/W/M/Y/5m涨跌、技术信号、盘前盘后、PE/目标/空间 |
| 个股详情 | 概览/图表/技术指标/机构评级/财报/资讯/AI分析 7 Tab |
| 技术扫描 | 批量扫描自选股买卖信号矩阵表 |
| 狩猎 | 按大盘+领域扫描交易所成分股，四维评分推荐低估机会，支持美股/A股/港股/日股/加密货币 |
| 交易记录 | 做多/做空开平仓记录，盈亏统计、浮盈浮亏 |
| 持仓分析 | 饼图占比、收益曲线、持仓明细卡片 |
| 加密货币 | 支持 BTC/ETH 等 30+ 主流币种，Binance+OKX 双源 |
| 时刻表 | 24h 刻度条，五地股市开闭盘状态，北京时间 |

## 目录结构

```
StockTracing/
├── run.py                         # 启动入口
├── requirements.txt
├── data/                          # 运行时数据
│   ├── config.json                # LLM + 代理配置
│   ├── watchlist.json             # 自选股列表
│   ├── trades.json                # 交易记录
│   ├── stocktracing.db            # SQLite 缓存
│   ├── stock_universe.json        # 狩猎标的库
│   └── exchange_stocks.json       # 交易所成分股缓存
├── backend/                       # 后端
│   ├── main.py                    # FastAPI 应用入口
│   ├── config.py                  # 配置加载
│   ├── database/models.py         # SQLAlchemy 模型
│   ├── services/                  # 核心服务
│   │   ├── stock_data.py          # 股价/行情
│   │   ├── financials.py          # 财报数据
│   │   ├── analyst.py             # 机构评级
│   │   ├── technical.py           # 技术指标 + 信号
│   │   ├── llm_service.py         # AI 分析
│   │   ├── news_service.py        # 资讯搜索
│   │   ├── cache_updater.py       # 后台缓存更新
│   │   ├── hunter.py              # 狩猎评分引擎
│   │   ├── discovery.py           # 交易所成分股发现
│   │   ├── crypto.py              # 加密货币数据
│   │   └── trades.py              # 交易记录管理
│   ├── routers/                   # API 路由
│   │   ├── stock.py               # REST API 端点
│   │   └── pages.py               # 页面路由
│   └── utils/                     # 工具
│       ├── watchlist.py           # 自选股管理
│       └── proxy.py               # 代理设置
└── frontend/                      # 前端 (Jinja2 + Tailwind CSS)
    ├── static/                    # 静态资源
    └── templates/                 # 页面模板
        ├── base.html              # 基模板
        ├── index.html             # 仪表盘
        ├── stock_detail.html      # 个股详情
        ├── scan.html              # 技术扫描
        ├── hunt.html              # 狩猎
        ├── trades.html            # 交易记录
        └── portfolio.html         # 持仓分析
```

## 技术栈

- **后端**: Python / FastAPI / SQLAlchemy / SQLite
- **数据源**: yfinance (Yahoo Finance) + Binance/OKX 公开 API
- **前端**: Jinja2 模板 + Tailwind CSS CDN + Chart.js
- **AI**: OpenAI 兼容 API
- **资讯**: DuckDuckGo 搜索

[详细架构文档 → ARCHITECTURE.md](ARCHITECTURE.md)

## 免责声明

本系统仅供学习与研究目的使用。

- 所有股票数据来源于 Yahoo Finance，AI 分析结论仅供参考，不构成任何投资建议。使用者应独立判断并承担投资风险。
- 本系统未经过安全审计，部署到公网可能导致服务器被攻击、数据泄露等安全风险。部署者应自行承担由此引发的系统损坏、数据丢失及其他损失。
- 作者不对因使用或部署本系统产生的任何投资损失、安全事件、系统故障或数据损坏负责。

## 许可

[MIT License](LICENSE)
