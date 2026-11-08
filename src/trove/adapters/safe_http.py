from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 5
USER_AGENT = "Trove/0.1 (+local personal library)"
CHUNK_SIZE = 1024 * 1024


class SafeHttpError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class HttpResponse:
    content: bytes
    content_type: str | None
    final_url: str


def validate_public_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise SafeHttpError("feed.scheme", "只允许 http/https URL")
    if not parts.hostname:
        raise SafeHttpError("feed.invalid_url", "URL 缺少主机名")
    if parts.username or parts.password:
        raise SafeHttpError("feed.invalid_url", "URL 不能包含用户名或密码")
    hostname = parts.hostname
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise SafeHttpError("feed.private_address", "不允许访问本机地址")
    try:
        addresses = {
            str(info[4][0]) for info in socket.getaddrinfo(hostname, parts.port or 80)
        }
    except OSError as exc:
        raise SafeHttpError("feed.network", f"无法解析主机名: {hostname}") from exc
    for address in addresses:
        if not _is_public_address(address):
            raise SafeHttpError("feed.private_address", "不允许访问私网、回环或元数据地址")
    return url


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    return not (
        isinstance(ip, ipaddress.IPv4Address)
        and ip in ipaddress.ip_network("100.64.0.0/10")
    )


class SafeHttpClient:
    def __init__(self, *, timeout: float = 20.0, max_redirects: int = MAX_REDIRECTS) -> None:
        self.timeout = timeout
        self.max_redirects = max_redirects

    def get_bytes(self, url: str, *, max_bytes: int) -> HttpResponse:
        current = validate_public_url(url)
        with httpx.Client(
            follow_redirects=False,
            timeout=self.timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for _ in range(self.max_redirects + 1):
                try:
                    with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise SafeHttpError("feed.network", "重定向缺少 Location")
                            current = validate_public_url(urljoin(current, location))
                            continue
                        if response.status_code >= 400:
                            raise SafeHttpError(
                                "feed.network", f"请求失败: HTTP {response.status_code}"
                            )
                        content_type = response.headers.get("content-type")
                        length = response.headers.get("content-length")
                        if length and length.isdigit() and int(length) > max_bytes:
                            raise SafeHttpError("feed.too_large", "响应超过大小限制")
                        chunks: list[bytes] = []
                        total = 0
                        for chunk in response.iter_bytes(CHUNK_SIZE):
                            total += len(chunk)
                            if total > max_bytes:
                                raise SafeHttpError("feed.too_large", "响应超过大小限制")
                            chunks.append(chunk)
                        return HttpResponse(
                            content=b"".join(chunks),
                            content_type=content_type,
                            final_url=str(response.url),
                        )
                except httpx.HTTPError as exc:
                    raise SafeHttpError("feed.network", f"网络请求失败: {exc}") from exc
            raise SafeHttpError("feed.network", "重定向次数过多")

    def download_to_file(
        self,
        url: str,
        destination: Path,
        *,
        max_bytes: int,
        allowed_types: set[str] | None = None,
    ) -> tuple[str | None, int]:
        current = validate_public_url(url)
        with httpx.Client(
            follow_redirects=False,
            timeout=self.timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for _ in range(self.max_redirects + 1):
                try:
                    with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise SafeHttpError("feed.network", "重定向缺少 Location")
                            current = validate_public_url(urljoin(current, location))
                            continue
                        if response.status_code >= 400:
                            raise SafeHttpError(
                                "feed.network", f"请求失败: HTTP {response.status_code}"
                            )
                        content_type = (response.headers.get("content-type") or "").split(";")[0]
                        if allowed_types and content_type and content_type not in allowed_types:
                            raise SafeHttpError(
                                "download.invalid_type",
                                f"不支持的内容类型: {content_type}",
                            )
                        length = response.headers.get("content-length")
                        if length and length.isdigit() and int(length) > max_bytes:
                            raise SafeHttpError("download.too_large", "媒体文件超过大小限制")
                        total = 0
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        temporary = destination.with_name(destination.name + ".tmp")
                        try:
                            with temporary.open("wb") as handle:
                                for chunk in response.iter_bytes(CHUNK_SIZE):
                                    total += len(chunk)
                                    if total > max_bytes:
                                        raise SafeHttpError(
                                            "download.too_large", "媒体文件超过大小限制"
                                        )
                                    handle.write(chunk)
                            temporary.replace(destination)
                        finally:
                            temporary.unlink(missing_ok=True)
                        return content_type, total
                except httpx.HTTPError as exc:
                    raise SafeHttpError("download.network", f"网络请求失败: {exc}") from exc
            raise SafeHttpError("download.network", "重定向次数过多")
