# 字段和使用方法

`data/annual_fertilizer.csv` 是长表：一行对应一个截图中的某年某肥料品名的表格单元格。`data/fertilizer_candidates.csv` 保留未经核对覆盖的机器抽取阶段。两者不能拼接相加。表格有分项时，一个县一年可以有多条同类别记录。

| 字段 | 含义 |
| --- | --- |
| `record_id` | 单元格记录标识，不是县级编码 |
| `province` | 压缩包中的省级目录原文 |
| `source_location` | 县志/供销志来源目录原文，可能是县、市、州或乡镇 |
| `county_raw` | 从目录可辨认的历史县/区/市名。未经行政区划代码或县界统一 |
| `geography_level` | 名称层面的初步分类，`city_level_unresolved` 表示尚不能判断地级市或县级市 |
| `year` | 原表年度，不使用截图创建日期 |
| `fertilizer_group` | `N` 氮肥；`P` 磷肥；`K` 钾肥；`compound` 复合/混合肥 |
| `product_label` | 表头/行名中的原始肥料品名。保留尿素、碳铵、固体氮肥、氨水等分项 |
| `quantity_raw` | 数字识别原文；补充的视觉抄录记录为抄录值 |
| `quantity_ocr` | 人工/视觉核对覆盖之前的机器数值，方便检查改动 |
| `quantity` | 数值或空值。空值不表示零 |
| `value_status` | `reported_ocr` 为未核对数字；`reported` 为已核对报告值；`blank_in_source` 为原表空白；`source_missing_symbol` 为原表缺失符号；`unresolved_ocr` 为粘连等原因无法确认数字 |
| `unit` | 原表重量单位。无法确定时留空 |
| `quantity_tonnes` | 按明确重量单位转换为吨；不进行养分含量折算 |
| `measurement_basis` | `physical` 实物量；`nutrient` 折纯/养分量；`standard_equivalent` 标准肥/折标；`unknown` 未明确 |
| `measure_type` | `sales` 销售，`supply` 供应，`purchases` 购进，`use` 施用/使用，`production` 生产，`unknown` 未明确 |
| `source_id` / `source_path` | 来源截图标识和压缩包内相对路径，对照 `source_manifest.csv` |
| `table_orientation` | 年份在行或在列 |
| `year_bbox` / `header_bbox` / `value_bbox` | `[x,y,width,height]`，0–1 标准化坐标，原点在截图左下角 |
| `ocr_confidence` | OCR 返回的识别分值；高分不保证数字、列归属或计量口径正确 |
| `review_status` | `ocr_candidate` 为机器候选；`visually_checked` 为已逐格查看截图的记录 |
| `review_flags` | 分号分隔的具体问题，包括单位不明、计量口径不明、数字/表头拆分、跨列数字等 |
| `review_note` / `metadata_source_id` / `printed_page` | 视觉核对说明、确认单位与口径的截图、可辨认的印刷页码 |

## 来源覆盖和复核

`data/image_coverage.csv` 为全部输入截图逐张列出状态。有候选数据不代表整张表已完整识别。`annual_table_header_or_layout_unresolved` 表示存在对齐的年份但未成功提取目标列，需要查看原图；这类页面也可能只有化肥总量或其他商品。`no_short_fertilizer_labels` 和 `no_supported_annual_table_layout` 是程序结果，不等于已经人工确认没有相关数据。

`ocr/observations.jsonl.gz` 保留全部截图的文字、置信度和坐标，包括用于判断表头与上下文的正文识别。年度数量数据只取表格，不从正文抽取数字。每行是一个截图的 JSON，可以用 Python 的 `gzip.open(..., 'rt')` 读取。

抽查发现相邻单元格会被识别为8–14位连续整数。跨越多个已识别肥料列的数字，以及8位以上的连续整数，都保留识别原文并暂时将数量置空，标记复核。这是针对数字粘连的复核规则，不代表真实数量存在统一上限。

显示原图定位框时，左上像素坐标为 `left=x*W`、`top=(1-y-height)*H`，其中 `W,H` 为原图宽高。视觉抄录新增的缺失格可能没有 OCR 定位框，使用来源页和品名定位。

## 汇总前的限制

只使用需要的业务口径与实物/折纯口径。不要把省、州、乡镇记录当作县。不要将总计与分项相加，不将固体氮肥当作包含氨水的氮肥总量。不同来源的重叠年份应先核对统计范围，再处理重复或冲突。价格表、比例表、化肥合计、农药等不进入目标数量数据；识别器未能识别的表仍在覆盖索引和 OCR 中保留。

单位换算采用：吨=1吨，万吨=10000吨，千吨=1000吨，市担/担=0.05吨，公担/百公斤=0.1吨，公斤/千克=0.001吨，市斤/斤=0.0005吨。历史特殊单位或换算制度需对照原书再确认。

另支持万公斤/万千克=10吨、万市担/万担=500吨、万市斤/万斤=5吨、百吨=100吨、百担=5吨、千担=50吨。折算吨仍保留原计量口径，标准肥不能与实物量或纯养分量直接相加。
