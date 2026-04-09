#!/usr/bin/env python3
"""QQ 音乐数字专辑销量抓取任务。

用法:
    python qqmusic_sales_task.py "https://c6.y.qq.com/base/fcgi-bin/u?__=fb1Etv2oaVhH"
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


class QQMusicSalesCrawler:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def _get_text(self, url: str) -> tuple[str, str]:
        req = Request(url, headers={"User-Agent": UA, "Referer": "https://y.qq.com/"})
        with urlopen(req, timeout=self.timeout) as resp:
            final_url = resp.geturl()
            text = resp.read().decode("utf-8", errors="ignore")
            return final_url, text

    def resolve_album_ids(self, share_url: str) -> dict[str, int]:
        final_url, html = self._get_text(share_url)
        ids: dict[str, int] = {}

        def add_from_text(label: str, text: str) -> None:
            for pattern in [
                rf"{label}[=:\"']+(\d+)",
                rf"\"{label}\"\s*:\s*(\d+)",
            ]:
                m = re.search(pattern, text, re.I)
                if m:
                    ids[label] = int(m.group(1))
                    return

        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        for key in ("albumid", "albummid", "productid", "id"):
            if key in qs and qs[key] and qs[key][0].isdigit():
                ids[key] = int(qs[key][0])

        for key in ("albumid", "productid", "pid", "album_id"):
            add_from_text(key, final_url)
            add_from_text(key, html)

        if "albumid" not in ids:
            m = re.search(r"/album/(\d+)", final_url)
            if m:
                ids["albumid"] = int(m.group(1))

        return ids

    def _musicu_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = urlencode({"format": "json", "data": json.dumps(payload, ensure_ascii=False)})
        api = f"https://u.y.qq.com/cgi-bin/musicu.fcg?{encoded}"
        _, text = self._get_text(api)
        return json.loads(text)

    def _find_sales_like_fields(self, obj: Any, path: str = "") -> list[tuple[str, int]]:
        hits: list[tuple[str, int]] = []
        sale_keys = (
            "sale",
            "sell",
            "sold",
            "buy",
            "count",
            "total",
            "num",
            "volume",
            "销量",
        )
        if isinstance(obj, dict):
            for k, v in obj.items():
                sub = f"{path}.{k}" if path else k
                if isinstance(v, int) and any(word in k.lower() for word in sale_keys) and v > 0:
                    hits.append((sub, v))
                hits.extend(self._find_sales_like_fields(v, sub))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                hits.extend(self._find_sales_like_fields(v, f"{path}[{i}]"))
        return hits

    def fetch_precise_sales(self, share_url: str) -> tuple[int, dict[str, Any]]:
        ids = self.resolve_album_ids(share_url)
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
        inspected: dict[str, Any] = {"ids": ids, "candidates": []}

        for payload in candidate_payloads:
            try:
                data = self._musicu_call(payload)
            except Exception as exc:
                inspected["candidates"].append({"payload": payload, "error": str(exc)})
                continue

            hits = self._find_sales_like_fields(data)
            inspected["candidates"].append({"payload": payload, "hits": hits[:20]})
            for p, v in hits:
                if best is None or v > best[1]:
                    best = (p, v)

        if best is None:
            raise RuntimeError(
                "未找到可识别的销量字段。可能是接口字段变更、风控限制，或需要登录 Cookie。"
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
