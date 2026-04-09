# QQ 音乐专辑精确销量任务

这个工具的目标是：**只返回精确销量字段**，不把前端 `1w+` 这类近似展示值当成精确值。

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

> `--browser-probe` 会启动 Playwright，监听网页端真实 `XHR/fetch` 返回，通常比手写猜 API 更可靠。

## 安装浏览器探测依赖

```bash
pip install playwright
playwright install chromium
```

## 输出说明

成功时输出：

- `精确销量`: 整数（来自接口真实字段）
- `识别字段`: 命中路径（`api:...` 或 `browser:<url>::...`）

`--debug` 时会额外输出：

- `api_candidates`: 默认 API 探测详情
- `browser_records`: 浏览器监听到的真实接口及命中字段

## 重要说明

- 脚本只接受**纯数字或数字型字段**作为精确销量候选。像 `1w+`、`1.5万` 这类展示值不会被当作最终结果。
- 脚本会过滤明显噪声字段（如 `count_ver`、评论计数、trace/version 等），避免把非销量数字误判为销量。
- 如果你看到“未找到精确销量字段”，一般表示需要打开 `--browser-probe` 并查看 `browser_records` 中的实际返回结构。
