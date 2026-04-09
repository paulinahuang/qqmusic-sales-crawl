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

脚本做了三件事：

1. 跟随分享短链跳转，解析 `albumid/productid`。
2. 组合多组 `musicu.fcg` 请求（`GetDigitalAlbumDetail` / `GetDigitalAlbumInfo` / `GetProductInfo`）。
3. 在返回 JSON 中递归检索与销量相关的字段（如 `sale/sold/buy/count/num`），选取最可信的整数值。

## 周杰伦示例（你给的链接）

基于公开报道，《最伟大的作品》这张专辑“最终总销量约 **725 万张**”（即 `7250000`）。

> 注意：这是公开报道中的结果，不代表你运行脚本时的实时销量；实时销量应以接口抓到的返回值为准。
