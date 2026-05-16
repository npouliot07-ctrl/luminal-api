import argparse
import json
import logging
import os
import time
import pandas as pd
import streamlit as st
from pathlib import Path
import requests
import openai
from google.oauth2.service_account import Credentials
import gspread

# Helper function to convert column number to letter
def col_num_to_letter(n):
    
    
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result

openai.api_key = st.secrets["OPENAI_API_KEY"]

# Optional debug
st.write("OpenAI key loaded:", openai.api_key[:8] + "...")  # prints first 8 chars

# Load Google credentials from service_account.json
with open("service_account.json") as f:
    google_creds = json.load(f)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# Get the absolute path to service_account.json in the same folder as app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
creds_path = os.path.join(BASE_DIR, "service_account.json")

creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
client = gspread.authorize(creds)

spreadsheet_id = "1u3ZnH8p6udu2IZuFXdq9P8RxyOpTMG6ZRT7_LITGux4"
sheet = client.open_by_key(spreadsheet_id).worksheet("RawData")
HF_API_TOKEN = "YOUR_HUGGINGFACE_TOKEN"  # get from https://huggingface.co/settings/tokens
HF_MODEL = "EleutherAI/gpt-j-6B"
HEADERS = {"Authorization": f"Bearer {HF_API_TOKEN}"}

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

# ==========================
# SETTINGS
# ==========================
INPUT_FILE = "clients.csv"
CACHE_FILE = "emails_cache.csv"
MAX_TOKENS = 250
TEMPERATURE = 0.7
TOP_P = 0.9
BATCH_DELAY = 2  # seconds between emails

COLUMN_ALIASES = {
    "nom/contact": "Name",
    "email": "Email",
    "compagnie": "Company",
    "industrie": "Industry",
    "langue": "Language",
    "site internet": "URL",
}

# ==========================
# HELPER FUNCTIONS
# ==========================
def load_cache():
    if Path(CACHE_FILE).exists():
        return pd.read_csv(CACHE_FILE)
    return pd.DataFrame(columns=["client_name", "email"])


def save_cache(df):
    df.to_csv(CACHE_FILE, index=False)


def get_sheet(sheet_name="RawData", creds_path="service_account.json"):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    
    # Replace with your spreadsheet ID
    spreadsheet_id = "1u3ZnH8p6udu2IZuFXdq9P8RxyOpTMG6ZRT7_LITGux4"
    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
    return sheet


def read_sheet(sheet):
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    
    # Normalize columns to match your code
    COLUMN_ALIASES = {
        "nom/contact": "Name",
        "email": "Email",
        "compagnie": "Company",
        "industrie": "Industry",
        "langue": "Language",
        "site internet": "URL"
       
    }
    df.columns = [COLUMN_ALIASES.get(c.lower(), c) for c in df.columns]
    return df


def write_emails_to_sheet(df, sheet, email_column="courriel"):
    # Keep all original data, only update email column
    if email_column not in df.columns:
        df[email_column] = ""
    
    # Convert DataFrame back to list of lists
    header = df.columns.tolist()
    values = df[header].values.tolist()
    sheet.update([header] + values)


def update_sheet_with_emails(sheet, df):
    """
    Updates only the 'courriel' column in the Google Sheet,
    without touching the 'client?' column or other data.
    """
    # Get all existing values from the sheet
    all_values = sheet.get_all_values()
    header = all_values[0]

    if "courriel" not in header:
        # Add the 'courriel' column if it doesn't exist
        header.append("courriel")
        all_values[0] = header
        for row in all_values[1:]:
            row.append("")  # empty email cell for each row

    email_col_index = header.index("courriel")

    # Update only the 'courriel' column with generated emails
    for i, email in enumerate(df["courriel"], start=1):  # skip header row
        all_values[i][email_col_index] = email

    # Push back to the sheet
    sheet.update(all_values)


def update_courriel_column_only(sheet, df, col_name="courriel"):
    """
    Update only the 'courriel' column in Google Sheet without touching checkboxes or other columns.
    """
    # Get headers from the first row
    headers = sheet.row_values(1)
    if col_name not in headers:
        # Add the column at the end if missing
        sheet.update_cell(1, len(headers) + 1, col_name)
        headers.append(col_name)

    col_index = headers.index(col_name) + 1  # gspread is 1-indexed
    col_letter = col_num_to_letter(col_index)

    # Prepare 2D list of emails
    email_values = [[email] for email in df[col_name]]

    # Update entire column at once
    sheet.update(f"{col_letter}2:{col_letter}{len(email_values)+1}", email_values)


def write_emails_to_sheet(df, sheet, email_column="courriel"):
    """
    Updates only the email_column in the Google Sheet without touching checkboxes or other columns.
    """
    # Get headers from the sheet
    headers = sheet.row_values(1)
    if email_column not in headers:
        # Add the column at the end if missing
        sheet.update_cell(1, len(headers) + 1, email_column)
        headers.append(email_column)

    col_index = headers.index(email_column) + 1  # gspread is 1-indexed

    # Update only the email column for each row
    for i, email in enumerate(df[email_column], start=2):  # skip header
        sheet.update_cell(i, col_index, email)


# Extract relevant info specifically for SEO outreach
def extract_relevant_info_for_seo(text: str) -> str:
    """
    Extracts key points for SEO agency outreach:
    - Products/services
    - Team or people
    - Other marketing-relevant info (e.g., unique services, programs)
    """
    if not text:
        return ""
    sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 20]
    keywords = ["product", "service", "offer", "team", "staff", "program", "company", "clients", "solutions"]
    relevant_sentences = [s for s in sentences if any(kw.lower() in s.lower() for kw in keywords)]
    return " ".join(relevant_sentences[:5])  # pick top 5 relevant sentences


def generate_email_gptj(name, company, language, relevant_info):
    prompt = f"""
You are an expert SEO consultant writing personalized outreach emails.

Write a concise, professional, friendly email in {language} to {name} at {company}.
The email should:
- Mention the company naturally, without sounding like a data dump.
- Include insights about their products, services, or team (use this info: {relevant_info}).
- Show how our SEO agency can help improve their online presence.
- Offer a free consultation or audit.
- End politely, encouraging a response.

Keep it clear, human, and engaging. Maximum 250 words.
"""

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 250,
            "temperature": 0.6,
            "top_p": 0.9,
            "repetition_penalty": 1.2  # helps reduce repeating phrases
        }
    }

    payload["parameters"]["stop_sequences"] = ["\n\n", "Best regards", "Sincerely"]

    response = requests.post(
        f"https://<your-endpoint>.hf.space",
        headers=HEADERS,
        json=payload,
        timeout=60
    )

    if response.status_code != 200:
        print(f"Error generating email for {name}: {response.text}")
        return ""

    data = response.json()
    # The generated text
    return data[0]["generated_text"] if "generated_text" in data[0] else ""

def generate_email_openai(name, company, language, relevant_info):
    import openai

    prompt = f"""
    Write a professional, friendly, and personalized email to {name} at {company} in {language}.
    Include the following information naturally about their company (products, team, services):
    {relevant_info}
    Encourage them to connect about SEO services.
    End politely.
    """

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.7
    )

    # Access the generated text with .content
    return response.choices[0].message.content

def write_generated_emails_to_sheet(df, sheet, column_name="Mail Generated"):
    """
    Writes generated emails back to Google Sheet in a new column.
    It preserves all existing columns, including 'Client?'.
    """
    # Ensure the column exists in the DataFrame
    if column_name not in df.columns:
        df[column_name] = ""

    # Update the DataFrame with generated emails
    # Convert DataFrame to list of lists for gspread
    header = sheet.row_values(1)
    
    # Add new column to header if not present
    if column_name not in header:
        header.append(column_name)
    
    # Prepare data for gspread update
    data = [header]
    for i, row in df.iterrows():
        row_values = [row.get(col, "") for col in header]
        data.append(row_values)
    
    sheet.update(data)

# ==========================
# MAIN EMAIL GENERATION
# ==========================
def main():
    parser = argparse.ArgumentParser(description="Generate personalised emails from CSV or Google Sheets.")
    parser.add_argument("--sheet", action="store_true", help="Use Google Sheets instead of local CSV")
    parser.add_argument("--sheet-name", default="RawData", help="Google Sheet tab name")
    parser.add_argument("--sheet-creds", default="service_account.json", help="Path to Google Sheets service account JSON")
    args = parser.parse_args()

    if args.sheet:
        sheet = get_sheet(sheet_name=args.sheet_name, creds_path=args.sheet_creds)
        df = read_sheet(sheet)

    # After loading the DataFrame (from sheet or CSV)
    if args.sheet:
        sheet = get_sheet(sheet_name=args.sheet_name, creds_path=args.sheet_creds)
        df = read_sheet(sheet)
    else:
        df = pd.read_csv(INPUT_FILE)

    if args.sheet:
        sheet = get_sheet(sheet_name=args.sheet_name, creds_path=args.sheet_creds)
        df = read_sheet(sheet)

    # Only take the first 5 rows
    df = df.head(5)
    df["courriel"] = ""  # Create the column if it doesn't exist

    # Then continue with your email generation loop
    for i, row in df.iterrows():
        name = row["Name"]
        company = row["Company"]
        language = row.get("Language", "English")
        relevant_info = row.get("Website Text", "")  # Or whatever column you use

        email_content = generate_email_openai(name, company, language, relevant_info)
        print(f"\n--- Email for {name} ---\n{email_content}\n")

        # Save generated email in 'courriel' column
        df.at[i, "courriel"] = email_content

    # Push back to Google Sheet when using sheet mode
    if args.sheet:
        write_emails_to_sheet(df, sheet, email_column="courriel")


if __name__ == "__main__":

    main()
