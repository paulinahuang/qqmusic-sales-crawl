#!/usr/bin/env python3
"""QQ 音乐数字专辑精确销量抓取任务。

默认策略：
1) 短链解析 + musicu 接口探测
2) 若未命中，可开启浏览器网络探测（Playwright）抓取页面真实请求返回
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

SALE_KEYWORDS = (
    "sale",
    "sales",
    "sold",
    "sell",
    "buy",
    "order",
    "销量",
    "pay",
)

NOISE_TOKENS = (
    "trace", "ts", "time", "version", "_ver", "uuid", "guid", "eid",
    "uin", "userid", "comment", "cmcount", "view", "play", "like",
)


class QQMusicSalesCrawler:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def _get_text(self, url: str) -> tuple[str, str]:
        req = Request(url, headers={"User-Agent": UA, "Referer": "https://y.qq.com/"})
        with urlopen(req, timeout=self.timeout) as resp:
            final_url = resp.geturl()
            text = resp.read().decode("utf-8", errors="ignore")
            return final_url, text

    @staticmethod
    def _strip_jsonp(text: str) -> str:
        t = text.strip()
        if t.startswith("{") or t.startswith("["):
            return t
        m = re.match(r"^[^(]+\((.*)\)\s*;?\s*$", t, re.S)
        return m.group(1).strip() if m else t

    def resolve_album_context(self, share_url: str) -> dict[str, Any]:
        final_url, html = self._get_text(share_url)
        ids: dict[str, int] = {}

        def add_from_text(label: str, text: str) -> None:
            for pattern in [rf"{label}[=:\"']+(\d+)", rf"\"{label}\"\s*:\s*(\d+)"]:
                m = re.search(pattern, text, re.I)
                if m:
                    ids[label] = int(m.group(1))
                    return

        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        for key in ("albumid", "productid", "pid", "id"):
            if key in qs and qs[key] and qs[key][0].isdigit():
                ids[key] = int(qs[key][0])

        for key in ("albumid", "productid", "pid", "album_id", "cid"):
            add_from_text(key, final_url)
            add_from_text(key, html)

        return {"ids": ids, "final_url": final_url, "html": html}

    def _musicu_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = urlencode({"format": "json", "data": json.dumps(payload, ensure_ascii=False)})
        api = f"https://u.y.qq.com/cgi-bin/musicu.fcg?{encoded}"
        _, text = self._get_text(api)
        return json.loads(self._strip_jsonp(text))

    def _collect_exact_sales_candidates(
        self,
        obj: Any,
        path: str = "",
        min_value: int = 1,
    ) -> list[tuple[str, int]]:
        """只收集“精确整数”销量候选，不接受 `1w+`/`万+` 等近似字符串。"""
        hits: list[tuple[str, int]] = []

        def score_key(k: str, p: str) -> bool:
            key = (k + " " + p).lower()
            if any(noise in key for noise in NOISE_TOKENS):
                return False
            return any(word in key for word in SALE_KEYWORDS)

        if isinstance(obj, dict):
            for k, v in obj.items():
                sub = f"{path}.{k}" if path else k
                if isinstance(v, bool):
                    continue
                if isinstance(v, int) and v >= min_value and v <= 1_000_000_000 and score_key(k, sub):
                    hits.append((sub, v))
                elif isinstance(v, str):
                    # 仅接受纯数字字符串，拒绝 1w+ / 1.5万 这类近似展示
                    raw = v.strip().replace(",", "")
                    if raw.isdigit() and score_key(k, sub):
                        val = int(raw)
                        if val <= 1_000_000_000:
                            hits.append((sub, val))

                    if raw.startswith("{") or raw.startswith("["):
                        try:
                            nested = json.loads(raw)
                            hits.extend(self._collect_exact_sales_candidates(nested, sub + "(json)", min_value))
                        except Exception:
                            pass

                hits.extend(self._collect_exact_sales_candidates(v, sub, min_value))

        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                hits.extend(self._collect_exact_sales_candidates(v, f"{path}[{i}]", min_value))

        return hits

    def _api_candidates(self, ids: dict[str, int]) -> list[dict[str, Any]]:
        album_id = ids.get("albumid") or ids.get("album_id")
        product_id = ids.get("productid") or ids.get("pid")
        payloads: list[dict[str, Any]] = []

        if album_id:
            payloads.extend(
                [
                    {
                        "comm": {"ct": 24, "cv": 0},
                        "req": {
                            "module": "musicmall.MusicMallSvr",
                            "method": "GetDigitalAlbumDetail",
                            "param": {"album_id": album_id},
                        },
                    },
                    {
                        "comm": {"ct": 24, "cv": 0},
                        "req": {
                            "module": "mall.MusicMallSvr",
                            "method": "GetDigitalAlbumDetail",
                            "param": {"album_id": album_id},
                        },
                    },
                    {
                        "comm": {"ct": 24, "cv": 0},
                        "req": {
                            "module": "vipmall.HallSvr",
                            "method": "GetDigitalAlbumInfo",
                            "param": {"albumid": album_id, "pid": product_id or 0},
                        },
                    },
                ]
            )

        if product_id:
            payloads.append(
                {
                    "comm": {"ct": 24, "cv": 0},
                    "req": {
                        "module": "vipmall.HallSvr",
                        "method": "GetProductInfo",
                        "param": {"productid": product_id},
                    },
                }
            )

        return payloads

    def probe_with_playwright(self, share_url: str, wait_ms: int = 5000) -> list[dict[str, Any]]:
        """通过浏览器监听页面真实 XHR/fetch 返回，以便拿到前端真实使用的销量字段。"""
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "未安装 Playwright。请先执行: pip install playwright && playwright install chromium"
            ) from exc

        records: list[dict[str, Any]] = []

        with sync_playwright() as p:  # pragma: no cover
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=UA)
            page = context.new_page()

            def handle_response(resp: Any) -> None:
                url = resp.url
                low_url = url.lower()
                if "y.qq.com" not in low_url and "qq.com" not in low_url:
                    return
                allow_tokens = ("musicu", "musicmall", "vipmall", "putao", "product", "digital", "album")
                if not any(t in low_url for t in allow_tokens):
                    return
                if "getcmcount" in low_url:
                    return

                try:
                    text = resp.text()
                    data = json.loads(self._strip_jsonp(text))
                except Exception:
                    return

                hits = self._collect_exact_sales_candidates(data)
                if hits:
                    records.append(
                        {
                            "url": url,
                            "hits": sorted(hits, key=lambda x: x[1], reverse=True)[:20],
                        }
                    )

            page.on("response", handle_response)
            page.goto(share_url, wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(wait_ms)
            context.close()
            browser.close()

        return records

    def fetch_precise_sales(
        self,
        share_url: str,
        use_browser_probe: bool = False,
        min_value: int = 1,
    ) -> tuple[int, dict[str, Any]]:
        context = self.resolve_album_context(share_url)
        ids = context["ids"]
        if not ids:
            raise RuntimeError("无法从链接中解析专辑/商品 ID，请确认链接有效。")

        inspected: dict[str, Any] = {
            "ids": ids,
            "final_url": context["final_url"],
            "api_candidates": [],
            "browser_records": [],
        }

        best: tuple[str, int] | None = None

        for payload in self._api_candidates(ids):
            try:
                data = self._musicu_call(payload)
            except Exception as exc:
                inspected["api_candidates"].append({"payload": payload, "error": str(exc)})
                continue

            hits = self._collect_exact_sales_candidates(data, min_value=min_value)
            inspected["api_candidates"].append(
                {
                    "payload": payload,
                    "hits": sorted(hits, key=lambda x: x[1], reverse=True)[:20],
                    "top_keys": list(data.keys())[:10] if isinstance(data, dict) else [],
                }
            )

            for p, v in hits:
                if best is None or v > best[1]:
                    best = (f"api:{p}", v)

        if use_browser_probe:
            records = self.probe_with_playwright(share_url)
            inspected["browser_records"] = records
            for rec in records:
                for p, v in rec["hits"]:
                    if best is None or v > best[1]:
                        best = (f"browser:{rec['url']}::{p}", v)

        if best is None:
            hint = (
                "未找到精确销量字段。你可以加 --browser-probe 让脚本直接监听网页真实接口，"
                "并查看 debug 中的 api_candidates/browser_records。"
            )
            raise RuntimeError(hint)

        return best[1], {"source_path": best[0], **inspected}


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 QQ 音乐数字专辑精确销量")
    parser.add_argument("url", help="QQ 音乐专辑分享链接")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    parser.add_argument(
        "--browser-probe",
        action="store_true",
        help="使用 Playwright 监听网页真实接口（更接近前端实际请求）",
    )
    parser.add_argument(
        "--min-value",
        type=int,
        default=1,
        help="销量候选最小值（默认 1；可设为 10000 过滤明显异常值）",
    )
    args = parser.parse_args()

    crawler = QQMusicSalesCrawler()
    try:
        sales, meta = crawler.fetch_precise_sales(
            args.url,
            use_browser_probe=args.browser_probe,
            min_value=args.min_value,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"精确销量: {sales}")
    print(f"识别字段: {meta['source_path']}")
    if args.debug:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
