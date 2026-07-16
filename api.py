import openai
import random
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


def build_greeting(contact_name: str, company_name: str, is_french: bool) -> str:
    """
    Builds the opening greeting line deterministically instead of letting the
    AI generate it — this guarantees the company/contact name is always used
    exactly as it appears in the lead data (no paraphrasing, no capitalization
    drift), while still varying naturally by language and by whether we have
    a real person's name to address.
    """
    contact_name = (contact_name or "").strip()
    company_name = (company_name or "").strip()

    # A "real" contact name is one that's actually different from the company
    # name — the frontend already falls back to company name when no personal
    # contact exists, so contact_name == company_name means "no real person".
    has_real_contact = bool(contact_name) and contact_name != company_name

    if has_real_contact:
        return f"Bonjour {contact_name}," if is_french else f"Hi {contact_name},"

    # No real contact — greet the company/team instead.
    company = company_name or contact_name or ("l'équipe" if is_french else "there")

    if is_french:
        options = [
            f"Bonjour l'équipe de {company},",
            f"Bonjour à l'équipe de {company},",
            f"Bonjour {company},",
        ]
    else:
        options = [
            f"Hi {company},",
            f"Hello {company},",
            f"Hello the {company} team,",
        ]
    return random.choice(options)


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

    greeting = build_greeting(contact_name, company_name, is_french)

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

DO NOT include a greeting line — one has already been added separately. Start directly with the personalized observation.

STRUCTURE AND FORMATTING:
1. Personalized observation about their business/industry (1-2 sentences)
2. Blank line
3. Insight about what is likely missing or the opportunity (1-2 sentences)
4. Blank line
5. Soft positioning and soft CTA — end with a question, not a pitch (1-2 sentences)
6. Blank line
7. Signature exactly as provided below

SIGNATURE (use exactly as written):
{signature}

Generate ONLY the email body, starting from the personalized observation (no greeting, no subject line, no explanations).
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

    ai_body = body_response.choices[0].message.content.strip()
    body = f"{greeting}\n\n{ai_body}"
    subject = subject_response.choices[0].message.content.strip().strip('"').strip("'")

    return {"subject": subject, "body": body}