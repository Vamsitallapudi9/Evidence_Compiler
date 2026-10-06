"""Safe fetching of user-supplied links.

The server fetches the link (the user never downloads anything) and keeps a snapshot,
because evidence must stay stable after the page changes. Requests are restricted to
public http(s) hosts: private, loopback and link-local addresses are refused on every
redirect hop (SSRF protection), and response size is capped.
"""

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlparse

import httpx

USER_AGENT = "EvidenceCompiler/0.1 (+local research tool)"


class FetchError(ValueError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class Fetched:
    url: str  # what the user gave us
    final_url: str  # after rewriting and redirects
    content_type: str
    data: bytes
    filename: str


def rewrite(url: str) -> str:
    """Turn common share links into direct-download links."""
    m = re.match(r"https?://docs\.google\.com/document/d/([\w-]+)", url)
    if m:
        return f"https://docs.google.com/document/d/{m.group(1)}/export?format=docx"
    m = re.match(r"https?://docs\.google\.com/spreadsheets/d/([\w-]+)", url)
    if m:
        gid = re.search(r"[#&?]gid=(\d+)", url)
        suffix = f"&gid={gid.group(1)}" if gid else ""
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv{suffix}"
    m = re.match(r"https?://drive\.google\.com/file/d/([\w-]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/(.+)", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    m = re.match(r"https?://arxiv\.org/abs/([\w.\-/]+?)(v\d+)?$", url)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}{m.group(2) or ''}"
    return url


def check_host(url: str, *, allow_private: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("only http(s) links are supported", 400)
    if not parsed.hostname:
        raise FetchError("link has no host", 400)
    if parsed.username or parsed.password:
        raise FetchError("links with embedded credentials are not allowed", 400)
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"could not resolve {parsed.hostname}", 502) from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise FetchError(f"refusing to fetch non-public address {ip}", 400)


def _filename(url: str, headers: httpx.Headers) -> str:
    cd = headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    if m:
        return unquote(m.group(1)).strip()
    path = urlparse(url).path.rstrip("/")
    return unquote(path.rsplit("/", 1)[-1]) or urlparse(url).hostname or "link"


def fetch(
    url: str,
    *,
    max_bytes: int = 25 * 1024 * 1024,
    allow_private: bool = False,
    timeout: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> Fetched:
    url = url.strip()
    target = rewrite(url)
    with httpx.Client(
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        transport=transport,
    ) as client:
        for _ in range(6):
            check_host(target, allow_private=allow_private)
            try:
                with client.stream("GET", target) as resp:
                    if resp.is_redirect:
                        target = urljoin(target, resp.headers.get("location", ""))
                        continue
                    if resp.status_code in (401, 403):
                        raise FetchError(
                            f"the link requires sign-in or is not public (HTTP {resp.status_code})",
                            403,
                        )
                    if resp.status_code == 404:
                        raise FetchError("the link was not found (HTTP 404)", 404)
                    if resp.status_code >= 400:
                        raise FetchError(f"fetch failed with HTTP {resp.status_code}", 502)
                    declared = int(resp.headers.get("content-length") or 0)
                    if declared > max_bytes:
                        raise FetchError(f"content exceeds {max_bytes // 2**20} MB limit", 413)
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise FetchError(f"content exceeds {max_bytes // 2**20} MB limit", 413)
                        chunks.append(chunk)
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    return Fetched(
                        url=url,
                        final_url=str(resp.url),
                        content_type=ctype,
                        data=b"".join(chunks),
                        filename=_filename(str(resp.url), resp.headers),
                    )
            except httpx.TimeoutException as exc:
                raise FetchError("the link timed out", 504) from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"could not fetch the link: {exc}", 502) from exc
    raise FetchError("too many redirects", 502)
