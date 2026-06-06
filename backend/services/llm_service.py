import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.config import get_llm_config, get_llm_enabled, get_proxy_dict
from backend.database.models import LLMCache, SessionLocal


def _get_client():
    cfg = get_llm_config()
    if not get_llm_enabled():
        return None
    try:
        from openai import OpenAI
        import httpx
        proxy = get_proxy_dict()
        http_client = None
        if proxy:
            http_client = httpx.Client(proxy=proxy.get("https") or proxy.get("http"))
        return OpenAI(
            api_key=cfg.get("api_key", ""),
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
            http_client=http_client,
        )
    except ImportError:
        return None


def _hash_prompt(symbol: str, context: dict) -> str:
    raw = json.dumps({"symbol": symbol, "context": context}, sort_keys=True, ensure_ascii=False, default=_json_default)
    return hashlib.sha256(raw.encode()).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        import pandas as pd
        if value is pd.NaT:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
    except Exception:
        pass
    return str(value)


def _get_cached(symbol: str, prompt_hash: str) -> str | None:
    db: Session = SessionLocal()
    try:
        row = db.query(LLMCache).filter(
            LLMCache.symbol == symbol,
            LLMCache.prompt_hash == prompt_hash,
        ).first()
        if row:
            return row.content
    finally:
        db.close()
    return None


def _cache_result(symbol: str, prompt_hash: str, content: str) -> None:
    db: Session = SessionLocal()
    try:
        db.add(LLMCache(symbol=symbol, prompt_hash=prompt_hash, content=content))
        db.commit()
    finally:
        db.close()


def get_latest_summary(symbol: str) -> dict[str, Any]:
    db: Session = SessionLocal()
    try:
        row = db.query(LLMCache).filter(
            LLMCache.symbol == symbol.upper().strip(),
        ).order_by(LLMCache.created_at.desc()).first()
        if not row:
            return {"enabled": get_llm_enabled(), "summary": "", "cached": True, "recommendation": None}
        return {
            "enabled": get_llm_enabled(),
            "summary": row.content,
            "cached": True,
            "recommendation": _extract_recommendation(row.content),
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
    finally:
        db.close()


def generate_summary(symbol: str, context: dict[str, Any]) -> dict[str, Any]:
    if not get_llm_enabled():
        return {"enabled": False, "summary": "LLM未配置。请在 data/config.json 中填入 api_key。支持OpenAI/Ollama等兼容API。"}

    prompt_hash = _hash_prompt(symbol, context)
    cached = _get_cached(symbol, prompt_hash)
    if cached:
        return {"enabled": True, "summary": cached, "cached": True, "recommendation": _extract_recommendation(cached)}

    client = _get_client()
    if client is None:
        return {"enabled": False, "summary": "LLM客户端初始化失败。请检查 openai 包是否安装。"}

    context_str = json.dumps(context, ensure_ascii=False, indent=2, default=_json_default)
    prompt = f"""你是一位严谨、风险优先的股票分析师。请根据以下数据对 {symbol} 进行全面分析总结。

数据：
{context_str}

请用中文输出，1000字以内，必须覆盖以下维度：
1. **公司概况**：业务、行业地位和当前市场关注点。
2. **近期资讯**：结合新闻标题/摘要判断潜在催化和负面事件。
3. **涨跌与技术面**：结合 D/W/M/Y 涨跌、周期信号、RSI、MACD、Bollinger 和综合技术信号判断趋势。
4. **机构评级与估值**：结合评级、目标价空间、调级和估值指标判断预期是否充分。
5. **营收与财务质量**：结合营收、利润、现金流和资产负债变化判断基本面质量。
6. **风险提示**：详细列出至少 3 个主要风险，包括估值风险、业绩风险、技术面风险、行业/宏观风险或新闻事件风险。
7. **结论**：最后单独一行输出 `AI信号：买入`、`AI信号：观望` 或 `AI信号：卖出`，并给出一句核心理由。

如果资料缺失，请明确说明缺失项如何影响判断，不要编造数据。"""

    try:
        cfg = get_llm_config()
        response = client.chat.completions.create(
            model=cfg.get("model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "你是一位专业的股票分析师。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1200,
        )
        summary = response.choices[0].message.content or ""
        _cache_result(symbol, prompt_hash, summary)
        return {"enabled": True, "summary": summary, "cached": False, "recommendation": _extract_recommendation(summary)}
    except Exception as e:
        return {"enabled": True, "summary": f"LLM分析出错: {str(e)}", "cached": False}


def _extract_recommendation(text: str) -> str | None:
    lowered = text.lower()
    for label in ("买入", "观望", "卖出"):
        if f"ai信号：{label}" in lowered or f"ai信号: {label}" in lowered or f"ai 信号：{label}" in lowered:
            return label
    if "买入" in text:
        return "买入"
    if "卖出" in text:
        return "卖出"
    if "观望" in text:
        return "观望"
    return None
