# StockTracing 架构与工作流程

## 系统架构

```
┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│  Jinja2 模板 + Tailwind CSS + Chart.js           │
│  ├── index.html      仪表盘 (实时价格条)          │
│  ├── stock_detail    个股详情 (7 Tab)             │
│  ├── scan.html       技术扫描 (信号矩阵)          │
│  ├── hunt.html       狩猎 (多维评分)              │
│  └── trades.html     交易记录 (盈亏统计)          │
└──────────────────┬──────────────────────────────┘
                   │ HTTP/SSE
┌──────────────────▼──────────────────────────────┐
│              FastAPI (backend/main.py)           │
│  ├── routers/stock.py    REST API (/api/*)       │
│  └── routers/pages.py    页面路由                 │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│                  Services                        │
│  ├── stock_data.py     yfinance 封装             │
│  ├── financials.py     财报解析                   │
│  ├── analyst.py        机构评级                   │
│  ├── technical.py      技术指标计算               │
│  ├── llm_service.py    AI 总结                   │
│  ├── news_service.py   资讯聚合                   │
│  ├── cache_updater.py  后台缓存更新 (daemon)      │
│  ├── hunter.py         狩猎评分引擎               │
│  ├── discovery.py      交易所成分股发现           │
│  └── trades.py         交易记录 CRUD              │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│                  Storage                         │
│  ├── SQLite (stocktracing.db)                    │
│  │   ├── stock_cache      股价/估值缓存           │
│  │   ├── financial_cache  财报缓存                │
│  │   ├── analysis_cache   技术指标/历史缓存       │
│  │   ├── llm_cache        AI 分析历史             │
│  │   └── hunt_session     狩猎历史                │
│  ├── JSON 文件                                   │
│  │   ├── watchlist.json   自选股                  │
│  │   ├── trades.json      交易记录 (明文)         │
│  │   ├── config.json      LLM/代理配置            │
│  │   ├── stock_universe.json  狩猎标的库          │
│  │   └── exchange_stocks.json 交易所成分股        │
│  └── Memory                                      │
│      ├── _price_history   5min 价格历史           │
│      └── _ticks           后台缓存价格             │
└─────────────────────────────────────────────────┘
```

## 核心工作流

### 1. 后台缓存更新 (`cache_updater.py`)

```
启动时自动创建 daemon 线程
    │
    ▼
┌─────────────────────┐
│ 每 1s 循环           │
│  ├── 读取自选股列表   │
│  ├── 合并狩猎队列     │  ← get_updater().queue_symbols()
│  ├── 每批 2 只        │
│  ├── 只间休 0.5s      │  防止 yfinance 限流
│  ├── 批间休 1.5s      │
│  └── 写入 StockCache  │  ← SQLite
└─────────────────────┘
```

### 2. 请求处理 (`/api/stock/{symbol}/full`)

```
请求进入
    │
    ▼
符号解析 (_resolve_asymbol)
  对 6 位数字自动补 .SS/.SZ
    │
    ├── get_stock_info    ─→ StockCache (缓存优先，不触发 yfinance)
    ├── get_stock_history ─→ AnalysisCache (10min TTL)
    ├── get_analyst_info  ─→ StockCache (target 字段)
    ├── calculate_all_indicators ─→ AnalysisCache (10min TTL)
    ├── get_period_analysis ─→ 1年历史 → 计算 D/W/M/Y 涨跌+信号
    └── generate_summary  ─→ LLMCache (永久) 或 实时调用 LLM
    │
    ▼
SafeJSONResponse (NaN/Inf → null 清洗)
```

### 3. 1s 价格轮询 (`/api/stock/{symbol}/tick`)

```
前端每 1s 调用 /tick
    │
    ▼
get_updater().get_tick() ─→ 内存 _ticks 缓存 (120s TTL)
    │                           ↑ 后台线程写入
    │ 命中缓存: 直接返回
    │ 未命中:   _price_info_cache (15s TTL) → yfinance.info
    │
    ▼
5min 涨跌计算
  _price_history 首次种子化 (yfinance 5m candle)
  每次记录 (timestamp, price)
  找距今 300±120s 最近价格比对
```

### 4. 狩猎评分 (`hunter.py`)

```
用户选择大盘 + 领域
    │
    ▼
discover_all_stocks() 获取标的列表
  ├── 美股: S&P 500 + NASDAQ 100 (206 只)
  ├── A股: CSI 300 (48 只)
  ├── 港股: 恒生指数 (60 只)
  └── 日股: 日经 225 (56 只)
    │
    ▼
queue_symbols() 加入后台更新队列
    │
    ▼
逐只 score_stock() (纯缓存读取)
  ├── 价值 (0-30): PE <15 +10, PEG <1 +5
  ├── 机构 (0-25): 目标空间 >30% +12, 买入评级 +5
  ├── 技术 (0-25): 买入信号 +2/个
  └── 财务 (0-20): 股息 +3, 低 Beta +2
    │
    ▼
按总分降序排列，写入 hunt_session 表
```

### 5. 技术指标计算 (`technical.py`)

```
calculate_all_indicators()
  ├── SMA (20/50/200)
  ├── EMA (12/26/9)
  ├── RSI (14): 超买>70 超卖<30
  ├── MACD (12/26/9): 金叉/死叉
  ├── Bollinger (20, 2σ): 突破上/下轨
  ├── ATR (14), OBV
  ├── Stochastic (14/3): 超买>80 超卖<20
  ├── MA Cross: SMA20 穿 SMA50
  ├── Volume Surge: 当日量 > 20日均量×1.5
  └── 综合评分: buy/sell/neutral 计数
    │
    ▼
get_period_analysis()
  四周期独立计算 (D/W/M/Y):
  ├── 各自窗口: 20d/40d/80d/252d
  ├── 各自趋势: SMA5/SMA10/SMA30/SMA100
  └── 涨跌 + 信号 (B/S/N)
```

### 6. AI 分析 (`llm_service.py`)

```
generate_summary(symbol, context)
    │
    ▼
hash(基本面+分析师+技术面) → LLMCache 查重
    │
    ├── 命中 → 返回缓存
    │
    └── 未命中 → OpenAI API
                  │
                  ▼
              生成 6 维度中文分析 (800 字)
                  │
                  ▼
              LLMCache 持久化
```

### 7. 交易记录生命周期

```
创建: POST /api/trades → trades.json 写入
    │
    ▼
状态判定: close_price == null ? "open" : "closed"
    │
    ▼
开仓: direction=long, 留空 close_price
做空: direction=short, 留空 open_price (先平后开逻辑)
    │
    ▼
GET /api/trades      → 所有记录 + 当前价 + 浮盈/浮亏
GET /api/trades/stats → 汇总统计 + 总浮盈
    │
    ▼
PUT  /api/trades/{id}  → 更新 (补平仓价可闭合持仓)
DELETE → 删除记录
```

## 数据缓存策略

| 数据层 | 存储 | TTL | 触发更新 |
|--------|------|-----|---------|
| 股价信息 | StockCache (SQLite) | 无限制 | 后台线程 1s 循环 |
| K线历史 | AnalysisCache (SQLite) | 10min | 首次请求 |
| 技术指标 | AnalysisCache (SQLite) | 10min | 首次请求 |
| AI 分析 | LLMCache (SQLite) | 永久 | 首次请求/手动刷新 |
| 新闻资讯 | 文件缓存 | 2h | 用户点击加载 |
| Tick 价格 | 内存 dict | 120s | 后台线程 |
| 5min 历史 | 内存 dict | — | get_tick 调用时 |
| 交易所成分股 | 文件缓存 | 24h | 首次狩猎 |
| 交易记录 | trades.json | — | 用户操作 |

## 前端组件关系

```
base.html (侧边栏 + 全局 CSS/JS)
  ├── index.html
  │   ├── 搜索框
  │   ├── 自选管理
  │   ├── 时刻表 (24h 五地股市)
  │   └── 价格条 (D/W/M/Y/5m + 信号 + 综合 + PE/市值/目标)
  │       └── 1s 自动轮询 tick 动画
  │
  ├── stock_detail.html
  │   ├── Tab: 概览 / 图表 / 技术指标 / 机构评级 / 财报 / 资讯 / AI
  │   ├── Chart.js 价格走势
  │   └── AI 历史分析时间线
  │
  ├── scan.html
  │   └── 自选股信号矩阵表
  │
  ├── hunt.html
  │   ├── 大盘/领域选择器
  │   ├── 四维评分进度条横条
  │   └── 历史记录弹窗
  │
  └── trades.html
      ├── 统计面板 (总数/持仓/已实现/浮盈/胜率)
      ├── 交易记录列表
      └── 模态表单 (datetime-local)
```
