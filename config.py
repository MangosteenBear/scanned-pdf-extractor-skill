"""用户可调参数"""
from dataclasses import dataclass


# 支持的模型提供商
# provider="anthropic" : Claude 模型，使用 ANTHROPIC_API_KEY
# provider="openai"    : GPT-4o 等，使用 OPENAI_API_KEY
# provider="google"    : Gemini，使用 GOOGLE_API_KEY
SUPPORTED_PROVIDERS = ("anthropic", "openai", "google")

# 各提供商默认模型
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "google": "gemini-2.0-flash",
}

# 各提供商 API Key 环境变量名
API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}

# 各提供商参考定价（USD / 1M tokens，仅用于费用估算）
PROVIDER_PRICING = {
    "anthropic": {"in": 3.0, "out": 15.0},   # claude-sonnet-4-6
    "openai":    {"in": 2.5, "out": 10.0},   # gpt-4o
    "google":    {"in": 0.35, "out": 1.05},  # gemini-2.0-flash
}


@dataclass
class ExtractorConfig:
    # 模型提供商与模型名
    provider: str = "anthropic"           # anthropic / openai / google
    model: str = ""                       # 空则使用 DEFAULT_MODELS[provider]
    max_tokens: int = 8000

    # 渲染
    analyze_dpi: int = 150
    extract_dpi: int = 200

    # 分析阶段抽样页数
    analyze_sample_pages: int = 9

    # 滑动窗口
    window_size: int = 5
    window_overlap: int = 1

    # 图像压缩（长边上限，px）
    max_image_long_edge: int = 1500

    # 成本控制
    use_batch: bool = False     # 仅 Anthropic 支持 Batch API
    max_cost_usd: float = 30.0

    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS.get(self.provider, "claude-sonnet-4-6")

    def pricing(self) -> dict:
        return PROVIDER_PRICING.get(self.provider, PROVIDER_PRICING["anthropic"])


DEFAULT = ExtractorConfig()
