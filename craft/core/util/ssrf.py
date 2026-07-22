"""SSRF 防护 — 移植自 ssrf.ts

防止 SSRF（服务端请求伪造）攻击的安全请求工具。
阻止请求内网地址、元数据服务等敏感目标。
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable
from urllib.parse import urlparse

import httpx

BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.goog",
    "kubernetes.default.svc",
})

BLOCKED_IPV4_CIDRS = [
    ipaddress.IPv4Network("10.0.0.0/8"),       # private class A
    ipaddress.IPv4Network("0.0.0.0/8"),         # current network
    ipaddress.IPv4Network("172.16.0.0/12"),     # private class B
    ipaddress.IPv4Network("192.168.0.0/16"),    # private class C
    ipaddress.IPv4Network("169.254.0.0/16"),    # link-local
    ipaddress.IPv4Network("100.64.0.0/10"),     # shared address (CGN)
    ipaddress.IPv4Network("100.100.100.200/32"),# Alibaba Cloud metadata
]

BLOCKED_IPV6_PREFIXES = [
    ipaddress.IPv6Network("fe80::/10"),   # link-local
    ipaddress.IPv6Network("fc00::/7"),    # ULA
]

MAX_REDIRECTS = 5


def _is_blocked_ipv4(ip_str: str) -> bool:
    """检查 IPv4 地址是否被阻止"""
    try:
        addr = ipaddress.IPv4Address(ip_str)
        for net in BLOCKED_IPV4_CIDRS:
            if addr in net:
                return True
    except ipaddress.AddressValueError:
        pass
    return False


def _is_blocked_ipv6(ip_str: str) -> bool:
    """检查 IPv6 地址是否被阻止"""
    try:
        addr = ipaddress.IPv6Address(ip_str)
        # 检查 IPv4-mapped IPv6
        if addr.ipv4_mapped:
            return _is_blocked_ipv4(str(addr.ipv4_mapped))
        for net in BLOCKED_IPV6_PREFIXES:
            if addr in net:
                return True
    except ipaddress.AddressValueError:
        pass
    return False


def _is_blocked_ip(ip_str: str) -> bool:
    """检查 IP 地址是否被阻止"""
    ip_str = ip_str.strip("[]")
    if ":" in ip_str:
        return _is_blocked_ipv6(ip_str)
    return _is_blocked_ipv4(ip_str)


async def assert_safe_url(url: str) -> None:
    """断言 URL 是安全的（不会被 SSRF 利用）

    对应 TS assertSafeUrl()。同步 DNS 解析并检查 IP。
    抛出 ValueError 如果 URL 指向内网或元数据服务。
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # 去除 IPv6 括号
    hostname = hostname.strip("[]")

    if hostname in BLOCKED_HOSTNAMES:
        raise ValueError(f'SSRF protection: blocked hostname "{hostname}"')

    # 数值 IP 检查
    try:
        if _is_blocked_ip(hostname):
            raise ValueError(f'SSRF protection: blocked private/internal IP "{hostname}"')
        # 如果可以直接解析为 IP 且通过了检查，返回
        ipaddress.ip_address(hostname)
        return
    except ValueError:
        # 不是纯 IP，继续 DNS 检查
        pass

    # DNS 解析检查
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addrinfo:
            ip = sockaddr[0]
            if _is_blocked_ip(ip):
                raise ValueError(
                    f'SSRF protection: hostname "{hostname}" resolves to blocked IP "{ip}"'
                )
    except socket.gaierror:
        raise ValueError(f'SSRF protection: DNS resolution failed for "{hostname}"')


async def safe_fetch(
    url: str,
    client: httpx.AsyncClient | None = None,
    **kwargs,
) -> httpx.Response:
    """安全地发起 HTTP 请求（带 SSRF 保护）

    对应 TS safeFetch()。检查每个重定向目标 URL 的安全性。
    """
    await assert_safe_url(url)
    close_client = client is None
    if client is None:
        client = httpx.AsyncClient(follow_redirects=False, timeout=30)

    try:
        current_url = url
        for _ in range(MAX_REDIRECTS):
            response = await client.get(current_url, **kwargs)
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                if not location:
                    return response
                from urllib.parse import urljoin
                current_url = urljoin(current_url, location)
                await assert_safe_url(current_url)
                continue
            return response
        raise ValueError("SSRF protection: too many redirects")
    finally:
        if close_client:
            await client.aclose()
