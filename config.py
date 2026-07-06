"""用户可调参数"""
from dataclasses import dataclass, field


@dataclass
class ExtractorConfig:
    # 模型
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8000

    # 渲染
    analyze_dpi: int = 150       # 分析阶段用低分辨率（省 token）
    extract_dpi: int = 200       # 提取阶段

    # 分析阶段：抽样页数（从首/中/尾各取）
    analyze_sample_pages: int = 9

    # 滑动窗口
    window_size: int = 5
    window_overlap: int = 1

    # 图像压缩
    max_image_long_edge: int = 1500   # 提取阶段；分析阶段用 800

    # 成本控制
    use_batch: bool = False
    max_cost_usd: float = 30.0

    # 定价（sonnet-4-6）
    price_in: float = 3.0
    price_out: float = 15.0
    batch_mult: float = 0.5


DEFAULT = ExtractorConfig()
