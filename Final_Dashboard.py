

import streamlit as st
import pandas as pd
import os
from openai import OpenAI
from supabase import create_client
import mock_pms

# --- Supabase Setup ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Streamlit Page Settings ---
st.set_page_config(page_title="All-in-One Assist | Claim Assistant", page_icon="🦷", layout="wide")

# --- Load Data ---
cdt_df = pd.read_csv("CDT_AI_Training_100_New_Rows.csv")
claim_df = pd.read_csv("cdt_claim_fields.csv")
patients = mock_pms.get_mock_patients()

# --- OpenAI Setup ---
api_key = st.secrets.get("OPENROUTER_API_KEY")
if not api_key:
    st.error("❌ OpenRouter API key not found.")
    st.stop()
client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
MODEL = "mistralai/mistral-7b-instruct"

# --- Session State Initialization ---
for key in ["selected_cdt_code", "suggestion_confirmed", "last_suggestion", "selected_patient"]:
    if key not in st.session_state:
        st.session_state[key] = None if "code" in key or "patient" in key else False

# --- Sidebar: Patient Selection ---
with st.sidebar:
    st.image("All in one assist.png", use_container_width=True)
    st.markdown("### 🦷 Select Patient")
    selected_name = st.selectbox("Patient", patients["Name"].tolist())
    st.markdown("---")
    st.markdown("📥 [Visit our Website](https://www.allinoneassist.com/)")

# Store selected patient
patient = patients[patients["Name"] == selected_name].iloc[0]
st.session_state.selected_patient = patient

# --- Tabs ---
tab1, tab2 = st.tabs(["CDT + ADA Claim Assistant", "Claims Dashboard"])

# ----------------------------
# Tab 1: CDT Claim Assistant
# ----------------------------
with tab1:
    st.markdown("## CDT Code Suggestion")

    st.info("Use AI to suggest the most accurate CDT code based on the patient’s clinical notes.")
    st.dataframe(pd.DataFrame({
        "Field": ["Name", "DOB", "Gender", "Tooth #", "Surface", "Note", "Treatment"],
        "Value": [
            str(patient["Name"]), str(patient["DOB"]), str(patient["Gender"]),
            str(patient["Tooth Number"]), str(patient["Surface"]),
            str(patient["Clinical Notes"]), str(patient["Procedure"])]
    }), use_container_width=True, hide_index=True)

    if not st.session_state.suggestion_confirmed:
        if st.button("Suggest CDT Code"):
            prompt = f"""You are a CDT coding assistant. Given the clinical note, suggest the most accurate CDT code.

Clinical Note: {patient['Clinical Notes']}
Tooth Number: {patient['Tooth Number']}
Surface: {patient['Surface']}

Return format:
CDT Code: <code>
Reason: <why this fits>
"""
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "You are a helpful CDT coding assistant."},
                        {"role": "user", "content": prompt}
                    ]
                )
                suggestion = response.choices[0].message.content.strip()
                st.session_state.last_suggestion = suggestion
                if "CDT Code:" in suggestion:
                    code = suggestion.split("CDT Code:")[1].strip().split()[0]
                    st.session_state.selected_cdt_code = code

                st.success("✅ CDT Code Suggested:")
                st.markdown(f"```\n{suggestion}\n```")
            except Exception as e:
                st.error(f"❌ Error generating suggestion:\n\n{e}")

        if st.session_state.last_suggestion:
            st.info("Do you want to continue with the suggested CDT Code?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Yes, proceed"):
                    st.session_state.suggestion_confirmed = True
            with col2:
                if st.button("🔄 Start Over"):
                    for key in ["selected_cdt_code", "last_suggestion"]:
                        st.session_state[key] = None
                    st.session_state.suggestion_confirmed = False

    # Step 2: ADA Form
    if st.session_state.suggestion_confirmed:
        st.markdown("---")
        st.markdown("## Auto-Filled ADA Claim Form")

        field_data = {}
        for _, row in claim_df.iterrows():
            field = row["Field Name"]
            field_lower = field.lower()

            if "cdt code" in field_lower or "procedure code" in field_lower:
                value = st.session_state.selected_cdt_code
            elif "patient name" in field_lower:
                value = patient["Name"]
            elif "relationship" in field_lower:
                value = patient["Relationship"]
            elif "date of birth" in field_lower:
                value = patient["DOB"]
            elif "gender" in field_lower:
                value = patient["Gender"]
            elif "subscriber name" in field_lower:
                value = patient["Subscriber Name"]
            elif "subscriber id" in field_lower:
                value = patient["Subscriber ID"]
            elif "tooth number" in field_lower:
                value = patient["Tooth Number"]
            elif "surface" in field_lower:
                value = patient["Surface"]
            elif "fee" in field_lower:
                value = patient["Fee"]
            elif "address" in field_lower:
                value = patient["Address"]
            elif "treating dentist" in field_lower:
                value = patient["Subscriber Name"]
            elif "phone number" in field_lower:
                value = "555-123-4567"
            else:
                value = ""

            field_data[field] = value

        edited_fields = {field: st.text_input(field, value=val) for field, val in field_data.items()}

        from datetime import datetime


        def clean_dates(claim_data):
            for key, value in claim_data.items():
                if "date" in key or "dob" in key:
                    try:
                        # Handle DD-MM-YYYY and similar formats
                        parsed = datetime.strptime(value, "%d-%m-%Y")
                        claim_data[key] = parsed.strftime("%Y-%m-%d")
                    except:
                        try:
                            parsed = datetime.strptime(value, "%d/%m/%Y")
                            claim_data[key] = parsed.strftime("%Y-%m-%d")
                        except:
                            pass  # skip conversion if already ISO or invalid
            return claim_data


        if st.button("📤 Submit to Supabase"):
            raw_claim_data = {k.lower().replace(" ", "_"): v for k, v in edited_fields.items()}
            cleaned = {k: v for k, v in raw_claim_data.items() if str(v).strip() != ""}
            cleaned = clean_dates(cleaned)  # 👈 convert dates to YYYY-MM-DD

            try:
                supabase.table("claims").insert(cleaned).execute()
                st.success("✅ Claim submitted and stored in Supabase.")
            except Exception as e:
                st.error(f"❌ Failed to save to Supabase: {e}")

# ----------------------------
# Tab 2: Claims Dashboard
# ----------------------------
with tab2:
    st.markdown("## Claims Submission Dashboard")

    if os.path.exists(CLAIM_LOG_PATH):
        df = pd.read_csv(CLAIM_LOG_PATH)
        if not df.empty:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Claims", len(df))
            col2.metric("Avg Fee", f"${df['Fee'].astype(float).mean():.2f}" if 'Fee' in df.columns else "-")
            col3.metric("CDT Codes Used", df['Procedure Code'].nunique() if 'Procedure Code' in df.columns else "-")
            st.divider()
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No claims submitted yet.")
    else:
        st.info("No claims submitted yet.")




