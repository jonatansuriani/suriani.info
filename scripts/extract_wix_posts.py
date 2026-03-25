#!/usr/bin/env python3
"""
Fetch Wix blog post pages (SSR HTML), extract rich text body, download images,
and write Jekyll Markdown with permalinks matching the live URL paths.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import html2text
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "_posts"
ASSETS_IMAGES = ROOT / "assets" / "images" / "posts"

UA = "Mozilla/5.0 (compatible; SurianiBlogExport/1.0; +https://suriani.info)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})
try:
    import certifi

    SESSION.verify = certifi.where()
except ImportError:
    pass
if os.environ.get("WIX_EXPORT_INSECURE_SSL") == "1":
    SESSION.verify = False
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

H2T = html2text.HTML2Text()
H2T.body_width = 0
H2T.ignore_links = False
H2T.ignore_images = False
H2T.ignore_emphasis = False
H2T.unicode_snob = True


def fetch(url: str) -> str:
    """Prefer curl (matches system trust store); fall back to requests."""
    try:
        out = subprocess.run(
            ["curl", "-fsSL", "-A", UA, "--max-time", "120", url],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        r = SESSION.get(url, timeout=120)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text


def discover_urls(index_url: str) -> list[str]:
    html_text = fetch(index_url)
    urls: set[str] = set()
    for m in re.finditer(
        r'href="(https://www\.suriani\.info/(?:en/)?post/[^"]+)"',
        html_text,
    ):
        urls.add(html.unescape(m.group(1)))
    for m in re.finditer(r'href="(/(?:en/)?post/[^"]+)"', html_text):
        path = html.unescape(m.group(1))
        urls.add("https://www.suriani.info" + path.split("?")[0])
    return sorted(urls)


def canonical_wix_media_url(url: str) -> str:
    """Prefer original asset URL without /v1/fill/ transforms."""
    if "static.wixstatic.com/media/" not in url:
        return url
    return url.split("/v1/")[0] if "/v1/" in url else url


def extract_ld_blog_posting(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string or not script.string.strip():
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "BlogPosting":
            return data
    return None


def img_best_url(tag) -> str | None:
    pm = tag.get("data-pin-media")
    src = tag.get("src")
    for u in (pm, src):
        if u:
            return canonical_wix_media_url(html.unescape(u))
    info = tag.get("data-image-info")
    if not info:
        return None
    try:
        d = json.loads(info.replace("&quot;", '"'))
    except json.JSONDecodeError:
        return None
    uri = (d.get("imageData") or {}).get("uri")
    if not uri:
        return None
    if uri.startswith("http"):
        return canonical_wix_media_url(uri)
    return canonical_wix_media_url("https://static.wixstatic.com/media/" + uri.lstrip("/"))


def simplify_body_ricos(desc_section) -> BeautifulSoup:
    """Return a small HTML tree suitable for html2text."""
    inner = desc_section.select_one(".fTEXDR")
    if inner is None:
        inner = desc_section
    soup = BeautifulSoup(str(inner), "html.parser")

    for w in soup.find_all("wow-image"):
        img = w.find("img")
        if not img:
            continue
        url = img_best_url(img)
        if not url:
            w.decompose()
            continue
        alt = img.get("alt") or ""
        new_img = soup.new_tag("img", src=url, alt=alt)
        w.replace_with(new_img)

    for img in soup.find_all("img"):
        if not img.get("src"):
            continue
        img["src"] = canonical_wix_media_url(html.unescape(img["src"]))

    for a in soup.find_all("a", href=True):
        href = html.unescape(a["href"])
        if "suriani.info" in href:
            path = urlparse(href).path or "/"
            a["href"] = path
        else:
            a["href"] = href

    for tag in soup.find_all(["script", "style", "button"]):
        tag.decompose()

    return soup


def slug_from_post_url(url: str) -> tuple[str, str]:
    """
    Return (jekyll_permalink_prefix, slug) e.g. ('/en/post', 'my-slug').
    permalink will be prefix/slug/
    """
    path = unquote(urlparse(url).path).strip("/")
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == "en" and parts[1] == "post":
        return "/en/post", "/".join(parts[2:])
    if len(parts) >= 2 and parts[0] == "post":
        return "/post", "/".join(parts[1:])
    raise ValueError(f"Unexpected post URL shape: {url}")


def safe_fs_slug(slug: str) -> str:
    """Filesystem-safe folder name; keep Unicode letters from the live URL slug."""
    s = unquote(slug)
    s = s.replace("/", "-").replace("\\", "-")
    s = re.sub(r"[\x00-\x1f<>:\"|?*]", "-", s)
    return s.strip("-.") or "post"


def download_image(url: str, dest_dir: Path, used_names: dict[str, int]) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    path_name = Path(urlparse(url).path).name
    base = path_name if path_name else "image.bin"
    if base in used_names:
        used_names[base] += 1
        p = Path(base)
        base = f"{p.stem}-{used_names[base]}{p.suffix}"
    else:
        used_names[base] = 0
    out = dest_dir / base
    if not out.exists():
        try:
            subprocess.run(
                ["curl", "-fsSL", "-A", UA, "--max-time", "120", "-o", str(out), url],
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            r = SESSION.get(url, timeout=120)
            r.raise_for_status()
            out.write_bytes(r.content)
        time.sleep(0.2)
    return base


def rewrite_images_in_markdown(
    md: str, url_to_local: dict[str, str], permalink_prefix: str, fs_slug: str
) -> str:
    def repl(m: re.Match) -> str:
        alt, url = m.group(1), m.group(2)
        canonical = canonical_wix_media_url(html.unescape(url))
        local = url_to_local.get(canonical) or url_to_local.get(url)
        if not local:
            for k, v in url_to_local.items():
                if k.rstrip("/") == canonical.rstrip("/"):
                    local = v
                    break
        if not local:
            return m.group(0)
        rel = f"/assets/images/posts/{fs_slug}/{local}"
        return f"![{alt}]({rel})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, md)


def extract_post(url: str) -> None:
    print("Fetching", url)
    doc = fetch(url)
    soup = BeautifulSoup(doc, "html.parser")

    ld = extract_ld_blog_posting(soup)
    title_el = soup.select_one('[data-hook="post-title"]')
    title = title_el.get_text(strip=True) if title_el else (ld or {}).get("headline", "Untitled")

    date_iso = None
    if ld:
        date_iso = (ld.get("datePublished") or "")[:10]
    if not date_iso:
        t = soup.select_one('[data-hook="time-ago"]')
        if t and t.get("title"):
            from datetime import datetime

            try:
                date_iso = datetime.strptime(t["title"], "%b %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

    if not date_iso:
        date_iso = "2000-01-01"

    desc = soup.select_one('section[data-hook="post-description"]')
    if not desc:
        print("  SKIP: no post body", url, file=sys.stderr)
        return

    mini = simplify_body_ricos(desc)
    body_html = str(mini)
    md = H2T.handle(body_html).strip()
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)

    prefix, slug = slug_from_post_url(url)
    fs_slug = safe_fs_slug(slug)
    img_dir = ASSETS_IMAGES / fs_slug
    used: dict[str, int] = {}
    url_to_local: dict[str, str] = {}

    for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", md):
        src = html.unescape(m.group(2))
        if "static.wixstatic.com" not in src:
            continue
        can = canonical_wix_media_url(src)
        if can in url_to_local:
            continue
        try:
            fname = download_image(can, img_dir, used)
            url_to_local[can] = fname
        except requests.RequestException as e:
            print("  image fail", can, e, file=sys.stderr)

    md = rewrite_images_in_markdown(md, url_to_local, prefix, fs_slug)

    permalink = f"{prefix}/{slug}/"
    file_slug = fs_slug.replace("/", "-")
    if len(file_slug) > 120:
        file_slug = file_slug[:120].rstrip("-")
    out_name = f"{date_iso}-{file_slug}.md"
    out_path = POSTS_DIR / out_name

    front = [
        "---",
        f"title: {json.dumps(title)}",
        f"date: {date_iso} 12:00:00 +0000",
        "layout: post",
        f"permalink: {permalink}",
        "---",
        "",
    ]
    out_path.write_text("\n".join(front) + md + "\n", encoding="utf-8")
    print("  Wrote", out_path.relative_to(ROOT))


def main() -> None:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_IMAGES.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    all_urls: list[str] = []
    for index in (
        "https://www.suriani.info/en",
        "https://www.suriani.info/",
    ):
        try:
            found = discover_urls(index)
        except requests.RequestException as e:
            print("Index failed", index, e, file=sys.stderr)
            continue
        for u in found:
            if u not in seen:
                seen.add(u)
                all_urls.append(u)

    if not all_urls:
        print("No post URLs found.", file=sys.stderr)
        sys.exit(1)

    for u in all_urls:
        try:
            extract_post(u)
        except Exception as e:
            print("Error", u, e, file=sys.stderr)
            raise
        time.sleep(0.4)


if __name__ == "__main__":
    main()
