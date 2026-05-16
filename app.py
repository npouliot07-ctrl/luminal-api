import streamlit as st
import json
import openai
import time
import pandas as pd
import os
from google.oauth2.service_account import Credentials
import gspread
from main import read_sheet, write_emails_to_sheet, update_courriel_column_only, generate_email_openai


# Helper function to convert column number to letter
def col_num_to_letter(n):
   
   
   
   
   result = ""
   while n > 0:
       n, remainder = divmod(n - 1, 26)
       result = chr(65 + remainder) + result
   return result


# Load OpenAI key from secrets
openai.api_key = st.secrets["OPENAI_API_KEY"]


# Debug: safe preview of key
st.write("OpenAI key preview:", openai.api_key[:4] + "..." + openai.api_key[-4:])


# Quick test using new API
try:
   client = openai.OpenAI(api_key=openai.api_key)
   models = client.models.list()
   st.success(f"✅ OpenAI key is valid! {len(models.data)} models accessible.")
except Exception as e:
   st.error(f"❌ OpenAI error: {e}")


SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]




def get_sheet(spreadsheet_id, sheet_name="RawData"):
   # Absolute path to JSON
   creds_path = os.path.join(os.getcwd(), "service_account.json")
   creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
   print("JSON loaded from:", creds_path)
   client = gspread.authorize(creds)


   sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
   return sheet


# Open spreadsheet
spreadsheet_id = "1u3ZnH8p6udu2IZuFXdq9P8RxyOpTMG6ZRT7_LITGux4"
sheet = get_sheet(spreadsheet_id, sheet_name="RawData")
print(sheet.title)


df = read_sheet(sheet)


st.set_page_config(page_title="SEO Email Generator - Row Selector", layout="wide")


st.title("SEO Email Generator - Row Selector")


if df.empty:
   st.warning("No data loaded yet. Enter a valid Google Sheet tab name and credentials path.")
else:
   st.title("Email Generator")


   # Ask the user which rows to process
   start_row = st.number_input("Start row", min_value=2, max_value=10000, value=2, step=1)
   end_row = st.number_input("End row", min_value=start_row, max_value=10000, value=100, step=1)


   st.write(f"Generating emails for rows {start_row} to {end_row}")


   # Read sheet into df
   df = read_sheet(sheet)


   # Only take the selected range
   df = df.iloc[start_row - 2 : end_row]  # subtract 2 because iloc is 0-indexed, first row is header


   # Slice the DataFrame for the selected range
   selected_rows = df
   st.dataframe(selected_rows[["Company", "Name", "Language"]])


   selected_index = start_row
   selected_row = df.loc[selected_index]


   if st.button("Generate Single Email"):
       name = selected_row["Name"]
       company = selected_row["Company"]
       language = selected_row.get("Language", "English")
       relevant_info = selected_row.get("Website Text", "")


       email_content = generate_email_openai(name, company, language, relevant_info)
      
       # Show the generated email
       st.subheader("Generated Email")
       st.text_area("Email Preview", email_content, height=300)
      
       # Save to DataFrame
       df.at[selected_index, "courriel"] = email_content


       if st.button("Save Emails"):
           write_emails_to_sheet(df, sheet, email_column="courriel")
           st.success("Email saved successfully!")


   if st.button("Generate Range Emails"):
       # Suppose start_row and end_row come from Streamlit input
       sheet_start = start_row  # first row in Google Sheet to update


       # Slice df
       df_slice = df.iloc[start_row - 2 : end_row]  # DataFrame slice


       # Get column index for 'courriel'
       headers = sheet.row_values(1)
       col_index = headers.index("courriel") + 1
       col_letter = col_num_to_letter(col_index)


       # Loop with correct sheet row
       for offset, (i, row) in enumerate(df_slice.iterrows()):
           sheet_row = sheet_start + offset  # actual Google Sheet row
           email_content = generate_email_openai(
               row["Name"], row["Company"], row.get("Language", "English"), row.get("Website Text", "")
           )
           # Update DataFrame
           df.at[i, "courriel"] = email_content


       # Batch update the sheet
       emails = df_slice["courriel"].tolist()  # list of generated emails
       sheet.update(f"{col_letter}{start_row}:{col_letter}{end_row}", [[e] for e in emails])
      
       st.success(f"Emails generated for rows {start_row} to {end_row}")


   if st.button("Save Generated Emails"):
       write_emails_to_sheet(df, sheet, email_column="courriel")
       st.success("All emails saved to Google Sheet!")


   st.write("### Client Data")
   st.dataframe(df)


   row_indices = st.multiselect(
       "Select rows to generate emails (row numbers shown above)",
       options=list(df.index)
   )


   if st.button("Generate Emails"):
       if not row_indices:
           st.warning("Please select at least one row.")
       else:
           if "courriel" not in df.columns:
               df["courriel"] = ""


           for i in row_indices:
               row = df.loc[i]
               email_content = generate_email_openai(
                   row["Name"],
                   row["Company"],
                   row.get("Language", "English"),
                   row.get("Website Text", "")
               )
               df.at[i, "courriel"] = email_content
               st.success(f"Email generated for {row['Name']}")
               time.sleep(1)


           if sheet is not None:
               write_emails_to_sheet(df, sheet, email_column="courriel")
               st.success("Selected emails saved to Google Sheet!")
           else:
               st.warning("No sheet available to write back.")


   st.write("### Preview Generated Emails")
   if "courriel" not in df.columns:
       df["courriel"] = ""
   st.dataframe(df[[col for col in df.columns if col != "courriel"] + ["courriel"]])
