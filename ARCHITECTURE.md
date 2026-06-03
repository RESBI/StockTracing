# StockTracing 架构与工作流程

## 系统架构总览

```
┌──────────────────────────────────────────────────────┐
│                     Frontend                         │
│  Jinja2 模板 + Tailwind CSS CDN + Chart.js           │
│  ├── index.html        仪表盘 (实时价格条/走势图)      │
│  ├── stock_detail.html 个股详情 (7 Tab)               │
│  ├── scan.html         技术扫描 (信号矩阵)            │
│  ├── hunt.html         狩猎 (多维评分)                │
│  ├── trades.html       交易记录 (CRUD)                │
│  └── portfolio.html    持仓分析 (饼图+收益曲线)       │
└───────────────────┬──────────────────────────────────┘
                    │ HTTP (JSON) / 1s 轮询
┌───────────────────▼──────────────────────────────────┐
│               FastAPI (backend/main.py)              │
│  ├── routers/stock.py    REST API (/api/*)           │
│  │   ├── /api/stock/*    股票 + 加密货币数据          │
│  │   ├── /api/watchlist  自选股管理                  │
│  │   ├── /api/config     系统配置                    │
│  │   ├── /api/hunt/*     狩猎扫描                    │
│  │   └── /api/trades/*   交易记录 + 持仓分析          │
│  └── routers/pages.py    页面路由                     │
│      ├── /               仪表盘                      │
│      ├── /stock/{sym}    个股详情                     │
│      ├── /scan           技术扫描                     │
│      ├── /hunt           狩猎                         │
│      ├── /trades         交易记录                     │
│      └── /portfolio      持仓分析                     │
└───────────────────┬──────────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────────┐
│                    Services                          │
│  ├── stock_data.py      股价行情、历史K线、Tick      │
│  ├── financials.py      财报(利润表/负债表/现金流)    │
│  ├── analyst.py         机构评级、近期评级、调级       │
│  ├── technical.py       技术指标(SMA/EMA/MACD/RSI等)  │
│  ├── llm_service.py     AI 分析总结(OpenAI兼容)       │
│  ├── news_service.py    资讯聚合(DuckDuckGo)          │
│  ├── cache_updater.py   后台缓存更新线程(daemon)      │
│  ├── hunter.py          狩猎评分引擎                  │
│  ├── discovery.py       交易所成分股发现              │
│  ├── crypto.py          加密货币数据(Binance+OKX)     │
│  └── trades.py          交易记录 + 持仓 + PnL曲线     │
└───────────────────┬──────────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────────┐
│                    Storage                           │
│  ├── SQLite (stocktracing.db)                        │
│  │   ├── stock_cache      股价/估值/机构目标价缓存    │
│  │   ├── financial_cache  财报数据缓存                │
│  │   ├── analysis_cache   技术指标/K线历史缓存        │
│  │   ├── llm_cache        AI分析历史记录              │
│  │   └── hunt_session     狩猎扫描历史               │
│  ├── JSON 文件                                       │
│  │   ├── watchlist.json       自选股列表              │
│  │   ├── trades.json          交易记录(明文可读)      │
│  │   ├── config.json          LLM+代理配置            │
│  │   ├── stock_universe.json  狩猎标的库              │
│  │   └── exchange_stocks.json 交易所成分股(24h缓存)   │
│  └── Memory (进程内)                                 │
│      ├── _price_history    {sym: [(ts,price),...]}    │
│      ├── _price_info_cache {sym: (ts,price)}          │
│      └── _ticks            {sym: {price,ts,ext,...}}  │
└──────────────────────────────────────────────────────┘
```

---

## 服务模块详解

### 1. `backend/services/stock_data.py` — 股票数据

| 函数 | 功能 | 数据流 |
|------|------|--------|
| `_resolve_asymbol(symbol)` | 6位纯数字自动补 `.SS`/`.SZ` | 600xxx → `600xxx.SS`，000xxx → `000xxx.SZ` |
| `get_stock_info(symbol, force_refresh)` | 获取股价、估值、机构目标价 | StockCache(缓存优先) → yfinance.info |
| `get_stock_history(symbol, period, interval)` | K线历史 | AnalysisCache(10min TTL) → yfinance.history |
| `get_tick(symbol)` | 实时价格快照(1s轮询用) | 内存 _ticks(120s) → _price_info_cache(15s) → yfinance |
| `search_stocks(query)` | 股票代码搜索 | yfinance.info 直接查询 |

**Auto-resolve 规则**：
- 6 位纯数字 → 6/9 开头试 `.SS` 再 `.SZ`，0/3 开头试 `.SZ` 再 `.SS`
- 已有后缀 → 直接使用
- 非数字 → 直接使用

### 2. `backend/services/financials.py` — 财报数据

| 函数 | 功能 |
|------|------|
| `get_financials(symbol, force_refresh)` | 年度+季度利润表、资产负债表、现金流量表 |
| `save_financials(symbol)` | 拉取并缓存财报 |

从 yfinance 获取 `ticker.financials`、`ticker.balance_sheet`、`ticker.cashflow`（年度），以及对应的 `quarterly_*` 版本。每条记录含 `period` 字段标识财报期间。

### 3. `backend/services/analyst.py` — 机构评级

| 函数 | 功能 | 缓存 |
|------|------|------|
| `get_analyst_info(symbol)` | 目标价、分析师评级、近期评级、调级记录 | StockCache(target字段) + AnalysisCache(ratings, 1h TTL) |
| `_fetch_ratings(sym)` | 拉取近期评级和调级记录 | AnalysisCache → yfinance.recommendations / upgrades_downgrades |

**返回字段**：`target_mean`, `target_high`, `target_low`, `target_median`, `number_of_analysts`, `recommendation`, `upside_percent`, `recent_ratings[]`, `upgrades_downgrades[]`

### 4. `backend/services/technical.py` — 技术指标

| 函数 | 功能 |
|------|------|
| `calculate_all_indicators(symbol)` | 计算全部技术指标 + 生成买卖信号 |
| `get_period_analysis(symbol)` | D/W/M/Y 四周期涨跌% + 信号 (B/S/N) |
| `_generate_signals(...)` | 综合各指标判断买入/卖出/中性 |

**计算的指标**：
- SMA (20/50/200)
- EMA (12/26/9)
- RSI (14)：超买>70，超卖<30
- MACD (12/26/9)：金叉/死叉 + 柱状图
- Bollinger Bands (20, 2σ)：突破上/下轨
- ATR (14)
- OBV
- Stochastic (14/3)：超买>80，超卖<20
- MA Cross：SMA20 穿 SMA50
- Volume Surge：当日量 > 20日均量×1.5

**D/W/M/Y 周期计算**（`get_period_analysis`）：

| 周期 | 数据窗口 | 趋势SMA | 信号判断 |
|------|---------|---------|---------|
| D | 20天 | SMA5 vs SMA10 | RSI + trend + volume → overall |
| W | 40天 | SMA10 vs SMA20 | 同上 |
| M | 80天 | SMA30 vs SMA60 | 同上 |
| Y | 252天 | SMA100 vs SMA200 | 同上 |

### 5. `backend/services/crypto.py` — 加密货币

| 函数 | 功能 |
|------|------|
| `get_crypto_info(symbol)` | 实时行情（价格/24h涨跌/成交量） |
| `get_crypto_history(symbol, period)` | OHLCV K线历史 |
| `get_crypto_tick(symbol)` | 轻量Tick + sparkline |
| `get_crypto_periods(symbol)` | D/W/M/Y 涨跌 + 信号 |
| `get_crypto_indicators(symbol)` | 完整技术指标（SMA/EMA/MACD/RSI/Bollinger/ATR/OBV/Stochastic） |

**数据源三层回退**：
1. ccxt Binance → `fetch_ticker()` / `fetch_ohlcv()`
2. ccxt OKX → 同上
3. Binance HTTP 原生 API → `/api/v3/ticker/24hr` + `/api/v3/klines`
4. OKX HTTP 原生 API → `/api/v5/market/ticker` + `/api/v5/market/candles`

**符号存储规则**：自选股中存为 `CRYPTO:BTC-USDT`，避免与股票代码冲突。显示时自动去除 `CRYPTO:` 前缀。

### 6. `backend/services/llm_service.py` — AI 分析

| 函数 | 功能 |
|------|------|
| `generate_summary(symbol, context)` | 调用 LLM 生成 800 字中文分析 |

**缓存流程**：对传入的 context 做 SHA256 hash，查 `LLMCache` 表。命中直接返回，未命中调 OpenAI API 后持久化。支持 `config.json` 中的自定义 `base_url`（可接 Ollama/DeepSeek 等）。

### 7. `backend/services/news_service.py` — 资讯聚合

| 函数 | 功能 |
|------|------|
| `get_stock_news(symbol, force_refresh)` | 聚合 yfinance 新闻 + DuckDuckGo 搜索 |
| `search_stock_insights(symbol)` | 分四个维度搜索（基本面/技术面/评级/风险） |

资讯缓存 2 小时（`data/news_cache/`），用户点击加载时触发。

### 8. `backend/services/cache_updater.py` — 后台缓存线程

**`CacheUpdater` 类**：
- 继承 `threading.Thread`，daemon 模式
- 1s 循环间隔
- 每批 2 只股票，只间休 0.5s，批间休 1.5s
- 更新自选股 + 狩猎队列中的所有股票
- 写入 `StockCache` (SQLite) + `_ticks` (内存)

**`_update_one(symbol)` 详细流程**：
```
跳过加密货币 (START_WITH CRYPTO: / 含 -USDT)
    │
    ▼
yfinance.Ticker → info dict
    │
    ▼
提取字段: price, name, sector, industry, market_cap, pe_ratio, eps,
         dividend_yield, beta, target_mean/high/low, number_of_analysts,
         recommendation, pre_market_price, post_market_price,
         regular_market_price, 52周高低, volume 等
    │
    ▼
写入 StockCache (SQLite) + _ticks (内存, 保留扩展数据)
```

### 9. `backend/services/hunter.py` — 狩猎评分引擎

| 函数 | 功能 |
|------|------|
| `get_markets()` | 返回所有可用大盘列表 |
| `get_sectors(market)` | 返回大盘下的所有领域（动态从 StockCache.sector 去重） |
| `get_symbols(market, sector)` | 返回领域对应的股票代码列表 |
| `score_stock(symbol)` | 单个股票四维评分 |
| `hunt(market, sector)` | 扫描所有标的并排序 |

**评分维度**（满分 100）：

| 维度 | 分值 | 评分规则 |
|------|------|---------|
| 价值 | 0-30 | PE<15 +10，PE<25 +5，PE偏高 -3；PEG<1 +5 |
| 机构 | 0-25 | 目标空间>30% +12，>15% +7，>5% +3；>5位分析师 +3；买入评级 +5 |
| 技术 | 0-25 | 每个买入信号 +2，每个卖出信号 -2（从 AnalysisCache 读） |
| 财务 | 0-20 | 有股息 +3；Beta<1.5 +2，Beta>2 -2 |

**综合评级**：≥60 → 推荐，40-59 → 关注，<40 → 一般

### 10. `backend/services/discovery.py` — 交易所成分股发现

| 函数 | 功能 |
|------|------|
| `discover_all_stocks(force_refresh)` | 多源获取成分股列表，缓存 24h |

**数据源**：
- 美股：Wikipedia S&P 500 + NASDAQ 100 + Russell 1000，回退内置列表
- A股：Wikipedia CSI 300 + CSI 500，回退内置列表
- 港股：Wikipedia HSI + HSCEI，回退内置列表
- 日股：Wikipedia Nikkei 225 + TOPIX，回退内置列表
- 加密货币：内置 30 个主流交易对

### 11. `backend/services/trades.py` — 交易记录与持仓分析

| 函数 | 功能 |
|------|------|
| `get_all_trades()` | 读取所有交易记录 + 注入当前价/浮盈 |
| `create_trade(data)` | 创建记录，自动判断 open/closed 状态 |
| `update_trade(id, data)` | 更新记录 |
| `delete_trade(id)` | 删除记录 |
| `get_trade_stats()` | 统计：总数/持仓/已实现盈亏/浮盈/胜率 |
| `get_portfolio(interval)` | 持仓分析：合并持仓、饼图数据、PnL曲线 |
| `_compute_pnl_curve(db, interval)` | 逐日/逐小时计算历史持仓浮盈曲线 |

**持仓合并规则**：同标的按加权均价合并数量和成本，收益曲线保持各笔分立计算。

**PnL曲线算法**：
1. 从 AnalysisCache 读取每只标的历史日线价格
2. 对每一天，遍历所有交易，判断是否处于持仓区间（`open_date ≤ day ≤ close_date`）
3. 取当日收盘价计算单笔浮盈，叠加得到总浮盈
4. 小时线：最近 5 天用 yfinance 60m 数据，更早用日线

---

## 数据库 Schema

### `stock_cache` — 股价估值缓存

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | VARCHAR(20) PK | 股票代码 |
| name | VARCHAR(200) | 公司名称 |
| sector | VARCHAR(100) | 行业板块 |
| current_price | FLOAT | 当前价 |
| previous_close | FLOAT | 前收盘价 |
| pe_ratio | FLOAT | 市盈率 |
| eps | FLOAT | 每股收益 |
| market_cap | FLOAT | 市值 |
| target_mean_price | FLOAT | 分析师目标均价 |
| target_high_price | FLOAT | 目标高价 |
| target_low_price | FLOAT | 目标低价 |
| number_of_analysts | INT | 覆盖分析师数量 |
| recommendation | VARCHAR(20) | 评级(buy/hold/sell) |
| dividend_yield | FLOAT | 股息率 |
| beta | FLOAT | 贝塔系数 |
| updated_at | DATETIME | 最后更新时间 |

### `analysis_cache` — 分析数据缓存

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | VARCHAR(20) | 股票代码 |
| analysis_type | VARCHAR(50) | 类型(history_1y_1d/full_indicators/analyst_ratings等) |
| data | JSON | 分析结果数据 |
| updated_at | DATETIME | 最后更新时间 |

### `llm_cache` — AI 分析记录

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | VARCHAR(20) | 股票代码 |
| prompt_hash | VARCHAR(64) | 请求内容的 SHA256 |
| content | TEXT | AI 分析文本 |
| created_at | DATETIME | 创建时间 |

### `hunt_session` — 狩猎历史

| 字段 | 类型 | 说明 |
|------|------|------|
| market | VARCHAR(50) | 大盘名称 |
| sector | VARCHAR(50) | 领域名称 |
| data | JSON | 完整扫描结果 |
| total | INT | 扫描标的数量 |
| created_at | DATETIME | 狩猎时间 |

---

## API 端点完整清单

### 股票数据
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stock/{symbol}` | 股票基本信息（缓存优先） |
| GET | `/api/stock/{symbol}?refresh=true` | 强制刷新 |
| GET | `/api/stock/{symbol}/history?period=6mo&interval=1d` | K线历史 |
| GET | `/api/stock/{symbol}/financials` | 财报数据 |
| GET | `/api/stock/{symbol}/analyst` | 机构评级 |
| GET | `/api/stock/{symbol}/technical` | 技术指标 |
| GET | `/api/stock/{symbol}/periods` | D/W/M/Y 周期分析 |
| GET | `/api/stock/{symbol}/tick` | 实时Tick（1s轮询） |
| GET | `/api/stock/{symbol}/news` | 新闻资讯（懒加载） |
| GET | `/api/stock/{symbol}/summary` | AI 分析总结 |
| GET | `/api/stock/{symbol}/full` | 完整分析聚合 |
| GET | `/api/stock/{symbol}/ai-history` | AI 分析历史 |

### 搜索与自选
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/search?q=AAPL` | 股票搜索 |
| GET | `/api/watchlist` | 获取自选列表 |
| POST | `/api/watchlist/{symbol}` | 添加自选（自动补全A股后缀/CRYPTO前缀） |
| DELETE | `/api/watchlist/{symbol}` | 移除自选 |

### 系统配置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 获取配置（API key 脱敏） |
| PUT | `/api/config` | 更新配置（llm + proxy） |

### 狩猎
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/hunt/markets` | 可用大盘列表 |
| GET | `/api/hunt/sectors?market=美股` | 领域列表 |
| POST | `/api/hunt/run?market=美股&sector=科技` | 执行扫描 |
| GET | `/api/hunt/history` | 历史记录列表 |
| GET | `/api/hunt/history/{id}` | 某次扫描详情 |

### 交易记录
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/trades` | 全部记录 + 当前价/浮盈 |
| GET | `/api/trades/stats` | 统计汇总 |
| GET | `/api/trades/portfolio?interval=1d` | 持仓分析（日线/小时） |
| POST | `/api/trades` | 创建记录 |
| PUT | `/api/trades/{id}` | 更新记录 |
| DELETE | `/api/trades/{id}` | 删除记录 |

---

## 核心工作流程

### 1. 后台缓存更新

```
应用启动 → get_updater().start()
                │
                ▼
         CacheUpdater daemon 线程
                │
     ┌──────────▼──────────┐
     │ 1s 间隔循环          │
     │  ├─ load_watchlist() │
     │  ├─ 合并 _ticks 队列  │
     │  ├─ 去重              │
     │  ├─ 每批 2 只          │
     │  ├─ _update_one()     │ → yfinance.info → StockCache + _ticks
     │  ├─ 只间休 0.5s       │
     │  └─ 批间休 1.5s       │
     └─────────────────────┘
```

### 2. 页面加载 — 仪表盘

```
浏览器 GET /
    │
    ▼
pages.py → index.html (Jinja2 渲染)
    │
    ▼
loadDashboard() [JS]
    ├── GET /api/watchlist → 自选列表
    ├── GET /api/stock/{sym}/full (并发 × N)
    │     ├── _is_crypto? → crypto 分支 或 股票分支
    │     ├── get_stock_info → StockCache
    │     ├── get_stock_history → AnalysisCache
    │     ├── get_analyst_info → StockCache + AnalysisCache
    │     ├── calculate_all_indicators → AnalysisCache
    │     ├── get_period_analysis → 1年历史 → 计算
    │     └── generate_summary → LLMCache
    │
    ▼
makeBar() → 生成 HTML 卡片
    │
    ▼
startAutoRefresh() [JS]
    └── setInterval(refreshPrices, 1000)
          └── GET /api/stock/{sym}/tick → 更新价格/5m/今日/盘前盘后
```

### 3. 1s 价格轮询路径

```
refreshPrices() [JS, 每1s]
    │
    ▼
for each symbol in watchlist:
    GET /api/stock/{sym}/tick
        │
        ▼
    _is_crypto? → get_crypto_tick → Binance/OKX HTTP
        │
        ▼ (股票)
    get_tick()
        ├── get_updater().get_tick() → 内存 _ticks (120s TTL)
        │   命中 → 直接返回 price + pre/post market + prev_close
        │
        └── 未命中
              ├── _price_info_cache (15s TTL) → 命中返回
              └── yfinance.info → 存入 _price_info_cache
        │
        ▼
    5min 涨跌计算:
        _price_history 种子化 (yfinance 5m candle 首次)
        每次记录 (timestamp, price)
        找距今 ~300s 最近价格 → change_5m
    
    sparkline: _price_history 最近 40 个点取出
    
    返回: {price, change_5m, sparkline, pre_market, post_market, ...}
        │
        ▼
    updatePriceCell()  → Flash + slide 动画
    update 5m / today / extended hours 各 cell
```

### 4. 狩猎扫描流程

```
用户选择: 美股 + 科技
    │
    ▼
POST /api/hunt/run?market=美股&sector=科技
    │
    ▼
discover_all_stocks() → 获取美股全部标的 (~444只)
    │
    ▼
queue_symbols() → 加入后台缓存更新队列
    │
    ▼
遍历标的，逐只 score_stock():
    ├── 读 StockCache: PE, EPS, target_mean, beta, dividend
    ├── 读 AnalysisCache: 技术信号(buy/sell count)
    └── 四维评分 → 返回 {total_score, scores:{value, analyst, technical, financial}}
    │
    ▼
按 total_score 降序排列
    │
    ▼
写入 hunt_session 表 (保留历史)
    │
    ▼
返回 JSON → 前端 renderHuntResults()
    卡片布局: 排名 | 代码 | 价格 | PE/目标/信号 | EPS/股息/Beta/分析师 | 评分bar | 总分 | 标签
```

### 5. 技术指标计算完整路径

```
GET /api/stock/{symbol}/technical
    │
    ▼
calculate_all_indicators(symbol)
    │
    ▼
Check AnalysisCache (type="full_indicators", 10min TTL)
    │ 命中 → 直接返回
    │
    ▼ 未命中
_get_hist_data(symbol) → yfinance.history(period="1y")
    │
    ▼
计算:
  SMA(20/50/200), EMA(12/26/9)
  MACD line + signal + histogram
  RSI(14)
  Bollinger(20, 2σ)
  ATR(14), OBV
  Stochastic(14,3)
  │
  ▼
_generate_signals() :
  遍历各指标 → buy/sell/neutral 判断
  综合评分 = buy_count vs sell_count
  │
  ▼
存入 AnalysisCache → 返回
```

### 6. 加密货币数据获取路径

```
GET /api/stock/CRYPTO:BTC-USDT
    │
    ▼
_is_crypto("CRYPTO:BTC-USDT") → True
    │
    ▼
_crypto_sym → "BTC-USDT"
    │
    ▼
get_crypto_info("BTC-USDT")
    ├── _get_ccxt() → ccxt.binance (5s timeout)
    │   成功 → fetch_ticker → 返回
    │   失败 ↓
    ├── _get_ccxt() → ccxt.okx (5s timeout)
    │   成功 → fetch_ticker → 返回
    │   失败 ↓
    ├── _fetch_ticker_binance() → HTTP GET api.binance.com (3s)
    │   成功 → 返回
    │   失败 ↓
    └── _fetch_ticker_okx() → HTTP GET www.okx.com (3s)
         成功 → 返回
         失败 → 返回 minimal info (symbol + name, price=None)
```

---

## 前端组件交互细节

### 仪表盘 (`index.html`)

**核心 JS 函数**：
- `makeBar(sym, data)` — 生成单行卡片 HTML，含价格动画 + sparkline SVG
- `priceHTML(sym, curPrice, prevPrice, prevClose, flash, crypto)` — 生成价格单元格（部分数字滑入动画）
- `diffPrice(oldStr, newStr)` — 逐字符比对，返回 `{prefix, changed, suffix}`
- `updatePriceCell(cell, newPrice)` — 更新价格 DOM + 滑入动画
- `refreshPrices()` — 1s 轮询主函数，更新价格/5m/今日/盘前盘后/sparkline
- `loadDashboard()` — 初始化加载所有自选股数据
- `updateMarketBar()` — 北京时间时钟 + 五地股市状态 + 24h 时间条

**价格动画效果**：
- 价格变化 → `.price-flash-up`/`.price-flash-down` 背景闪烁 (0.8s)
- 新数字 → `.price-slide-in` 从上下方滑入 (0.35s)
- 仅变化部分的字符滑入，不变部分保持静态

**24h 时刻表**：
- 每小时 12 根短线 = 5 分钟间隔
- 彩色条带表示开市时段（A股红/港股橙/日股紫/欧股蓝/美股绿），重叠时上下堆叠
- 灰色蒙板从左推进覆盖已过时间
- 白色竖线指示当前北京时间
- 鼠标 hover 色带 → 显示开盘时间 tooltip + 盘前/盘后延展段

### 个股详情 (`stock_detail.html`)

**7个Tab**：
1. **概览** — 价格/涨跌/关键指标/综合建议
2. **图表** — Chart.js 价格走势 (1月/3月/6月/1年)
3. **技术指标** — 买卖信号卡片 + RSI/MACD/Bollinger 快照
4. **机构评级** — 3×2 目标价网格 + 评级调级 + 近期评级
5. **财报** — 利润表/负债表/现金流 (可折叠 details)
6. **资讯** — 点击加载，DuckDuckGo + yfinance 新闻
7. **AI分析** — 最新分析 + 历史记录时间线，可手动刷新

### 交易记录 (`trades.html`)

- 5 格统计面板
- 交易记录列表（做多绿/做空红标签 → 日期 → 盈亏百分比）
- 模态表单（方向/数量/开仓时间/开仓价/平仓时间/平仓价/备注）

### 持仓分析 (`portfolio.html`)

- 左侧竖排：持仓成本+总值 / 总浮盈+百分比 / 标的总数
- 右侧并排：标的占比饼图 + 领域占比饼图
- 下方：收益曲线（日线/小时切换）
- 持仓明细卡片（浅色底）：代码 | 股数 | 成本(总额/单价) | 现值(总额/单价) | 涨跌%

---

## 配置说明

### `data/config.json`

```json
{
    "llm": {
        "api_key": "sk-xxx",          // API密钥（OpenAI/DeepSeek/Ollama）
        "model": "gpt-4o-mini",       // 模型名称
        "base_url": "https://api.openai.com/v1"  // API地址
    },
    "proxy": {
        "enabled": false,             // 是否启用代理
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }
}
```

代理启用后通过 `setup_proxy()` 注入到 yfinance Session 和 OpenAI httpx.Client。`PUT /api/config` 可在线修改即时生效。

---

## 错误处理

- **Yahoo Finance 限流**：`@retry_on_rate_limit` 装饰器，指数退避 3 次（2s→4s→8s + 随机抖动）
- **NaN/Inf 清洗**：`SafeJSONResponse` 递归替换 NaN/Inf → null
- **加密货币网络不可达**：四层回退后返回 minimal info（symbol + name, price=None）
- **数据库异常**：所有 DB 操作带 `try/finally`，确保 Session 关闭
- **前端容错**：所有 API 调用带 `try/catch`，失败时显示 "—" 或 "加载失败"

---

## 安全说明

- `config.json` 含 API Key，已加入 `.gitignore` 不纳入版本控制
- `trades.json` 含交易记录明文，已加入 `.gitignore`
- 系统无用户认证，建议仅在内网或本地使用
- 部署公网需自行添加认证层和 HTTPS
