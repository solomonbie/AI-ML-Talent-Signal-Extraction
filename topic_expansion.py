"""
topic_expansion.py

A small, hand-curated map of closely related terms for common AI/ML
topics. This is deliberately NOT AI-generated or automatic — every entry
here was chosen by a person, so the search stays predictable and free.
Extend this dict yourself as you find gaps; it's just plain data.
"""

TOPIC_EXPANSIONS = {
    "rlhf": ["ppo", "dpo", "constitutional ai"],
    "reinforcement learning from human feedback": ["rlhf", "dpo"],
    "rag": ["retrieval augmented generation"],
    "retrieval augmented generation": ["rag"],
    "llm quantization": ["gptq", "qlora"],
    "quantization": ["gptq", "qlora", "awq"],
    "vision transformers": ["vit", "swin transformer"],
    "diffusion models": ["stable diffusion", "ddpm"],
    "speculative decoding": ["medusa decoding", "draft model"],
    "mixture of experts": ["moe", "sparse moe"],
    "moe": ["mixture of experts"],
    "model distillation": ["knowledge distillation"],
    "lora": ["qlora", "low rank adaptation"],
    "prompt engineering": ["in-context learning", "chain of thought"],
    "agentic ai": ["ai agents", "tool use llm"],
}


def expand_topic(topic, max_extra=2):
    """
    Returns up to `max_extra` closely related search terms for a topic,
    or an empty list if there's no curated entry for it. Never guesses —
    an unrecognized topic just returns nothing extra.
    """
    key = topic.strip().lower()
    related = TOPIC_EXPANSIONS.get(key, [])
    return related[:max_extra]
