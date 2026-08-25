# SHRGT45 机制小结

SHRGT45（Fraction of Area with Shear > 45°）是 SDO/HMI 卫星 SHARP 数据产品的衍生参数之一，定义为活动区内剪切角超过 45° 的像素面积占总有效像素面积的比值 [1]。其中，剪切角为光球层实测三维矢量磁场与以光球法向场为边界条件导出的势场之间的空间夹角 [1]。势场是给定边界条件下能量最低的磁场位形，剪切角越大，实际磁场偏离这一最低能态越远。以 45° 为阈值，沿袭自 Falconer et al. (2008) 将剪切角 > 45° 定义为强剪切的惯用判据 [2]。SHRGT45 因此量度的是活动区中强非势性区域的空间覆盖范围——强剪切区域占比越大，活动区整体非势性越强，储存的磁自由能越多。

非势性与耀斑的关联在于：耀斑能量以磁自由能的形式预先储存，自由能来源于磁场的非势性 [3]。观测上，日冕呈非势性的活动区耀斑发生频率为近势场活动区的 2.4 倍，X 射线峰值耀斑亮度高出 3.3 倍 [4]——需注意此为日冕非势性数据，并非 SHRGT45 的直接结论，此处作为"非势性→耀斑活性"物理逻辑的间接旁证。flare-productive 活动区频繁显示出 δ 型黑子、剪切极性反转线和磁绳等特征 [3]，所有大耀斑均与高梯度、强剪切的极性反转线相关联 [5]。

活动区磁场的非势性主要来源于磁通浮现——磁通量管从太阳内部穿过光球表面冒出，天然携带剪切与扭曲。但浮现并非自由能注入的唯一途径：Schrijver et al. (2005) 指出携能的电流同样可通过光球表面的剪切流或磁对消产生，但驱动耀斑活性增强或日冕非势性的前提是伴随约 30 小时内的复杂动态磁通浮现 [4]，前者正是 SHRGT45 所捕捉的信息。进一步地，Kutsenko et al. (2024) 对 100 个 M5.0 级及以上耀斑活动区的统计表明，11% 的活动区属于 IV 型（完全无可检测的磁通浮现），却仍产生了包括 X14.4、X17.0 级在内的强耀斑，且此类活动区均以强剪切结构为特征 [6]。换言之，磁通浮现对于强耀斑的产生既非必要条件也非充分条件——决定耀斑潜力的直接因素是磁场当前的自由能状态，而非该状态的历史成因。SHRGT45 作为这一状态量的光球层度量，具有相对独立于浮现的价值。

尽管有上述关联，SHRGT45 作为单参数存在两个层面的局限。统计层面，Leka & Barnes (2007) 对 496 个活动区的 1212 幅矢量磁图分析表明，没有任何单一光球参数能完全可靠地区分耀斑与非耀斑活动区——两群体的参数分布存在显著重叠 [7]。物理层面，SHRGT45 是光球单层量，而耀斑的触发发生在日冕。Zou et al. (2019) 对 66 例产生高速 CME 的暗条爆发统计表明，触发机制可分为两类：磁重联触发和理想 MHD 不稳定性触发 [8]。两类触发涉及的是日冕磁场的三维拓扑结构——上覆场的衰减指数、磁绳的扭缠程度、四极场位形下的重联位置——这些信息不包含在光球单层的剪切角测量中。所以，SHRGT45 可以衡量自由能的，但无法触及自由能"如何释放、何时释放"的问题 [8]。

综上，SHRGT45 的升高关联非势性与自由能积累，由此提出可检验假设：SHRGT45 在耀斑爆发前 3–6 小时内的异常升高，与随后 M 级及以上耀斑的发生存在统计上的显著关联。


[1] Bobra M G, Sun X, Hoeksema J T, et al. The Helioseismic and Magnetic Imager (HMI) Vector Magnetic Field Pipeline: SHARPs – Space-Weather HMI Active Region Patches [J]. Solar Physics, 2014, 289: 3549–3578.

[2] Falconer D A, Moore R L, Gary G A. Magnetogram Measures of Total Nonpotentiality for Prediction of Solar Coronal Mass Ejections from Active Regions of Any Degree of Magnetic Complexity [J]. The Astrophysical Journal, 2008, 689: 1433–1442.

[3] Toriumi S, Wang H. Flare-productive Active Regions [J]. Living Reviews in Solar Physics, 2019, 16: 3.

[4] Schrijver C J, DeRosa M L, Title A M, Metcalf T R. The Nonpotentiality of Active-Region Coronae and the Dynamics of the Photospheric Magnetic Field [J]. The Astrophysical Journal, 2005, 628: 501–513.

[5] Schrijver C J. A Characteristic Magnetic Field Pattern Associated with All Major Solar Flares and Its Use in Flare Forecasting [J]. The Astrophysical Journal Letters, 2007, 655: L117–L120.

[6] Kutsenko A S, Abramenko V I, Plotnikov A A. A Statistical Study of Magnetic Flux Emergence in Solar Active Regions Prior to Strongest Flares [J]. Research in Astronomy and Astrophysics, 2024, 24: 045014.

[7] Leka K D, Barnes G. Photospheric Magnetic Field Properties of Flaring versus Flare-quiet Active Regions. IV. A Statistically Significant Sample [J]. The Astrophysical Journal, 2007, 656: 1173–1186.

[8] Zou P, Jiang C, Wei F, Zuo P, Wang Y. A Statistical Study of Solar Filament Eruptions that Form High-speed Coronal Mass Ejections [J]. The Astrophysical Journal, 2019, 884: 157.
