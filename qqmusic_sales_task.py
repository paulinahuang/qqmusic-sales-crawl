#!/usr/bin/env python3
"""QQ 音乐数字专辑销量抓取任务。"""

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


def _parse_human_number(text: str) -> int | None:
    """将 '15000' / '1.5万' / '725万+' 等字符串转换为整数。"""
    s = text.strip().replace(",", "").replace("+", "")
    m = re.search(r"(\d+(?:\.\d+)?)([万亿]?)", s)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        n *= 10_000
    elif unit == "亿":
        n *= 100_000_000
    return int(n)


class QQMusicSalesCrawler:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def _get_text(self, url: str) -> tuple[str, str]:
        req = Request(url, headers={"User-Agent": UA, "Referer": "https://y.qq.com/"})
        with urlopen(req, timeout=self.timeout) as resp:
            final_url = resp.geturl()
            text = resp.read().decode("utf-8", errors="ignore")
            return final_url, text

    def resolve_album_context(self, share_url: str) -> dict[str, Any]:
        final_url, html = self._get_text(share_url)
        ids: dict[str, int] = {}

        def add_from_text(label: str, text: str) -> None:
            patterns = [
                rf"{label}[=:\"']+(\d+)",
                rf"\"{label}\"\s*:\s*(\d+)",
            ]
            for pattern in patterns:
                m = re.search(pattern, text, re.I)
                if m:
                    ids[label] = int(m.group(1))
                    return

        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        for key in ("albumid", "albummid", "productid", "id", "pid"):
            if key in qs and qs[key] and qs[key][0].isdigit():
                ids[key] = int(qs[key][0])

        for key in ("albumid", "productid", "pid", "album_id", "cid"):
            add_from_text(key, final_url)
            add_from_text(key, html)

        if "albumid" not in ids:
            m = re.search(r"/album/(\d+)", final_url)
            if m:
                ids["albumid"] = int(m.group(1))

        return {"ids": ids, "final_url": final_url, "html": html}

    def _musicu_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = urlencode({"format": "json", "data": json.dumps(payload, ensure_ascii=False)})
        api = f"https://u.y.qq.com/cgi-bin/musicu.fcg?{encoded}"
        _, text = self._get_text(api)
        return json.loads(text)

    def _try_parse_embedded_json(self, text: str) -> Any:
        s = text.strip()
        if not s:
            return None
        if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
            return None
        try:
            return json.loads(s)
        except Exception:
            return None

    def _collect_sales_candidates(self, obj: Any, path: str = "") -> list[tuple[str, int]]:
        hits: list[tuple[str, int]] = []
        strong_keywords = (
            "sale",
            "sales",
            "sold",
            "sell",
            "buy",
            "order",
            "count",
            "num",
            "volume",
            "销量",
            "张",
        )

        def score_key(k: str, p: str) -> bool:
            key = (k + " " + p).lower()
            return any(word in key for word in strong_keywords)

        if isinstance(obj, dict):
            for k, v in obj.items():
                sub = f"{path}.{k}" if path else k
                if isinstance(v, (int, float)) and v > 0 and score_key(k, sub):
                    hits.append((sub, int(v)))
                elif isinstance(v, str):
                    num = _parse_human_number(v)
                    if num is not None and num > 0 and score_key(k, sub):
                        hits.append((sub, num))

                    embedded = self._try_parse_embedded_json(v)
                    if embedded is not None:
                        hits.extend(self._collect_sales_candidates(embedded, sub + "(json)"))

                hits.extend(self._collect_sales_candidates(v, sub))

        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                hits.extend(self._collect_sales_candidates(v, f"{path}[{i}]"))

        return hits

    def _extract_sales_from_html(self, html: str) -> list[tuple[str, int]]:
        hits: list[tuple[str, int]] = []
        patterns = [
            r'"(?:sale_num|sales|sold_num|buy_count|total_sales|history_sales)"\s*:\s*(\d+)',
            r"(?:已售|销量)\s*[:：]?\s*(\d+(?:\.\d+)?[万亿]?)",
        ]
        for i, p in enumerate(patterns):
            for m in re.finditer(p, html, flags=re.I):
                num = _parse_human_number(m.group(1))
                if num:
                    hits.append((f"html.pattern[{i}]", num))
        return hits

    def fetch_precise_sales(self, share_url: str) -> tuple[int, dict[str, Any]]:
        context = self.resolve_album_context(share_url)
        ids = context["ids"]
        if not ids:
            raise RuntimeError("无法从链接中解析专辑 ID，请确认链接有效。")

        album_id = ids.get("albumid") or ids.get("album_id")
        product_id = ids.get("productid") or ids.get("pid")

        candidate_payloads: list[dict[str, Any]] = []
        if album_id:
            candidate_payloads.extend(
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
            candidate_payloads.append(
                {
                    "comm": {"ct": 24, "cv": 0},
                    "req": {
                        "module": "vipmall.HallSvr",
                        "method": "GetProductInfo",
                        "param": {"productid": product_id},
                    },
                }
            )

        best: tuple[str, int] | None = None
        inspected: dict[str, Any] = {
            "ids": ids,
            "final_url": context["final_url"],
            "candidates": [],
        }

        for payload in candidate_payloads:
            try:
                data = self._musicu_call(payload)
            except Exception as exc:
                inspected["candidates"].append({"payload": payload, "error": str(exc)})
                continue

            hits = self._collect_sales_candidates(data)
            candidate_summary: dict[str, Any] = {
                "payload": payload,
                "hits": hits[:30],
            }
            if isinstance(data, dict):
                candidate_summary["top_keys"] = list(data.keys())[:10]
            inspected["candidates"].append(candidate_summary)

            for p, v in hits:
                if best is None or v > best[1]:
                    best = (p, v)

        html_hits = self._extract_sales_from_html(context["html"])
        inspected["html_hits"] = html_hits[:30]
        for p, v in html_hits:
            if best is None or v > best[1]:
                best = (p, v)

        if best is None:
            raise RuntimeError(
                "未找到可识别的销量字段。请使用 --debug 查看返回结构后补充字段映射。"
            )

        return best[1], {"source_path": best[0], **inspected}


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 QQ 音乐数字专辑精确销量")
    parser.add_argument("url", help="QQ 音乐专辑分享链接")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    args = parser.parse_args()

    crawler = QQMusicSalesCrawler()
    try:
        sales, meta = crawler.fetch_precise_sales(args.url)
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
