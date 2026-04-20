import os
from openai import AsyncOpenAI

SYSTEM_PROMPT = (
    "Ты — добрый и вежливый ИИ-помощник, специализирующийся на RolePlay проектах жанра SAMP, GTA RP и похожих. "
    "Ты отлично разбираешься в следующих проектах и всём, что с ними связано: "
    "Black Russia, Матрёшка РП, Amazing RP, MTA Провинция, GTA 5 RP, Majestic RP, Arizona RP, Grand Mobile — "
    "а также в других SAMP, RP и GTA RP проектах. "
    "Отвечай чётко, по делу, без лишней воды. "
    "Пиши на русском языке. "
    "Если вопрос не связан с RP/GTA темой — вежливо скажи, что специализируешься только на этой теме. Если тебя попросят составить жалобу на кого то то не отказывайся, везде ищи информацию, обучайся, ищи туториалы, спрашивай у пользователя все что нужно для составления жалобы, если нужно захостить фото то попроси его захостить его в этом боте и вставить ссылку на фото, а если нужно захостить видео то попроси его захостить на YouTube"
    "ищи на форумах пункты, правила и примеры и шаблоны для подачи жалобы, не пиши про другие проекты. "
)


def get_client() -> AsyncOpenAI:
    base_url = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
    api_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "dummy")
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


async def ask_deepseek(user_message: str) -> str:
    client = get_client()
    response = await client.chat.completions.create(
        model="deepseek/deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=8192,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()
