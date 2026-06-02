# StockTracing — 智能股票追踪分析系统

> 本项目由本人使用 [OpenCode](https://github.com/anomalyco/opencode) 基于 DeepSeek V4 Pro 生成。本人仅负责项目大致结构设计与网页画面调整。

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
| 仪表盘 | 自选股实时价格、D/W/M/Y/5m 涨跌、技术信号、PE/市值/目标价 |
| 个股详情 | 概览/图表/技术指标/机构评级/财报/资讯/AI分析 7 个 Tab |
| 技术扫描 | 批量扫描自选股买卖信号矩阵表 |
| 狩猎 | 按大盘+领域扫描所有标的，四维评分推荐低估机会 |
| 交易记录 | 做多/做空开平仓记录，盈亏统计、浮盈浮亏 |
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
        └── trades.html            # 交易记录
```

## 技术栈

- **后端**: Python / FastAPI / SQLAlchemy / SQLite
- **数据源**: yfinance (Yahoo Finance)
- **前端**: Jinja2 模板 + Tailwind CSS CDN + Chart.js
- **AI**: OpenAI 兼容 API
- **资讯**: DuckDuckGo 搜索

[详细架构文档 → ARCHITECTURE.md](ARCHITECTURE.md)
