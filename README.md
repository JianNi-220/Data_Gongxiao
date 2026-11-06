# 供销志：县级年度肥料表格数据

从用户提供的《供销志》截图中抽取氮肥、磷肥、钾肥和复合肥年度数量，为后续研究大型化肥厂开工的影响准备数据。当前范围是表格，正文中的数字不进入年度数据。

## 本轮结果

1,998张截图全部完成OCR，共210,873条识别记录，13张空识别截图经左右页裁切补回。结构化长表共8,788条单元格记录（其中8,622条有数字），来自165个来源目录；其中390格逐格查看截图核对（269个数字、121个原表空白）。其余8,398条保留为未核验OCR候选。

379张截图存在对齐年份但目标表头或版式未解析，需复核；其中可能仅有化肥合计或其他商品，不能据此认定全部是漏取目标肥料。4,041条记录的单位尚未明确，7,942条的实物/折纯/折标口径未明确。本轮属于首轮抽取，尚未完成所有县、所有表格的逐格校验。抽取目标为表格中的年度数量，不抽取正文数字；已识别的价格、金额、占比及错列问题用排除及修正清单处理。未核验候选仍需对照原图。

## 数据口径

- 保留原始品名、县名、年份、单位、业务口径和截图定位。销售、供应、购进、生产、施用分别记录。
- 实物量与折纯量分别记录；没有养分含量时不推算纯氮量。
- 氮肥分项（如尿素、碳铵、硫铵、氨水）保留品名，不与氮肥小计重复汇总。
- 原表空白、破折号和无法识别的数字不补零。多年合计不拆为年度数据。
- OCR 结果保留核验状态。模型置信度不代表数字已经人工核对。

## 来源

输入为 `供销志.zip`，完整性校验通过，包含 1,998 张 PNG 截图，29 个省级目录。`data/source_manifest.csv` 记录原始相对路径、尺寸、文件大小和 SHA-256，可据此找到并校验原图。原始截图约 2.5 GB，由本地原始压缩包保管；仓库存放抽取数据、OCR 记录、来源索引和可复现脚本。

## 后续 DID

参见 [研究设计说明](docs/did_design.md)。当前未提供大型化肥厂的清单、产能、坐标和开工/投产时点，不生成处理变量或因果估计。其他肥料可以作为比较结果，但其不受替代和供给溢出影响需要验证；复合肥可能含氮。

## 文件

| 文件 | 用途 |
| --- | --- |
| `data/annual_fertilizer.csv` | 合并视觉核对记录后的年度长表，包含核验状态和定位 |
| `data/fertilizer_review.xlsx` | 方便筛选的年度数量表及全部截图覆盖索引 |
| `data/fertilizer_candidates.csv` | 原始机器候选阶段，避免与年度长表重复相加 |
| `data/reviewed_cells.csv` | 已逐格查看截图的值和空白格，附核对说明 |
| `data/image_coverage.csv` | 1,998 张截图逐张记录识别、排除或待复核状态 |
| `data/source_manifest.csv` / `archive_info.json` | 原图索引、文件和压缩包校验值 |
| `data/manual_exclusions.csv` | 经查看原图确认的价格/百分比页面排除清单 |
| `data/cell_exclusions.csv` / `source_metadata_overrides.csv` | 已确认错列的单元格排除及表格单位、业务口径修正 |
| `data/source_geography_overrides.csv` | 按表名确认的县名修正，保留原始目录名称 |
| `ocr/observations.jsonl.gz` | 全部截图的原始 OCR 文字、置信度和坐标 |
| `docs/data_dictionary.md` | 字段定义、单位换算和重复处理说明 |
| `docs/visual_review.json` | 抽查发现的具体问题及来源 |
| `data/factories_template.csv` | 后续合并工厂开工/投产与空间信息的空模板 |

## 复现

提取和整理阶段仅使用 Python 标准库；本次 OCR 使用 macOS 自带 Apple Vision（简体中文与英文、准确模式、关闭语言纠错），在本机处理原图。需要 macOS、Swift 编译器和原始压缩包。Apple Vision 不同系统版本的结果可能有差异；本次识别结果已完整留存。

```bash
python3 scripts/prepare_sources.py /path/to/供销志.zip raw build/manifest.json
mkdir -p build/module_cache build/ocr
swiftc -module-cache-path build/module_cache -O scripts/ocr.swift -o build/ocr_binary
build/ocr_binary build/manifest.json build/ocr 4
python3 scripts/ocr_fallback.py prepare build/manifest.json build/ocr build/fallback
build/ocr_binary build/fallback/crop_manifest.json build/fallback/crop_ocr 4
python3 scripts/ocr_fallback.py merge build/manifest.json build/ocr build/fallback
python3 scripts/check_ocr.py build/manifest.json build/ocr
python3 scripts/extract_tables.py build/manifest.json build/ocr build/candidates --exclusions data/manual_exclusions.csv
python3 scripts/package_data.py build/manifest.json build/candidates build/ocr .
python3 scripts/test_extract_tables.py
```

OCR 会跳过已成功保存的截图，错误记录会重试。程序不会自动解决所有跨页表头、缩写年份、倾斜/复杂表格及数字粘连；待复核页面保留在覆盖索引中。当前结果属于全量 OCR 后的首轮结构化抽取，不能直接视为所有县、所有年份均已完成核验的平衡面板。

空识别补救脚本使用 Pillow 裁成左右半页，随后用同一 OCR 重新识别并还原坐标；运行前需安装 `Pillow`（`python3 -m pip install pillow`）。本次有13张截图经此步骤补回。原始截图不被修改。
