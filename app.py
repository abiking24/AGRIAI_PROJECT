import sqlite3
import time
from datetime import datetime
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# --------------------------------------------------
# 1. PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="AgriAI V2 - የሰብል በሽታ መለያ", page_icon="🌿", layout="wide"
)


# --------------------------------------------------
# 2. DATABASE SETUP (SQLite)
# --------------------------------------------------
def init_db():
  conn = sqlite3.connect("agriai_history.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            crop_name TEXT,
            result_text TEXT
        )
    """)
  conn.commit()
  conn.close()


init_db()


def save_to_db(crop_name, result_text):
  conn = sqlite3.connect("agriai_history.db")
  cursor = conn.cursor()
  timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  cursor.execute(
      "INSERT INTO analyses (timestamp, crop_name, result_text) VALUES (?, ?,"
      " ?)",
      (timestamp, crop_name, result_text),
  )
  conn.commit()
  conn.close()


# --------------------------------------------------
# 3. API CONFIGURATION
# --------------------------------------------------
try:
  api_key = st.secrets["GEMINI_API_KEY"]
  client = genai.Client(api_key=api_key)
  API_READY = True
except Exception as e:
  API_READY = False
  st.error("❌ Gemini API Key ማዋቀር አልተቻለም።")
  st.code(str(e))

# --------------------------------------------------
# 4. APP HEADER & SIDEBAR HISTORY
# --------------------------------------------------
st.title("🌿 AgriAI V2 - የሰብል በሽታ መለያ እና የባለሙያ ምክር ስርዓት")
st.write(
    "የሰብል ቅጠል ፎቶ በመጫን በሽታውን በፍጥነት ይለዩ እና የታሪክ ማህደርዎን ያስቀምጡ።"
)

# የጎን ማስታወሻ (Sidebar) ለቀድሞ ፍተሻዎች ታሪክ ማሳያ
st.sidebar.title("ራዕይ / የታሪክ ማህደር 📋")
if st.sidebar.button("🔄 ታሪኮችን አድስ (Refresh)"):
  pass

# ከዳታቤዝ የቀድሞ ታሪኮችን ማንበብ
conn = sqlite3.connect("agriai_history.db")
cursor = conn.cursor()
cursor.execute(
    "SELECT timestamp, crop_name, result_text FROM analyses ORDER BY id DESC"
    " LIMIT 5"
)
history_records = cursor.fetchall()
conn.close()

if history_records:
  st.sidebar.subheader("የቅርብ ጊዜ ፍተሻዎች:")
  for idx, (ts, crop, res) in enumerate(history_records):
    with st.sidebar.expander(f"{crop} ({ts})"):
      st.write(res[:200] + "...")
else:
  st.sidebar.write("እስካሁን የተመዘገበ ታሪክ የለም።")

# --------------------------------------------------
# 5. INPUT METHOD & ANALYSIS
# --------------------------------------------------
input_option = st.radio(
    "📷 የምስል ማስገቢያ ዘዴ ይምረጡ:",
    ("📁 ከፋይል መጫን (Upload)", "📸 በቀጥታ ካሜራ ማንሳት"),
    horizontal=True,
)

uploaded_file = None
if input_option == "📁 ከፋይል መጫን (Upload)":
  uploaded_file = st.file_uploader(
      "የሰብል ቅጠል ፎቶ ይጫኑ (JPG, PNG)", type=["jpg", "jpeg", "png"]
  )
else:
  uploaded_file = st.camera_input("ካሜራውን በመጠቀም የቅጠል ፎቶ ያንሱ")

detailed_explanation = st.checkbox(
    "📖 ተጨማሪ ጥልቅ እና ዝርዝር ማብራሪያ አሳይ (Detailed Analysis)"
)

if uploaded_file is not None:
  image = Image.open(uploaded_file)
  image.thumbnail((1024, 1024))

  st.image(image, caption="የተመረጠው የሰብል ፎቶ", use_container_width=True)

  if st.button("🔍 በሽታውን በብልህነት መርምር", type="primary"):
    if not API_READY:
      st.error("❌ Gemini API ዝግጁ አይደለም።")
    else:
      with st.spinner(
          "⏳ AI ፎቶውን በመመርመር እና መፍትሄዎችን በማዘጋጀት ላይ ይገኛል..."
      ):

        if detailed_explanation:
          prompt = """
You are an expert agricultural plant pathologist.
Analyze the uploaded crop leaf image carefully and provide a very detailed, in-depth response in Amharic (keep official crop and disease names in English too).
Provide a structured response covering Crop, Disease, Overview, Treatment, Prevention, Warning, and Action Plan.
"""
        else:
          prompt = """
You are an expert agricultural plant pathologist.
Analyze the uploaded crop leaf image carefully and respond in Amharic (keep official crop and disease names in English too).
Provide a structured response covering: 1. Crop, 2. Disease, 3. Overview, 4. Treatment, 5. Prevention, 6. Warning, 7. Action Plan.
"""

        response_text = None
        models_to_try = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]

        success = False
        for model_name in models_to_try:
          try:
            response = client.models.generate_content(
                model=model_name,
                contents=[image, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2, max_output_tokens=1600
                ),
            )
            response_text = response.text
            success = True
            break
          except Exception as e:
            continue

        if success and response_text:
          st.success("✅ ትንተናው በተሳካ ሁኔታ ተጠናቋል!")
          st.markdown("---")
          st.markdown(response_text)

          # የተገኘውን ውጤት በዳታቤዝ ውስጥ ማስቀመጥ (ማህደር)
          save_to_db("የተመረመረ ሰብል/ቅጠል", response_text)
        else:
          st.error(
              "❌ የነጻው መለያ የጥያቄ ገደብ (Quota) ሙሉ በሙሉ አልቋል። እባክዎ ከጥቂት ሰዓታት"
              " በኋላ እንደገና ይሞክሩ።"
          )