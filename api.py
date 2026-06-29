import openai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

openai.api_key = os.environ.get("OPENAI_API_KEY", "")

SIGNATURES = {
    "Nathaniel Pouliot": {
        "english": "Best regards,\nNathaniel Pouliot\n\n1055 Rue Lucien-L'Allier\nMontreal, QC H3G 3C4\nCanada",
        "french": "Cordialement,\nNathaniel Pouliot\n\n1055 Rue Lucien-L'Allier\nMontreal, QC H3G 3C4\nCanada",
    },
    "Mathys Gagnon": {
        "english": "Best regards,\nMathys Gagnon\n\n1055 Rue Lucien-L'Allier\nMontreal, QC H3G 3C4\nCanada",
        "french": "Cordialement,\nMathys Gagnon\n\n1055 Rue Lucien-L'Allier\nMontreal, QC H3G 3C4\nCanada",
    },
}

@app.post("/generate")
def generate(data: dict):
    lead = data.get("lead", data)
    contact_name = lead.get("contactName", lead.get("companyName", ""))
    company_name = lead.get("companyName", "")
    language = lead.get("language", "English")
    website = lead.get("websiteUrl", "")
    generator = lead.get("generator", "Nathaniel Pouliot")

    is_french = any(x in language.lower() for x in ["fr", "french", "français", "francais", "fran"])
    lang_key = "french" if is_french else "english"
    write_in = "French" if is_french else "English"
    generator_key = generator if generator in SIGNATURES else "Nathaniel Pouliot"
    signature = SIGNATURES[generator_key][lang_key]

    body_prompt = f"""
You are an expert SEO strategist writing hyper-personalized cold emails for a high-end SEO agency.

Your goal is to generate a short cold email (max 120-160 words) that feels deeply personalized, specific, and based on real observations about their website.

CLIENT DATA:
- Contact name: {contact_name}
- Company: {company_name}
- Website: {website}
- Language to write in: {write_in}

CRITICAL LANGUAGE RULE:
- You MUST write the ENTIRE email in {write_in}
- Every single word must be in {write_in}
- If {write_in} is French, write 100% in French — not a single English word anywhere

INSTRUCTIONS:
- Choose ONE primary angle: visibility gap, authority gap, content gap, backlink gap, technical issue, competitor dominance, or paid ads dependency
- Write as if you have analyzed their website specifically
- Include 1-2 specific observations about their industry or business type
- Sound natural, direct, and human — no hype, no buzzwords, no generic lines
- Never say "I noticed your website" or "I came across your business"
- Never mention SEO in the first sentence

STRUCTURE AND FORMATTING:
1. Start with: "Hi {contact_name}," on its own line
2. Blank line
3. Personalized observation about their business/industry (1-2 sentences)
4. Blank line
5. Insight about what is likely missing or the opportunity (1-2 sentences)
6. Blank line
7. Soft positioning and soft CTA — end with a question, not a pitch (1-2 sentences)
8. Blank line
9. Signature exactly as provided below

SIGNATURE (use exactly as written):
{signature}

Generate ONLY the email body. No subject line. No explanations.
"""

    subject_prompt = f"""
Write a cold email subject line for an SEO outreach email to {company_name}.

CRITICAL: Write the subject line in {write_in} only.

Rules:
- Max 8 words
- Must spark curiosity and make them want to open it
- Sound like a human wrote it, not a marketer
- Reference their business, industry, or a specific pain point
- No emojis
- No exclamation marks
- No buzzwords
- Create a subtle information gap — hint at something they do not know

Return ONLY the subject line, nothing else. No quotes around it.
"""

    body_response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": body_prompt}],
        temperature=0.75,
        max_tokens=400
    )

    subject_response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": subject_prompt}],
        temperature=0.9,
        max_tokens=40
    )

    body = body_response.choices[0].message.content.strip()
    subject = subject_response.choices[0].message.content.strip().strip('"').strip("'")

    return {"subject": subject, "body": body}
