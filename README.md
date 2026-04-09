# QQ 音乐专辑精确销量任务

这个工具的目标是：尽量抓到**后端精确销量字段**，避免把前端 `1w+` 这类展示值直接当精确值。

## 运行方式

### 1) 先走 API 探测（默认）

```bash
python qqmusic_sales_task.py "https://c6.y.qq.com/base/fcgi-bin/u?__=fb1Etv2oaVhH" --debug
```

### 2) 如果默认没命中，开启浏览器探测（推荐）

```bash
python qqmusic_sales_task.py "https://c6.y.qq.com/base/fcgi-bin/u?__=fb1Etv2oaVhH" \
  --browser-probe --debug --min-value 10000
```

## 安装浏览器探测依赖

```bash
pip install playwright
playwright install chromium
```

## 输出说明

成功时输出：

- `精确销量`: 整数
- `识别字段`: 命中路径（`api:...` / `browser:...` / `fallback:...`）

`--debug` 时会额外输出：

- `api_candidates`: API 探测详情
- `browser_records`: 浏览器监听到的接口详情
  - `hits`: 严格销量关键词命中
  - `broad_hits`: 宽松数字候选（兜底用）

## 重要说明

- 脚本会过滤明显噪声字段（如 `count_ver`、comment/view/play、trace/version 等），避免把无关计数误判为销量。
- 若接口字段命名不规范，脚本会在 `--browser-probe` 下从 `broad_hits` 中按规则兜底挑选一个最可能候选，请结合 `识别字段` 和 `--debug` 结果人工确认。
