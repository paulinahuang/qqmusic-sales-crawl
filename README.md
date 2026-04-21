# QQ Music Exact Sales Crawling Project
This warehouse provides a directly executable task script: Input the sharing link of the QQ music album, automatically parse the album ID, and attempt to call the public interface of QQ music to retrieve the "precise sales figures". 
## Operating Mode 
```bash
python qqmusic_sales_task.py "https://c6.y.qq.com/base/fcgi-bin/u?__=fb1Etv2oaVhH" --debug
```

After success, the following message will be displayed: 
- `Precise Sales Volume`: Integer sales volume (e.g. `15000`)
- `Identification Field`: The path of the matched interface field (for facilitating subsequent troubleshooting) 
## Script Description 
The script accomplished three things: 
1. Follow the sharing short link redirection and parse `albumid/productid`.
2. Combine multiple sets of `musicu.fcg` requests (such as `GetDigitalAlbumDetail`, `GetDigitalAlbumInfo`, `GetProductInfo`).
3. Recursively retrieve the fields related to sales (such as `sale/sold/buy/count/num`) in the returned JSON and select the most reliable integer value. 
## Jay Chou Example (The link provided) 
According to public reports, the album "The Greatest Works" had a total final sales volume of approximately **7.25 million copies** (that is, 7,250,000). 
Note: This is the result from an open report and does not represent the actual real-time sales figures when you run the script; the real-time sales figures should be based on the returned values captured by the interface.
