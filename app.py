from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware


BASE_DIR = Path(__file__).resolve().parent
SH_TZ = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


class Settings(BaseModel):
    gateway_base_url: str = Field(
        default_factory=lambda: _env("LITELLM_GATEWAY_URL", "http://127.0.0.1:4000")
    )
    gateway_master_key: str = Field(default_factory=lambda: _env("LITELLM_MASTER_KEY"))
    admin_username: str = Field(
        default_factory=lambda: _env("SIMPLE_UI_USERNAME", os.getenv("UI_USERNAME", "admin"))
    )
    admin_password: str = Field(
        default_factory=lambda: _env("SIMPLE_UI_PASSWORD", os.getenv("UI_PASSWORD"))
    )
    session_secret: str = Field(
        default_factory=lambda: _env(
            "SIMPLE_UI_SESSION_SECRET", os.getenv("LITELLM_MASTER_KEY")
        )
    )
    app_port: int = Field(default_factory=lambda: int(_env("SIMPLE_UI_PORT", "4040")))
    max_chart_pages: int = Field(
        default_factory=lambda: int(_env("SIMPLE_UI_MAX_CHART_PAGES", "20"))
    )
    demo_mode: bool = Field(
        default_factory=lambda: os.getenv("SIMPLE_UI_DEMO_MODE", "false").lower()
        in ("1", "true", "yes", "on")
    )


settings = Settings()

app = FastAPI(title="LiteLLM 中文控制台", version="0.2.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="simple_cn_ui_session",
    same_site="lax",
    https_only=False,
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class ModelCreatePayload(BaseModel):
    model_name: str
    upstream_model: str
    api_base: str
    api_key: str | None = ""
    rpm: int | None = 600
    description: str | None = ""


class KeyCreatePayload(BaseModel):
    key_alias: str
    duration: str | None = "30d"
    models: list[str] = Field(default_factory=list)
    max_budget: float | None = None


def is_logged_in(request: Request) -> bool:
    return request.session.get("simple_ui_logged_in") is True


def require_login(request: Request) -> None:
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="请先登录。")


def _normalize_model_name(value: str) -> str:
    value = value.strip()
    return value if "/" in value else f"openai/{value}"


def _parse_iso(dt_value: str | None) -> datetime | None:
    if not dt_value:
        return None
    try:
        return datetime.fromisoformat(dt_value.replace("Z", "+00:00")).astimezone(SH_TZ)
    except ValueError:
        return None


def _range_from_query(
    range_name: str | None, start_date: str | None, end_date: str | None
) -> tuple[datetime, datetime, str]:
    now = datetime.now(SH_TZ)
    if start_date and end_date:
        start = datetime.combine(date.fromisoformat(start_date), time.min, SH_TZ)
        end = datetime.combine(date.fromisoformat(end_date), time.max, SH_TZ)
        return start, end, "custom"

    presets = {
        "24h": now - timedelta(hours=24),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
    }
    label = range_name or "24h"
    start = presets.get(label, presets["24h"])
    return start, now, label


def _to_int(*values: Any) -> int:
    for value in values:
        if value in (None, "", "None"):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return 0


def _to_float(*values: Any) -> float:
    for value in values:
        if value in (None, "", "None"):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _nested(row: dict[str, Any], *path: str) -> Any:
    current: Any = row
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _usage_number(row: dict[str, Any], *names: str) -> int:
    usage = row.get("usage") or {}
    response_cost = row.get("response_cost") or {}
    metadata = row.get("metadata") or {}
    candidates: list[Any] = []
    for name in names:
        candidates.extend(
            [
                row.get(name),
                usage.get(name),
                response_cost.get(name),
                metadata.get(name),
            ]
        )
    return _to_int(*candidates)


def token_breakdown(row: dict[str, Any]) -> dict[str, int | bool]:
    input_tokens = _usage_number(
        row,
        "prompt_tokens",
        "input_tokens",
        "prompt_token_count",
        "total_prompt_tokens",
    )
    output_tokens = _usage_number(
        row,
        "completion_tokens",
        "output_tokens",
        "completion_token_count",
        "total_completion_tokens",
    )
    total_tokens = _usage_number(row, "total_tokens", "total_token_count")
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    if input_tokens == 0 and output_tokens == 0 and total_tokens:
        input_tokens = total_tokens

    cached_tokens = _to_int(
        row.get("cached_tokens"),
        _nested(row, "prompt_tokens_details", "cached_tokens"),
        _nested(row, "usage", "prompt_tokens_details", "cached_tokens"),
        _nested(row, "metadata", "cached_tokens"),
        _nested(row, "metadata", "cache_read_input_tokens"),
        _nested(row, "metadata", "cache_hit_tokens"),
    )
    cache_creation_tokens = _to_int(
        row.get("cache_creation_input_tokens"),
        _nested(row, "metadata", "cache_creation_input_tokens"),
        _nested(row, "metadata", "cache_creation_tokens"),
    )
    reasoning_tokens = _to_int(
        row.get("reasoning_tokens"),
        _nested(row, "completion_tokens_details", "reasoning_tokens"),
        _nested(row, "usage", "completion_tokens_details", "reasoning_tokens"),
        _nested(row, "metadata", "reasoning_tokens"),
    )
    cache_hit = bool(
        row.get("cache_hit")
        or _nested(row, "metadata", "cache_hit")
        or cached_tokens > 0
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cache_hit": cache_hit,
    }


async def gateway_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    url = f"{settings.gateway_base_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {settings.gateway_master_key}"}
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_body,
        )
    if response.status_code >= 400:
        try:
            detail: Any = response.json()
        except ValueError:
            detail = {"message": response.text}
        raise HTTPException(status_code=response.status_code, detail=detail)
    if not response.content:
        return {}
    return response.json()


async def fetch_keys(size: int = 100) -> dict[str, Any]:
    if settings.demo_mode:
        return demo_keys()
    return await gateway_request(
        "GET",
        "/key/list",
        params={"page": 1, "size": size, "return_full_object": "true"},
    )


async def fetch_models() -> dict[str, Any]:
    if settings.demo_mode:
        return demo_models()
    return await gateway_request("GET", "/model/info")


async def fetch_logs_page(
    start_at: datetime,
    end_at: datetime,
    *,
    page: int,
    page_size: int,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if settings.demo_mode:
        return demo_logs_page(start_at, end_at, page=page, page_size=page_size)
    params: dict[str, Any] = {
        "start_date": start_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "page": page,
        "page_size": page_size,
        "sort_by": "startTime",
        "sort_order": "desc",
    }
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v not in (None, "")})
    return await gateway_request("GET", "/spend/logs/v2", params=params)


async def fetch_logs_window(
    start_at: datetime,
    end_at: datetime,
    *,
    max_pages: int,
    page_size: int = 100,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    first_page = await fetch_logs_page(start_at, end_at, page=1, page_size=page_size)
    all_rows.extend(first_page.get("data", []))
    total_pages = int(first_page.get("total_pages", 1) or 1)
    stop_page = min(total_pages, max_pages)
    for page in range(2, stop_page + 1):
        page_data = await fetch_logs_page(start_at, end_at, page=page, page_size=page_size)
        all_rows.extend(page_data.get("data", []))
    return all_rows, {
        "total_pages": total_pages,
        "loaded_pages": stop_page,
        "truncated": total_pages > max_pages,
    }


def empty_summary(start_at: datetime, end_at: datetime) -> dict[str, Any]:
    return summarize_logs([], {}, start_at, end_at)


async def safe_fetch_models() -> tuple[dict[str, Any], str | None]:
    try:
        return await fetch_models(), None
    except HTTPException as exc:
        return {"data": []}, readable_error(exc.detail)


async def safe_fetch_keys() -> tuple[dict[str, Any], str | None]:
    try:
        return await fetch_keys(), None
    except HTTPException as exc:
        return {"keys": [], "total_count": 0}, readable_error(exc.detail)


def readable_error(detail: Any) -> str:
    if isinstance(detail, dict):
        return (
            detail.get("error", {}).get("message")
            or detail.get("message")
            or str(detail)
        )
    return str(detail)


def demo_models() -> dict[str, Any]:
    return {
        "data": [
            {
                "model_name": "qwen3.7-plus",
                "litellm_params": {
                    "model": "openai/qwen3.7-plus",
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                },
                "model_info": {
                    "id": "demo-qwen37-plus",
                    "description": "百炼 Qwen 长上下文模型",
                    "context_window": 1000000,
                    "input_price_cny_per_1m_tokens": 2,
                    "output_price_cny_per_1m_tokens": 8,
                    "db_model": False,
                },
            },
            {
                "model_name": "Qwen3.5-9B-FP8",
                "litellm_params": {
                    "model": "openai/qwen9b-fp8-kv",
                    "api_base": "http://127.0.0.1:8000/v1",
                },
                "model_info": {
                    "id": "demo-qwen-local",
                    "description": "本地 vLLM FP8 模型",
                    "context_window": 32768,
                    "db_model": False,
                },
            },
            {
                "model_name": "deepseek-v3.2",
                "litellm_params": {
                    "model": "openai/deepseek-v3.2",
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                },
                "model_info": {
                    "id": "demo-deepseek",
                    "description": "云端 DeepSeek 兼容接口",
                    "context_window": 65536,
                    "input_price_cny_per_1m_tokens": 2,
                    "output_price_cny_per_1m_tokens": 3,
                    "db_model": False,
                },
            },
        ]
    }


def demo_keys() -> dict[str, Any]:
    return {
        "total_count": 3,
        "keys": [
            {"token": "demo-key-1", "key_alias": "合同解析", "spend": 18.42, "models": ["qwen3.7-plus"], "expires": None, "user_id": "legal"},
            {"token": "demo-key-2", "key_alias": "研发测试", "spend": 6.31, "models": [], "expires": None, "user_id": "dev"},
            {"token": "demo-key-3", "key_alias": "本地模型", "spend": 0.0, "models": ["Qwen3.5-9B-FP8"], "expires": None, "user_id": "local"},
        ],
    }


def demo_logs_page(start_at: datetime, end_at: datetime, *, page: int, page_size: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    model_cycle = ["qwen3.7-plus", "Qwen3.5-9B-FP8", "deepseek-v3.2"]
    key_cycle = ["demo-key-1", "demo-key-2", "demo-key-3"]
    total_hours = max(1, int((end_at - start_at).total_seconds() // 3600))
    for index in range(min(72, total_hours + 1)):
        at = end_at - timedelta(hours=index)
        base = 1200 + index * 137
        input_tokens = base * (4 + index % 5)
        output_tokens = 320 + (index % 7) * 94
        cached_tokens = int(input_tokens * (0.42 + (index % 4) * 0.08))
        cache_create = int(input_tokens * 0.08) if index % 3 == 0 else 0
        rows.append(
            {
                "request_id": f"demo-{index:04d}",
                "startTime": at.astimezone(UTC).isoformat(),
                "model_group": model_cycle[index % len(model_cycle)],
                "api_key": key_cycle[index % len(key_cycle)],
                "status": "failure" if index % 23 == 0 else "success",
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cached_tokens": cached_tokens,
                "cache_creation_input_tokens": cache_create,
                "reasoning_tokens": 120 if index % 4 == 0 else 0,
                "cache_hit": cached_tokens > 0,
                "spend": round((input_tokens * 0.000002 + output_tokens * 0.000008), 6),
                "request_duration_ms": 680 + index * 11,
                "metadata": {"user_api_key_alias": demo_keys()["keys"][index % 3]["key_alias"]},
            }
        )
    start = (page - 1) * page_size
    end = start + page_size
    total_pages = max(1, (len(rows) + page_size - 1) // page_size)
    return {
        "data": rows[start:end],
        "page": page,
        "page_size": page_size,
        "total": len(rows),
        "total_pages": total_pages,
    }


def key_alias_map(keys_payload: dict[str, Any]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for item in keys_payload.get("keys", []):
        token = item.get("token") or ""
        alias = item.get("key_alias") or item.get("key_name") or token
        if token:
            alias_map[token] = alias
    return alias_map


def row_key_name(row: dict[str, Any], alias_map: dict[str, str]) -> str:
    api_key = row.get("api_key") or ""
    metadata = row.get("metadata") or {}
    return (
        metadata.get("user_api_key_alias")
        or alias_map.get(api_key)
        or ("未使用虚拟密钥" if api_key in ("", "None", None) else api_key[:12])
    )


def summarize_logs(
    logs: list[dict[str, Any]], alias_map: dict[str, str], start_at: datetime, end_at: datetime
) -> dict[str, Any]:
    hourly = defaultdict(lambda: {"requests": 0, "input": 0, "output": 0, "cached": 0, "cache_create": 0, "spend": 0.0})
    daily = defaultdict(lambda: {"requests": 0, "tokens": 0, "spend": 0.0})
    key_stats = defaultdict(lambda: {"requests": 0, "tokens": 0, "spend": 0.0})
    model_stats = defaultdict(lambda: {"requests": 0, "tokens": 0, "spend": 0.0})

    totals = {
        "requests": len(logs),
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "reasoning_tokens": 0,
        "cache_hits": 0,
        "spend": 0.0,
        "failures": 0,
        "duration_ms": 0.0,
    }

    bucket = start_at.replace(minute=0, second=0, microsecond=0)
    while bucket <= end_at:
        hourly[bucket.strftime("%m-%d %H:00")]
        bucket += timedelta(hours=1)

    day_bucket = start_at.date()
    while day_bucket <= end_at.date():
        daily[day_bucket.strftime("%m-%d")]
        day_bucket += timedelta(days=1)

    for row in logs:
        row_time = _parse_iso(row.get("startTime"))
        if row_time is None:
            continue

        tokens = token_breakdown(row)
        spend = _to_float(row.get("spend"))
        duration_ms = _to_float(row.get("request_duration_ms"), row.get("duration_ms"))
        model_name = row.get("model_group") or row.get("model") or "-"
        key_name = row_key_name(row, alias_map)

        totals["input_tokens"] += int(tokens["input_tokens"])
        totals["output_tokens"] += int(tokens["output_tokens"])
        totals["total_tokens"] += int(tokens["total_tokens"])
        totals["cached_tokens"] += int(tokens["cached_tokens"])
        totals["cache_creation_tokens"] += int(tokens["cache_creation_tokens"])
        totals["reasoning_tokens"] += int(tokens["reasoning_tokens"])
        totals["cache_hits"] += 1 if tokens["cache_hit"] else 0
        totals["spend"] += spend
        totals["duration_ms"] += duration_ms
        if row.get("status") == "failure":
            totals["failures"] += 1

        hour_key = row_time.strftime("%m-%d %H:00")
        day_key = row_time.strftime("%m-%d")
        hourly[hour_key]["requests"] += 1
        hourly[hour_key]["input"] += int(tokens["input_tokens"])
        hourly[hour_key]["output"] += int(tokens["output_tokens"])
        hourly[hour_key]["cached"] += int(tokens["cached_tokens"])
        hourly[hour_key]["cache_create"] += int(tokens["cache_creation_tokens"])
        hourly[hour_key]["spend"] += spend

        daily[day_key]["requests"] += 1
        daily[day_key]["tokens"] += int(tokens["total_tokens"])
        daily[day_key]["spend"] += spend

        key_stats[key_name]["requests"] += 1
        key_stats[key_name]["tokens"] += int(tokens["total_tokens"])
        key_stats[key_name]["spend"] += spend

        model_stats[model_name]["requests"] += 1
        model_stats[model_name]["tokens"] += int(tokens["total_tokens"])
        model_stats[model_name]["spend"] += spend

    cache_hit_rate = (totals["cache_hits"] / totals["requests"] * 100) if totals["requests"] else 0
    success_rate = ((totals["requests"] - totals["failures"]) / totals["requests"] * 100) if totals["requests"] else 0
    avg_latency = totals["duration_ms"] / totals["requests"] if totals["requests"] else 0

    return {
        "cards": {
            **totals,
            "spend": round(totals["spend"], 6),
            "cache_hit_rate": round(cache_hit_rate, 2),
            "success_rate": round(success_rate, 2),
            "avg_latency_ms": round(avg_latency, 2),
        },
        "hourly_usage": [
            {
                "label": label,
                "requests": item["requests"],
                "input": item["input"],
                "output": item["output"],
                "cached": item["cached"],
                "cache_create": item["cache_create"],
                "spend": round(item["spend"], 6),
            }
            for label, item in hourly.items()
        ],
        "daily_usage": [
            {
                "label": label,
                "requests": item["requests"],
                "tokens": item["tokens"],
                "spend": round(item["spend"], 6),
            }
            for label, item in daily.items()
        ],
        "key_usage": sorted(
            [
                {
                    "label": label,
                    "requests": item["requests"],
                    "tokens": item["tokens"],
                    "spend": round(item["spend"], 6),
                }
                for label, item in key_stats.items()
            ],
            key=lambda item: item["tokens"],
            reverse=True,
        )[:10],
        "model_usage": sorted(
            [
                {
                    "label": label,
                    "requests": item["requests"],
                    "tokens": item["tokens"],
                    "spend": round(item["spend"], 6),
                }
                for label, item in model_stats.items()
            ],
            key=lambda item: item["tokens"],
            reverse=True,
        )[:10],
    }


def normalize_model_rows(models_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in models_payload.get("data", []):
        model_info = item.get("model_info") or {}
        litellm_params = item.get("litellm_params") or {}
        rows.append(
            {
                "id": model_info.get("id"),
                "model_name": item.get("model_name"),
                "upstream_model": litellm_params.get("model"),
                "api_base": litellm_params.get("api_base") or "",
                "description": model_info.get("description") or "",
                "db_model": bool(model_info.get("db_model")),
                "status_text": "数据库模型" if model_info.get("db_model") else "配置模型",
                "can_delete": bool(model_info.get("db_model")),
                "context_window": model_info.get("context_window") or "-",
                "input_price": model_info.get("input_price_cny_per_1m_tokens"),
                "output_price": model_info.get("output_price_cny_per_1m_tokens"),
            }
        )
    return rows


def normalize_keys(rows: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in rows.get("keys", []):
        normalized.append(
            {
                "token": item.get("token"),
                "key_alias": item.get("key_alias") or item.get("key_name") or "未命名密钥",
                "spend": item.get("spend") or 0,
                "models": item.get("models") or [],
                "expires": item.get("expires"),
                "created_at": item.get("created_at"),
                "user_id": item.get("user_id") or "",
            }
        )
    return normalized


def normalize_log_rows(rows: list[dict[str, Any]], alias_map: dict[str, str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        metadata = row.get("metadata") or {}
        error_info = metadata.get("error_information") or {}
        tokens = token_breakdown(row)
        normalized.append(
            {
                "request_id": row.get("request_id"),
                "time": row.get("startTime"),
                "model": row.get("model_group") or row.get("model") or "-",
                "key_name": row_key_name(row, alias_map),
                "status": "失败" if row.get("status") == "failure" else "成功",
                "status_code": row.get("status_code") or (500 if row.get("status") == "failure" else 200),
                "spend": row.get("spend") or 0,
                "duration_ms": row.get("request_duration_ms") or row.get("duration_ms") or 0,
                "error_message": error_info.get("error_message") or row.get("error_message") or "",
                **tokens,
            }
        )
    return normalized


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if is_logged_in(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> HTMLResponse:
    if username == settings.admin_username and password == settings.admin_password:
        request.session["simple_ui_logged_in"] = True
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "用户名或密码不正确。"},
        status_code=401,
    )


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_range": "24h",
            "gateway_url": settings.gateway_base_url,
        },
    )


@app.get("/api/bootstrap")
async def bootstrap(request: Request) -> JSONResponse:
    require_login(request)
    models_payload, models_error = await safe_fetch_models()
    keys_payload, keys_error = await safe_fetch_keys()
    return JSONResponse(
        {
            "system": {
                "gateway_url": settings.gateway_base_url,
                "model_count": len(models_payload.get("data", [])),
                "key_count": keys_payload.get("total_count", 0),
            },
            "models": normalize_model_rows(models_payload),
            "keys": normalize_keys(keys_payload),
            "warnings": [item for item in [models_error, keys_error] if item],
        }
    )


@app.get("/api/dashboard")
async def dashboard(
    request: Request,
    range_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> JSONResponse:
    require_login(request)
    start_at, end_at, label = _range_from_query(range_name, start_date, end_date)
    warnings: list[str] = []
    try:
        logs, meta = await fetch_logs_window(
            start_at, end_at, max_pages=settings.max_chart_pages
        )
    except HTTPException as exc:
        logs = []
        meta = {"total_pages": 0, "loaded_pages": 0, "truncated": False}
        warnings.append(readable_error(exc.detail))
    keys_payload, keys_error = await safe_fetch_keys()
    models_payload, models_error = await safe_fetch_models()
    warnings.extend([item for item in [keys_error, models_error] if item])
    alias_map = key_alias_map(keys_payload)
    summary = summarize_logs(logs, alias_map, start_at, end_at)
    summary["range"] = {
        "label": label,
        "start_date": start_at.date().isoformat(),
        "end_date": end_at.date().isoformat(),
    }
    summary["system"] = {
        "model_count": len(models_payload.get("data", [])),
        "key_count": keys_payload.get("total_count", 0),
        "gateway_url": settings.gateway_base_url,
    }
    summary["meta"] = meta
    summary["warnings"] = warnings
    summary["recent_logs"] = normalize_log_rows(logs[:20], alias_map)
    return JSONResponse(summary)


@app.get("/api/logs")
async def logs_api(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    range_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> JSONResponse:
    require_login(request)
    start_at, end_at, _ = _range_from_query(range_name, start_date, end_date)
    try:
        log_page = await fetch_logs_page(start_at, end_at, page=page, page_size=page_size)
        warning = None
    except HTTPException as exc:
        log_page = {"data": [], "page": page, "page_size": page_size, "total": 0, "total_pages": 0}
        warning = readable_error(exc.detail)
    keys_payload, _ = await safe_fetch_keys()
    alias_map = key_alias_map(keys_payload)
    return JSONResponse(
        {
            "data": normalize_log_rows(log_page.get("data", []), alias_map),
            "page": log_page.get("page", page),
            "page_size": log_page.get("page_size", page_size),
            "total": log_page.get("total", 0),
            "total_pages": log_page.get("total_pages", 0),
            "warning": warning,
        }
    )


@app.get("/api/models")
async def models_api(request: Request) -> JSONResponse:
    require_login(request)
    models_payload, warning = await safe_fetch_models()
    return JSONResponse({"data": normalize_model_rows(models_payload), "warning": warning})


@app.post("/api/models")
async def create_model(request: Request, payload: ModelCreatePayload) -> JSONResponse:
    require_login(request)
    body = {
        "model_name": payload.model_name.strip(),
        "litellm_params": {
            "model": _normalize_model_name(payload.upstream_model),
            "api_base": payload.api_base.strip(),
            "api_key": (payload.api_key or "").strip() or "not-used-for-local-endpoint",
            "rpm": payload.rpm or 600,
        },
        "model_info": {"description": (payload.description or "").strip()},
    }
    created = await gateway_request("POST", "/model/new", json_body=body)
    return JSONResponse({"message": "模型已注册。", "data": created})


@app.delete("/api/models/{model_id}")
async def delete_model_api(request: Request, model_id: str) -> JSONResponse:
    require_login(request)
    deleted = await gateway_request("POST", "/model/delete", json_body={"id": model_id})
    return JSONResponse({"message": "模型已删除。", "data": deleted})


@app.get("/api/keys")
async def keys_api(request: Request) -> JSONResponse:
    require_login(request)
    keys_payload, warning = await safe_fetch_keys()
    return JSONResponse({"data": normalize_keys(keys_payload), "warning": warning})


@app.post("/api/keys")
async def create_key(request: Request, payload: KeyCreatePayload) -> JSONResponse:
    require_login(request)
    body: dict[str, Any] = {
        "key_alias": payload.key_alias.strip(),
        "duration": payload.duration or "30d",
        "models": payload.models,
    }
    if payload.max_budget is not None:
        body["max_budget"] = payload.max_budget
    created = await gateway_request("POST", "/key/generate", json_body=body)
    return JSONResponse(
        {
            "message": "密钥已生成。",
            "actual_key": created.get("key"),
            "masked_key": created.get("key_name"),
            "token_id": created.get("token"),
            "data": created,
        }
    )


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})
