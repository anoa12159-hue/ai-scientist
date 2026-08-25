# SHRGT45 全信息基准版 Demo QUALITY 处理规则

本表记录本次 Demo 的 QUALITY 位掩码处理方式。`0x80000000`、`0x40000000` 及二者的组合 `0xC0000000` 作为致命位，从相应帧和历史窗中排除；其他非零值保留原始十六进制值，并标记为 `NONZERO_RETAINED_PROVISIONAL`。

官方依据采用 HMI QUALITY 表和 JSOC/SHARP 文档入口：

- Hoeksema et al., HMI vector magnetic field pipeline / HMI QUALITY tables: https://link.springer.com/article/10.1007/s11207-014-0516-8
- JSOC SHARP 文档入口: https://jsoc.stanford.edu/doc/data/hmi/sharp/old/sharp.MB.htm

`0x00010400`、`0x00000400` 的精确 SHARP-level 含义在表中保持“待定位”状态；对应记录保留，便于结合官方 bit 位置继续核对。
