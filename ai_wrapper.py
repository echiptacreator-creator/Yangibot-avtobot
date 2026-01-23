import os
from openai import AsyncOpenAI

# 1️⃣ OpenAI kalitni olamiz
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


# 2️⃣ XAVFSIZ AI FUNKSIYA
async def generate_ai_posts(prompt: str, count: int = 5) -> list[str]:
    """
    🔒 Xavfsiz AI generator
    - hech qachon exception tashlamaydi
    - har doim list qaytaradi
    """

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen o‘zbek tilida tabiiy yozadigan shafyorsan."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_tokens=900,
        )
    except Exception as e:
        print("❌ OPENAI ERROR:", e)
        return []

    if not response or not response.choices:
        return []

    text = response.choices[0].message.content
    if not text:
        return []

    # 3️⃣ Postlarni bo‘lamiz
    blocks = [
        b.strip()
        for b in text.split("\n\n")
        if len(b.strip()) > 80
    ]

    return blocks[:count]
