# StockTracing - 智能股票追踪分析系统

> 本项目由本人使用 [OpenCode](https://github.com/anomalyco/opencode) 基于 DeepSeek V4 Pro 生成，并在后续开发中引入 GPT-5.5 模型参与代码优化与文档维护。本人负责项目大致结构设计与网页画面调整。

![Demo](images/GIF%2003-06-2026%2018-43-00.gif)

StockTracing 是一个本地运行的投资研究面板，用于追踪自选标的、查看技术指标、AI 分析、机构评级、公开机构持仓、交易记录、组合收益和多市场机会扫描。

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

- 渐进式加载自选标的，先绘制全部横幅，再填入缓存数据，随后后台并发补齐完整分析。
- 展示价格、走势、今日涨跌、5 分钟变化、D/W/M/Y 周期涨跌和技术信号。
- 展示综合技术建议、AI 推荐、PE、目标价和目标价空间。
- 支持股票和加密货币混合追踪。
- 搜索标的后可直接加入自选，也可进入详情页。
- 提供主要股指横条、市场时刻表、顶部开闭市状态、全屏模式和盘前/盘后扩展时段信息。

### 个股详情

- 查看标的概览、行情图表、关键估值指标、技术指标、机构评级、财报和资讯。
- 资讯默认保留上次加载结果，手动点击后再更新。
- AI 分析会综合近期资讯、周期涨跌、技术指标、评级、估值、营收和财务摘要。
- AI 输出会重点分析风险，并给出 `买入`、`观望` 或 `卖出` 信号。
- 初次进入详情页只读取已有 AI 缓存，不阻塞页面访问；手动刷新 AI 时会同步刷新资料和资讯。

### 技术扫描

- 批量分析自选标的的技术状态。
- 按买入、卖出、中性信号聚合展示扫描结果。
- 扫描结果包含 RSI、MACD、Bollinger、Stochastic、均线交叉、成交量、综合信号和 AI 信号。
- 点击“开始扫描”会为每只自选标的刷新一次 AI 分析。

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
│   ├── database/
│   │   └── models.py
│   ├── routers/
│   │   ├── pages.py
│   │   └── stock.py
│   ├── services/
│   │   ├── ai_context.py
│   │   ├── analyst.py
│   │   ├── cache_updater.py
│   │   ├── crypto.py
│   │   ├── discovery.py
│   │   ├── financials.py
│   │   ├── hunter.py
│   │   ├── institution_mapper.py
│   │   ├── institution_normalizer.py
│   │   ├── institutions.py
│   │   ├── llm_service.py
│   │   ├── news_service.py
│   │   ├── stock_data.py
│   │   ├── technical.py
│   │   └── trades.py
│   └── utils/
│       ├── proxy.py
│       └── watchlist.py
├── frontend/
│   └── templates/
│       ├── base.html
│       ├── hunt.html
│       ├── index.html
│       ├── institutions.html
│       ├── portfolio.html
│       ├── scan.html
│       ├── stock_detail.html
│       └── trades.html
└── data/
    ├── config.json
    ├── watchlist.json
    ├── trades.json
    ├── stocktracing.db
    ├── news_cache/
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

项目采用 FastAPI 单体后端 + Jinja2 模板前端。页面路由由 `backend/routers/pages.py` 管理，REST API 由 `backend/routers/stock.py` 管理，核心业务逻辑集中在 `backend/services/`。运行数据主要保存在 `data/`，其中 SQLite 用于行情、分析、财报、AI 和扫描历史缓存，JSON 文件用于配置、自选、交易记录和机构持仓专题数据。

详细架构、数据流和模块说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 免责声明

本系统仅供学习与研究目的使用。所有行情、评级、财报、机构持仓、AI 分析均可能存在延迟、错误或缺失，不构成投资建议。使用者应独立判断并自行承担投资风险。本系统未经过安全审计，不建议直接暴露到公网。

## 许可

[MIT License](LICENSE)
