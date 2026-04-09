# QQ 音乐专辑精确销量任务

这个仓库提供了一个可直接运行的任务脚本：输入 QQ 音乐专辑分享链接，自动解析专辑 ID，并尝试调用 QQ 音乐公开接口抓取“精确销量数字”。

## 运行方式

```bash
python qqmusic_sales_task.py "https://c6.y.qq.com/base/fcgi-bin/u?__=fb1Etv2oaVhH" --debug
```

成功后会输出：

- `精确销量`：整数销量（例如 `15000`）
- `识别字段`：命中的接口字段路径（便于后续排查）

## 脚本说明

脚本做了四件事：

1. 跟随分享短链跳转，解析 `albumid/productid`。
2. 组合多组 `musicu.fcg` 请求（`GetDigitalAlbumDetail` / `GetDigitalAlbumInfo` / `GetProductInfo`）。
3. 在返回 JSON 中递归检索销量字段，支持整数、浮点、字符串数字，以及 `1.5万/725万+` 这类格式。
4. 如果接口结果缺字段，会回退到分享页 HTML 做二次提取（`sale_num/sold_num/buy_count/history_sales` 等）。

## 调试建议

如果仍然报“未找到可识别的销量字段”，请执行：

```bash
python qqmusic_sales_task.py "<你的链接>" --debug > debug.json
```

然后检查：

- `candidates[].hits`
- `candidates[].top_keys`
- `html_hits`

你可以据此把新增字段名补到脚本的关键词或显式映射里。
