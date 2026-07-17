import openai
import random
import json
import os
import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

openai.api_key = os.environ.get("OPENAI_API_KEY", "")

# ─── Microsoft OAuth (confidential client — backend holds the secret) ─────────
#
# The frontend used to talk to Microsoft's token endpoint directly, which only
# works for apps registered as "Single-page application" in Azure — and SPA
# registrations get refresh tokens capped at 24 hours, by Microsoft design.
# Moving the token exchange here, behind a "Web" platform registration with a
# client secret, gets the normal ~90-day sliding-window refresh tokens instead.
# The secret never reaches the browser — only this server ever sees it.

MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "ffcaea26-e142-4daf-aeb7-e6751f5937dd")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_SCOPES = "Mail.ReadWrite Mail.Send User.Read offline_access"


def _redirect_uri_for(request: Request) -> str:
    # Derives the redirect URI from whatever host actually received the
    # request, so the same code works unmodified on localhost and on Render.
    return f"{request.url.scheme}://{request.url.netloc}/auth/callback"


def _popup_close_html(payload: dict) -> str:
    """Tiny page that hands the result back to the window that opened the
    popup (via postMessage) and closes itself — mirrors the message-based
    handshake the frontend was already using."""
    return f"""<!DOCTYPE html>
<html><body style="font-family: sans-serif; padding: 2rem; color: #333;">
<script>
  if (window.opener) {{
    window.opener.postMessage({json.dumps(payload)}, "*");
  }}
  window.close();
</script>
<p>{"Connected — you can close this window." if payload.get("type") == "ms_auth_success" else "Authentication failed — you can close this window."}</p>
</body></html>"""


@app.get("/auth/callback")
def auth_callback(request: Request, code: str = None, error: str = None, error_description: str = None):
    if error:
        return HTMLResponse(_popup_close_html({
            "type": "ms_auth_error",
            "error": error_description or error,
        }))

    if not MS_CLIENT_SECRET:
        return HTMLResponse(_popup_close_html({
            "type": "ms_auth_error",
            "error": "Server is missing MS_CLIENT_SECRET — set it as an environment variable.",
        }))

    redirect_uri = _redirect_uri_for(request)
    token_res = requests.post(MS_TOKEN_URL, data={
        "client_id": MS_CLIENT_ID,
        "client_secret": MS_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": MS_SCOPES,
    })
    token_data = token_res.json()

    if not token_res.ok:
        return HTMLResponse(_popup_close_html({
            "type": "ms_auth_error",
            "error": token_data.get("error_description", "Token exchange failed"),
        }))

    return HTMLResponse(_popup_close_html({
        "type": "ms_auth_success",
        "accessToken": token_data["access_token"],
        "refreshToken": token_data.get("refresh_token", ""),
        "expiresIn": token_data.get("expires_in", 3600),
    }))


@app.post("/auth/refresh")
def auth_refresh(data: dict):
    refresh_token = data.get("refreshToken", "")
    if not refresh_token:
        return {"error": "Missing refreshToken"}
    if not MS_CLIENT_SECRET:
        return {"error": "Server is missing MS_CLIENT_SECRET — set it as an environment variable."}

    token_res = requests.post(MS_TOKEN_URL, data={
        "client_id": MS_CLIENT_ID,
        "client_secret": MS_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": MS_SCOPES,
    })
    token_data = token_res.json()

    if not token_res.ok:
        return {"error": token_data.get("error_description", "Token refresh failed")}

    return {
        "accessToken": token_data["access_token"],
        "refreshToken": token_data.get("refresh_token", refresh_token),
        "expiresIn": token_data.get("expires_in", 3600),
    }


# ─── Existing email generation endpoint (unchanged) ────────────────────────────

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

    has_real_contact = bool(contact_name) and contact_name != company_name

    if has_real_contact:
        return f"Bonjour {contact_name}," if is_french else f"Hi {contact_name},"

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