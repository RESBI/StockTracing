# StockTracing - 智能股票追踪分析系统

> 本项目由本人使用 [OpenCode](https://github.com/anomalyco/opencode) 基于 DeepSeek V4 Pro 生成，并在后续开发中引入 GPT-5.5 模型参与代码优化与文档维护。本人负责项目大致结构设计与网页画面调整。

![Demo](images/GIF%2003-06-2026%2018-43-00.gif)

StockTracing 是一个本地运行的投资研究面板，集成自选股实时追踪、技术指标、AI 分析、机构评级、SEC 13F 机构持仓、交易记录、持仓收益和多市场狩猎扫描。

## 快速开始

```bash
pip install -r requirements.txt
python run.py
```

访问：`http://localhost:8000`

## 配置

编辑 `data/config.json`。

LLM 配置：

```json
{
    "llm": {
        "api_key": "sk-xxx",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1"
    }
}
```

代理配置：

```json
{
    "proxy": {
        "enabled": true,
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }
}
```

如果 `https` 为空，系统会复用 `http` 代理。

## 功能概览

### 仪表盘

- 集中展示自选标的的价格、涨跌、短线变化、周期趋势和综合信号。
- 支持搜索、添加、删除自选标的。
- 支持股票和加密货币混合追踪。
- 提供全屏看板、市场时刻表和盘前/盘后信息。

### 个股详情

- 查看标的概览、行情走势、关键估值指标和综合建议。
- 支持多周期图表、完整技术指标、机构评级、财报和资讯。
- 配置 AI 后可生成中文分析总结，并保留历史分析记录。

### 技术扫描

- 批量分析自选标的的技术状态。
- 按买入、卖出、中性信号聚合展示扫描结果。
- 用于快速发现技术面偏强或偏弱的标的。

### 狩猎

- 面向不同市场和领域筛选潜在机会。
- 从价值、机构、技术和财务多个维度给出综合评分。
- 支持保存和回看历史扫描结果。

### 机构持仓

- 跟踪主要机构的公开持仓变化。
- 横幅展示机构投资规模、前十资产和领域分布。
- 展开机构后查看完整持仓明细、持仓金额、权重和增减持趋势。
- 支持手动刷新、进度展示和历史记录查看。

### 交易记录与持仓分析

- 记录交易方向、数量、开平仓价格和备注。
- 自动统计盈亏、胜率和当前持仓状态。
- 提供持仓占比、领域分布和收益曲线。

### 加密货币

- 支持 BTC、ETH、SOL 等主流交易对。
- 支持实时行情、历史走势、周期涨跌和技术指标。
- 可以与股票一起加入自选列表统一追踪。

## 数据源

| 模块 | 数据源 |
|---|---|
| 股票行情 | yfinance / Yahoo Finance |
| 财报 | yfinance |
| 机构评级 | yfinance |
| 加密货币 | ccxt Binance / OKX / Binance HTTP / OKX HTTP |
| 资讯 | Yahoo Finance / DuckDuckGo |
| AI 分析 | OpenAI 兼容 API |
| 机构持仓 | SEC EDGAR 13F |
| CUSIP 映射 | OpenFIGI / 本地缓存 |
| ticker directory | SEC company tickers / NASDAQ symbol directory |

## 目录结构

```text
StockTracing/
├── run.py
├── requirements.txt
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database/models.py
│   ├── routers/pages.py
│   ├── routers/stock.py
│   ├── services/stock_data.py
│   ├── services/financials.py
│   ├── services/analyst.py
│   ├── services/technical.py
│   ├── services/crypto.py
│   ├── services/llm_service.py
│   ├── services/news_service.py
│   ├── services/cache_updater.py
│   ├── services/discovery.py
│   ├── services/hunter.py
│   ├── services/trades.py
│   ├── services/institutions.py
│   ├── services/institution_mapper.py
│   └── services/institution_normalizer.py
├── frontend/templates/
│   ├── base.html
│   ├── index.html
│   ├── stock_detail.html
│   ├── scan.html
│   ├── hunt.html
│   ├── institutions.html
│   ├── trades.html
│   └── portfolio.html
└── data/
    ├── config.json
    ├── watchlist.json
    ├── trades.json
    ├── stocktracing.db
    ├── institution_holdings.json
    ├── institution_visible_cache.json
    ├── institution_holdings_history/
    ├── cusip_mapping_cache.json
    ├── sec_ticker_cache.json
    ├── sec_ticker_exchange_cache.json
    ├── nasdaq_directory_cache.json
    └── ticker_sector_cache.json
```

## 项目实现

项目采用 FastAPI 单体后端 + Jinja2 模板前端的结构，核心业务逻辑集中在 `backend/services/`，页面和 API 路由分别由 `backend/routers/pages.py` 与 `backend/routers/stock.py` 管理。运行数据主要保存在 `data/`，其中 SQLite 用于行情、分析和历史缓存，JSON 文件用于配置、自选、交易记录和部分专题数据。

详细架构、数据流和模块说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 免责声明

本系统仅供学习与研究目的使用。所有行情、评级、财报、机构持仓、AI 分析均可能存在延迟、错误或缺失，不构成投资建议。使用者应独立判断并自行承担投资风险。本系统未经过安全审计，不建议直接暴露到公网。

## 许可

[MIT License](LICENSE)
