"""统一 API 客户端

屏蔽不同提供商的 SDK 差异，对外暴露统一的 create_message() 接口。
支持 Anthropic / OpenAI / Google Gemini。
"""
import json
import os
from typing import Any

from config import API_KEY_ENV, ExtractorConfig


def _check_api_key(provider: str) -> str:
    env = API_KEY_ENV.get(provider)
    key = os.environ.get(env, "")
    if not key:
        raise ValueError(
            f"API key not found. Set the {env} environment variable "
            f"or pass --api-key when using the CLI."
        )
    return key


def create_message(
    system: str,
    user_content: list[dict],
    cfg: ExtractorConfig,
    json_schema: dict[str, Any],
) -> list[dict]:
    """
    调用模型，返回提取结果列表。

    Args:
        system:       系统 prompt 字符串
        user_content: 用户消息的 content 列表（文本 + 图片块）
        cfg:          ExtractorConfig
        json_schema:  期望的 JSON 输出 schema

    Returns:
        list[dict]，对应 schema 中 "items" 数组的内容
    """
    provider = cfg.provider
    model = cfg.resolved_model()
    _check_api_key(provider)

    if provider == "anthropic":
        return _call_anthropic(system, user_content, cfg, model, json_schema)
    elif provider == "openai":
        return _call_openai(system, user_content, cfg, model, json_schema)
    elif provider == "google":
        return _call_google(system, user_content, cfg, model, json_schema)
    else:
        raise ValueError(f"Unsupported provider: {provider}. Choose from: anthropic, openai, google")


def _call_anthropic(system, user_content, cfg, model, json_schema):
    import anthropic
    client = anthropic.Anthropic()

    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    msg = client.messages.create(
        model=model,
        max_tokens=cfg.max_tokens,
        system=system_blocks,
        thinking={"type": "disabled"},
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": json_schema},
        },
        messages=[{"role": "user", "content": user_content}],
    )
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text).get("items", [])
    return []


def _call_openai(system, user_content, cfg, model, json_schema):
    from openai import OpenAI
    client = OpenAI()

    # 把 anthropic 格式的 content 转成 OpenAI 格式
    oai_content = []
    for block in user_content:
        if block["type"] == "text":
            oai_content.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image":
            src = block["source"]
            oai_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"},
            })

    response = client.chat.completions.create(
        model=model,
        max_tokens=cfg.max_tokens,
        response_format={"type": "json_schema", "json_schema": {"name": "extraction", "schema": json_schema}},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": oai_content},
        ],
    )
    text = response.choices[0].message.content or "{}"
    return json.loads(text).get("items", [])


def _call_google(system, user_content, cfg, model, json_schema):
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get(API_KEY_ENV["google"]))

    gemini = genai.GenerativeModel(
        model_name=model,
        system_instruction=system,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=json_schema,
            max_output_tokens=cfg.max_tokens,
        ),
    )

    # 把 content 块转成 Gemini 格式
    import base64
    parts = []
    for block in user_content:
        if block["type"] == "text":
            parts.append(block["text"])
        elif block["type"] == "image":
            src = block["source"]
            parts.append({
                "mime_type": src["media_type"],
                "data": base64.b64decode(src["data"]),
            })

    response = gemini.generate_content(parts)
    return json.loads(response.text).get("items", [])


def estimate_cost(usage: dict, cfg: ExtractorConfig) -> float:
    """估算单次调用成本（USD）。"""
    pricing = cfg.pricing()
    m = cfg.batch_mult if cfg.use_batch and cfg.provider == "anthropic" else 1.0
    in_tok = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    c_read = usage.get("cache_read_input_tokens", 0)
    c_write = usage.get("cache_creation_input_tokens", 0)
    cost = (
        in_tok * pricing["in"]
        + c_read * pricing["in"] * 0.1
        + c_write * pricing["in"] * 1.25
        + out_tok * pricing["out"]
    ) / 1_000_000
    return cost * m
