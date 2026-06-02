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
    raw = json.dumps({"symbol": symbol, "context": context}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


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


def generate_summary(symbol: str, context: dict[str, Any]) -> dict[str, Any]:
    if not get_llm_enabled():
        return {"enabled": False, "summary": "LLM未配置。请在 data/config.json 中填入 api_key。支持OpenAI/Ollama等兼容API。"}

    prompt_hash = _hash_prompt(symbol, context)
    cached = _get_cached(symbol, prompt_hash)
    if cached:
        return {"enabled": True, "summary": cached, "cached": True}

    client = _get_client()
    if client is None:
        return {"enabled": False, "summary": "LLM客户端初始化失败。请检查 openai 包是否安装。"}

    context_str = json.dumps(context, ensure_ascii=False, indent=2)
    prompt = f"""你是一位资深股票分析师。请根据以下数据对 {symbol} 进行全面分析总结。

数据：
{context_str}

请从以下维度分析（中文，800字以内）：
1. **公司概况**：业务、行业地位
2. **财务健康度**：盈利能力、成长性
3. **估值分析**：当前估值合理性、机构目标价
4. **技术面**：当前信号、趋势判断
5. **风险提示**：潜在风险
6. **综合建议**：偏多/偏空/观望及理由"""

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
        return {"enabled": True, "summary": summary, "cached": False}
    except Exception as e:
        return {"enabled": True, "summary": f"LLM分析出错: {str(e)}", "cached": False}
