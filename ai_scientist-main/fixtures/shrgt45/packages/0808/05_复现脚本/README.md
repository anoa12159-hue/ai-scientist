# 复现入口说明

从交付包根目录运行以下脚本：

```powershell
python -B 05_复现脚本\build_demo_visualizations.py
python -B 05_复现脚本\reproduce_fullinfo_package.py
python -B 05_复现脚本\finalize_fullinfo_delivery_20260808.py
```

`build_demo_visualizations.py` 从 `03_结果数据/` 生成 `04_图表/visualizations/` 中的六张图和质量指标。`reproduce_fullinfo_package.py` 只读取包内的事件输入与缓存 JSON，在临时目录中重建数值链，并把 SHA256 比对结果写入 `06_审计与交付/reproduction_log.txt`。`finalize_fullinfo_delivery_20260808.py` 更新 manifest、SHA256 清单与验收检查，并生成包外同名 ZIP。

严格前推审计的脚本和复现材料位于 `03_结果数据/09_严格对照审计/05_复现脚本/`；它们只使用该目录封存的 NCEI 目录、JSOC 80 小时 JSON 和派生审计表，不读取主 Demo 的结果指标来选择时间点。

`其他脚本/` 保存离线复现所调用的底层重建逻辑。日常核对只需要运行前三个入口脚本，不需要直接运行其中的文件。
