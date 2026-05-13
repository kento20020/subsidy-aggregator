"""SSRF対策付きの安全なHTTPクライアント。

- allowlistに含まれるhostのみアクセス許可
- IPv4/IPv6リテラルURLは拒否
- リダイレクトは自動追従せず、手動で最大3回・allowlist内のみ追従
- 全リクエストにtimeout適用
"""
from __future__ import annotations

import ipaddress
import logging
import time
from urllib.parse import urlparse

import httpx

from .config import ALLOWED_HOSTS, MAX_REDIRECTS, REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)


class UnsafeURLError(ValueError):
    """allowlist違反・IPリテラル等で発射を拒否したエラー。"""


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def _validate_url(url: str) -> str:
    """URLのスキーム・host を検証して正規化済みのhostを返す。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise UnsafeURLError(f"unsupported scheme: {parsed.scheme}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeURLError("missing host")
    if _is_ip_literal(host):
        raise UnsafeURLError("IP literal URLs are not allowed")
    if host not in ALLOWED_HOSTS:
        raise UnsafeURLError(f"host not in allowlist: {host}")
    return host


def get_safe(
    url: str,
    *,
    params: dict | None = None,
    max_retries: int = 3,
) -> httpx.Response:
    """allowlist検証＋手動リダイレクト追従＋指数バックオフ付きのGET。

    - リトライ対象: 接続例外と5xx
    - 4xxは即座にreturn（呼び出し側で判断）
    """
    _validate_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9"}

    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=False,
        headers=headers,
    ) as client:
        current_url = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            response = _request_with_retry(client, current_url, params, max_retries)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    return response
                _validate_url(location)
                current_url = location
                params = None
                continue
            return response
        raise UnsafeURLError(f"too many redirects (>{MAX_REDIRECTS})")


def _request_with_retry(
    client: httpx.Client,
    url: str,
    params: dict | None,
    max_retries: int,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.get(url, params=params)
            if response.status_code >= 500 and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return response
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("unreachable")
