# 2026-10-02 — EPG 名称对齐 (v0.6.4)

将频道显示名与订阅导出的 `tvg-id` / `tvg-name` 对齐到
https://epg.zsdc.eu.org/t.xml.gz ，便于播放器匹配节目单。

## 显示名

- 央视：`CCTV1` … `CCTV17`、`CCTV5+`、`CCTV4K`（不再使用「CCTV-1 综合」等带副标题形式）
- 卫视：保持 `湖南卫视` 等与 EPG 一致
- 其他：内置 EPG 频道表（凤凰、CGTN、CHC、金鹰卡通、欢笑剧场等），别名映射到主 id

## 导出

- M3U / CLI 导出：`tvg-id` 与 `tvg-name` 使用 EPG 显示名，不再使用内部 key（如 `cctv-1`）
- `group-title` 仍按规则：`央视` / `卫视` / `其他`（EPG 本身无分组）

## 存量数据

- 启动时 `refresh_epg_names` 会刷新已有频道的 `display_name` 与 `group_name`
- 内部 `channel.id` 不变，测试结果与源归属不受影响
