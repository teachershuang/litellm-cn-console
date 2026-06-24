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
    gateway_master_key: str = Field(
        default_factory=lambda: _env("LITELLM_MASTER_KEY")
    )
    admin_username: str = Field(
        default_factory=lambda: _env("SIMPLE_UI_USERNAME", _env("UI_USERNAME", "admin"))
    )
    admin_password: str = Field(
        default_factory=lambda: _env("SIMPLE_UI_PASSWORD", _env("UI_PASSWORD"))
    )
    session_secret: str = Field(
        default_factory=lambda: _env(
            "SIMPLE_UI_SESSION_SECRET", _env("LITELLM_MASTER_KEY")
        )
    )
    app_port: int = Field(
        default_factory=lambda: int(_env("SIMPLE_UI_PORT", "4040"))
    )
    max_chart_pages: int = Field(
        default_factory=lambda: int(_env("SIMPLE_UI_MAX_CHART_PAGES", "20"))
    )


settings = Settings()

app = FastAPI(title="LiteLLM 简化管理台", version="0.1.0")
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
    today = datetime.now(SH_TZ)
    if start_date and end_date:
        start = datetime.combine(date.fromisoformat(start_date), time.min, SH_TZ)
        end = datetime.combine(date.fromisoformat(end_date), time.max, SH_TZ)
        return start, end, "自定义"

    presets = {
        "24h": today - timedelta(hours=24),
        "7d": today - timedelta(days=7),
        "30d": today - timedelta(days=30),
    }
    label = range_name or "7d"
    start = presets.get(label, presets["7d"])
    return start, today, label


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
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = {"message": response.text}
        raise HTTPException(status_code=response.status_code, detail=detail)
    if not response.content:
        return {}
    return response.json()


async def fetch_keys(size: int = 100) -> dict[str, Any]:
    return await gateway_request(
        "GET",
        "/key/list",
        params={"page": 1, "size": size, "return_full_object": "true"},
    )


async def fetch_models() -> dict[str, Any]:
    return await gateway_request("GET", "/model/info")


async def fetch_logs_page(
    start_at: datetime,
    end_at: datetime,
    *,
    page: int,
    page_size: int,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        page_data = await fetch_logs_page(
            start_at, end_at, page=page, page_size=page_size
        )
        all_rows.extend(page_data.get("data", []))
    return all_rows, {
        "total_pages": total_pages,
        "loaded_pages": stop_page,
        "truncated": total_pages > max_pages,
    }


def key_alias_map(keys_payload: dict[str, Any]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for item in keys_payload.get("keys", []):
        token = item.get("token") or ""
        alias = item.get("key_alias") or item.get("key_name") or token
        if token:
            alias_map[token] = alias
    return alias_map


def summarize_logs(
    logs: list[dict[str, Any]], alias_map: dict[str, str], start_at: datetime, end_at: datetime
) -> dict[str, Any]:
    hourly = defaultdict(int)
    daily_tokens = defaultdict(int)
    key_counts = defaultdict(int)
    total_tokens = 0
    total_spend = 0.0
    failures = 0

    bucket = start_at.replace(minute=0, second=0, microsecond=0)
    while bucket <= end_at:
        hourly[bucket.strftime("%m-%d %H:00")] = 0
        bucket += timedelta(hours=1)

    day_bucket = start_at.date()
    while day_bucket <= end_at.date():
        daily_tokens[day_bucket.strftime("%m-%d")] = 0
        day_bucket += timedelta(days=1)

    for row in logs:
        row_time = _parse_iso(row.get("startTime"))
        if row_time is None:
            continue
        hour_key = row_time.strftime("%m-%d %H:00")
        day_key = row_time.strftime("%m-%d")
        hourly[hour_key] += 1
        daily_tokens[day_key] += int(row.get("total_tokens") or 0)

        api_key = row.get("api_key") or ""
        metadata = row.get("metadata") or {}
        key_name = (
            metadata.get("user_api_key_alias")
            or alias_map.get(api_key)
            or ("未使用虚拟密钥" if api_key in ("", "None", None) else api_key[:12])
        )
        key_counts[key_name] += 1

        total_tokens += int(row.get("total_tokens") or 0)
        total_spend += float(row.get("spend") or 0.0)
        if row.get("status") == "failure":
            failures += 1

    top_keys = sorted(
        [{"label": label, "value": value} for label, value in key_counts.items()],
        key=lambda item: item["value"],
        reverse=True,
    )[:10]

    return {
        "cards": {
            "requests": len(logs),
            "tokens": total_tokens,
            "spend": round(total_spend, 6),
            "failures": failures,
        },
        "hourly_requests": [{"label": k, "value": v} for k, v in hourly.items()],
        "daily_tokens": [{"label": k, "value": v} for k, v in daily_tokens.items()],
        "key_requests": top_keys,
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
        api_key = row.get("api_key") or ""
        key_name = (
            metadata.get("user_api_key_alias")
            or alias_map.get(api_key)
            or ("未使用虚拟密钥" if api_key in ("", "None", None) else api_key[:12])
        )
        normalized.append(
            {
                "request_id": row.get("request_id"),
                "time": row.get("startTime"),
                "model": row.get("model_group") or row.get("model") or "-",
                "key_name": key_name,
                "status": "失败" if row.get("status") == "failure" else "成功",
                "total_tokens": row.get("total_tokens") or 0,
                "spend": row.get("spend") or 0,
                "duration_ms": row.get("request_duration_ms") or 0,
                "error_message": error_info.get("error_message") or "",
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
            "default_range": "7d",
            "gateway_url": settings.gateway_base_url,
        },
    )


@app.get("/api/bootstrap")
async def bootstrap(request: Request) -> JSONResponse:
    require_login(request)
    models_payload, keys_payload = await fetch_models(), await fetch_keys()
    return JSONResponse(
        {
            "system": {
                "gateway_url": settings.gateway_base_url,
                "model_count": len(models_payload.get("data", [])),
                "key_count": keys_payload.get("total_count", 0),
            },
            "models": normalize_model_rows(models_payload),
            "keys": normalize_keys(keys_payload),
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
    logs, meta = await fetch_logs_window(
        start_at, end_at, max_pages=settings.max_chart_pages
    )
    keys_payload = await fetch_keys()
    models_payload = await fetch_models()
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
    log_page = await fetch_logs_page(start_at, end_at, page=page, page_size=page_size)
    alias_map = key_alias_map(await fetch_keys())
    return JSONResponse(
        {
            "data": normalize_log_rows(log_page.get("data", []), alias_map),
            "page": log_page.get("page", page),
            "page_size": log_page.get("page_size", page_size),
            "total": log_page.get("total", 0),
            "total_pages": log_page.get("total_pages", 0),
        }
    )


@app.get("/api/models")
async def models_api(request: Request) -> JSONResponse:
    require_login(request)
    return JSONResponse({"data": normalize_model_rows(await fetch_models())})


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
        "model_info": {
            "description": (payload.description or "").strip(),
        },
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
    return JSONResponse({"data": normalize_keys(await fetch_keys())})


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
