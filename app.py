import os
import sqlite3
from datetime import datetime

import requests
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# --------------------------------------------------
# 1. PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="Agre AI Project - Smart Crop Disease & Weather Diagnosis",
    page_icon="🌿",
    layout="wide",
)

# --------------------------------------------------
# 2. SECURE BACKEND API CONFIGURATION (NO UI EXPOSURE)
# --------------------------------------------------
def get_api_key() -> str:
  # 1. Check Streamlit secrets
  try:
    sec_key = st.secrets.get("GEMINI_API_KEY", "")
    if (
        isinstance(sec_key, str)
        and sec_key.strip()
        and sec_key.strip() != "YOUR_GEMINI_API_KEY"
    ):
      return sec_key.strip()
  except Exception:
    pass

  # 2. Check environment variables
  env_key = os.environ.get("GEMINI_API_KEY", "")
  if (
      isinstance(env_key, str)
      and env_key.strip()
      and env_key.strip() != "YOUR_GEMINI_API_KEY"
  ):
    return env_key.strip()

  return ""


API_KEY = get_api_key()
if API_KEY:
  os.environ["GEMINI_API_KEY"] = API_KEY

# Optional legacy configure hook
try:
  import google.generativeai as gai

  if API_KEY:
    gai.configure(api_key=API_KEY)
except Exception:
  pass

client = None
API_READY = False
if API_KEY:
  try:
    client = genai.Client(api_key=API_KEY)
    API_READY = True
  except Exception:
    client = None
    API_READY = False

# --------------------------------------------------
# 3. AUTOMATED MODEL FALLBACK LOGIC
# --------------------------------------------------
FLASH_MODELS_ORDER = [
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]


def generate_content_automatically(contents, model_names=None):
  """Cycles through available flash models automatically without requiring UI intervention."""
  if not client:
    raise RuntimeError("Gemini Client is not initialized.")

  models_to_try = model_names or FLASH_MODELS_ORDER
  last_exception = None

  for model_name in models_to_try:
    try:
      response = client.models.generate_content(
          model=model_name,
          contents=contents,
      )
      if response and response.text:
        return response
    except Exception as exc:
      last_exception = exc
      continue

  if last_exception is not None:
    raise last_exception
  raise RuntimeError("All candidate Gemini models failed to generate content.")


def gemini_error_message(error):
  error_text = str(error).lower()
  error_code = getattr(error, "code", None)
  if (
      error_code == 429
      or "quota" in error_text
      or "resource_exhausted" in error_text
  ):
    return "የGemini ጥቅም ገደብ (quota) ተደርሷል። እባክዎ ጥቂት ቆይተው እንደገና ይሞክሩ።"
  if error_code == 401 or "api_key_invalid" in error_text:
    return "የGemini API ቁልፉ ትክክል አይደለም ወይም ተቀባይነት አላገኘም።"
  if error_code == 403:
    return "የGemini API መዳረሻ ተከልክሏል።"
  if isinstance(error_code, int) and error_code >= 500:
    return "የGemini አገልግሎት ጊዜያዊ ችግር አጋጥሞታል። እባክዎ ቆይተው እንደገና ይሞክሩ።"
  return f"የምርመራ ሂደቱ አልተሳካም: {str(error)}"


# --------------------------------------------------
# 4. DATABASE & HISTORY PERSISTENCE (SQLite)
# --------------------------------------------------
DB_PATH = "agriai_history.db"


def init_db():
  try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                crop_name TEXT,
                result_text TEXT
            )
        """)
    conn.commit()
    conn.close()
  except Exception as e:
    print(f"Database init error: {e}")


def save_diagnosis_to_db(timestamp, location_name, result_text):
  try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO analyses (timestamp, crop_name, result_text) VALUES (?, ?,"
        " ?)",
        (timestamp, location_name, result_text),
    )
    conn.commit()
    conn.close()
  except Exception as e:
    print(f"Database save error: {e}")


def load_diagnoses_from_db():
  try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, crop_name, result_text FROM analyses ORDER BY id ASC"
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"time": r[0], "city": r[1], "image": None, "summary": r[2]}
        for r in rows
    ]
  except Exception as e:
    print(f"Database load error: {e}")
    return []


def clear_db_history():
  try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM analyses")
    conn.commit()
    conn.close()
  except Exception as e:
    print(f"Database clear error: {e}")


init_db()

if "diagnosis_history" not in st.session_state:
  st.session_state["diagnosis_history"] = load_diagnoses_from_db()

# --------------------------------------------------
# 5. SIDEBAR: ONLY HISTORY PERSISTENCE (ZERO SETTINGS)
# --------------------------------------------------
st.sidebar.title("📜 የቅድመ ምርመራ ታሪክ (History)")

if st.sidebar.button("🗑️ ታሪኮችን ባዶ አድርግ"):
  st.session_state["diagnosis_history"] = []
  clear_db_history()
  st.rerun()

if len(st.session_state["diagnosis_history"]) == 0:
  st.sidebar.info("እስካሁን የተከናወነ ምርመራ የለም።")
else:
  for idx, item in enumerate(reversed(st.session_state["diagnosis_history"])):
    with st.sidebar.expander(f"📌 {item['time']} - {item['city']}"):
      if item.get("image") is not None:
        st.image(item["image"], width=150)
      st.write(f"**አካባቢ:** {item['city']}")
      st.markdown(item["summary"][:150] + "...")

# --------------------------------------------------
# 6. APP HEADER & SEARCH
# --------------------------------------------------
st.title("🌿 Agre AI Project - የሰብል በሽታ መለያ እና የአየር ንብረት ትንተና ስርአት")
st.write(
    "የማንኛውንም አካባቢ አየር ንብረትና ዝናብ ሁኔታ በመመርኮዝ፣ ለገበሬዎች የሚሆን"
    " ትክክለኛ የመስኖ ጊዜ እና የባለሙያ ትንተና ያግኙ።"
)

# --------------------------------------------------
# 7. GLOBAL LOCATION & WEATHER (Open-Meteo)
# --------------------------------------------------
st.subheader("📍 የአካባቢዎ እና የአየር ንብረት ሁኔታ (ማንኛውንም ከተማ ይፈልጉ)")

user_city_input = st.text_input(
    "የከተማውን ስም በእንግሊዝኛ ይጻፉ (ለምሳሌ፦ Dilla, Addis Ababa, Nairobi, London):",
    value="Dilla",
)

weather = {}
selected_city_name = user_city_input.strip()

if selected_city_name:
  try:
    geo_url = (
        "https://geocoding-api.open-meteo.com/v1/search?name="
        f"{selected_city_name}&count=1&language=en&format=json"
    )
    geo_res = requests.get(geo_url, timeout=3)
    if geo_res.status_code == 200:
      geo_data = geo_res.json()
      if "results" in geo_data and len(geo_data["results"]) > 0:
        location = geo_data["results"][0]
        lat = location["latitude"]
        lon = location["longitude"]
        country = location.get("country", "")
        city_display_name = f"{location['name']}, {country}"

        weather_url = (
            "https://api.open-meteo.com/v1/forecast?latitude="
            f"{lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,precipitation"
        )
        w_res = requests.get(weather_url, timeout=3)
        if w_res.status_code == 200:
          cur = w_res.json().get("current", {})
          weather = {
              "temp": cur.get("temperature_2m", 24),
              "humidity": cur.get("relative_humidity_2m", 65),
              "rain": cur.get("precipitation", 0),
              "display_name": city_display_name,
          }
      else:
        st.warning("⚠️ ያስገቡት ከተማ አልተገኘም።")
  except Exception as e:
    st.error(f"የአየር ንብረት መረጃን ማምጣት አልተቻለም: {str(e)}")

if not weather:
  weather = {
      "temp": 24.0,
      "humidity": 65.0,
      "rain": 0.0,
      "display_name": selected_city_name,
  }

st.success(
    f"✅ የተመረጠው አካባቢ: {weather.get('display_name', selected_city_name)} | የሙቀት"
    f" መጠን: {weather['temp']}°C | እርጥበት: {weather['humidity']}% | የዝናብ መጠን:"
    f" {weather['rain']} ሚሜ"
)
st.markdown("---")

# --------------------------------------------------
# 8. INPUT METHODS: IMAGE & VOICE RECORDING
# --------------------------------------------------
col_in1, col_in2 = st.columns(2)

with col_in1:
  st.subheader("📷 የሰብል ፎቶ ግብዓት")
  input_option = st.radio(
      "ዘዴ ይምረጡ:",
      ("📁 ከፋይል መጫን (Upload)", "📸 በቀጥታ ካሜራ ማንሳት"),
      horizontal=True,
  )
  uploaded_file = None
  if input_option == "📁 ከፋይል መጫን (Upload)":
    uploaded_file = st.file_uploader(
        "የቅጠል ፎቶ ይጫኑ", type=["jpg", "jpeg", "png"]
    )
  else:
    uploaded_file = st.camera_input("ካሜራ በመጠቀም ፎቶ ያንሱ")

with col_in2:
  st.subheader("🎤 የድምፅ ጥያቄ እና ግልባጭ")
  st.write("ማይክሮፎኑን በመጫን ጥያቄዎን በአማርኛ በግልጽ ይናገሩ፦")

  if "reset_audio" not in st.session_state:
    st.session_state["reset_audio"] = False

  audio_key = (
      "audio_input_v23_reset"
      if st.session_state["reset_audio"]
      else "audio_input_v23_normal"
  )
  audio_file = st.audio_input("🎙️ ድምፅ ይቅረጹ", key=audio_key)

audio_bytes = None
audio_mime_type = "audio/webm"

if audio_file is not None:
  audio_bytes = audio_file.read()
  if hasattr(audio_file, "type") and audio_file.type:
    audio_mime_type = audio_file.type

  if len(audio_bytes) > 0:
    st.audio(audio_bytes, format=audio_mime_type)

    if (
        "last_audio_size" not in st.session_state
        or st.session_state["last_audio_size"] != len(audio_bytes)
    ):
      if API_READY:
        with st.spinner("🔄 ድምፁን በአማርኛ በመተርጎም ላይ..."):
          try:
            audio_part = types.Part.from_bytes(
                data=audio_bytes, mime_type=audio_mime_type
            )
            trans_prompt = (
                "You are an expert Amharic speech-to-text transcription system."
                " Listen extremely carefully to the attached audio recording"
                " spoken in Amharic. Your ONLY task is to transcribe the exact"
                " words spoken in the audio into proper Amharic script (Ge'ez)."
                " Strict Rules: 1. Do NOT translate the audio into English. 2."
                " Do NOT guess, invent, or hallucinate words if the audio is"
                " unclear. 3. Do NOT add any conversational introduction,"
                " notes, or markdown. 4. Output ONLY the exact Amharic text"
                " spoken in the audio."
            )
            trans_response = generate_content_automatically(
                [audio_part, trans_prompt]
            )
            if trans_response and trans_response.text:
              st.session_state["transcription"] = trans_response.text.strip()
              st.session_state.pop("transcription_error", None)
            else:
              st.session_state.pop("transcription", None)
              st.session_state["transcription_error"] = (
                  "ግልባጭ ማግኘት አልተቻለም። እባክዎ ድምፁን እንደገና ይቅረጹ።"
              )
          except Exception as error:
            st.session_state.pop("transcription", None)
            st.session_state["transcription_error"] = gemini_error_message(error)

          st.session_state["last_audio_size"] = len(audio_bytes)

    if "transcription_error" in st.session_state:
      st.error(st.session_state["transcription_error"])
    elif "transcription" in st.session_state:
      st.success("📝 **የተቀዳው ድምፅ ግልባጭ (Transcription):**")
      st.info(f"_{st.session_state['transcription']}_")

    if (
        "transcription_error" in st.session_state
        or "transcription" in st.session_state
    ):
      if st.button("🗑️ ድምፁን ሰርዞ እንደገና መቅረጽ", type="secondary"):
        st.session_state.pop("transcription", None)
        st.session_state.pop("transcription_error", None)
        st.session_state.pop("last_audio_size", None)
        st.session_state["reset_audio"] = not st.session_state["reset_audio"]
        st.rerun()

st.markdown("---")

# --------------------------------------------------
# 9. DIAGNOSIS & REASONING (IMAGE + WEATHER + VOICE)
# --------------------------------------------------
if "chat_history" not in st.session_state:
  st.session_state["chat_history"] = []

if "initial_analyzed" not in st.session_state:
  st.session_state["initial_analyzed"] = False

if uploaded_file is not None:
  image = Image.open(uploaded_file)
  image.thumbnail((1024, 1024))
  st.image(image, caption="የተመረጠው የሰብል ፎቶ", width="stretch")

  if st.button("🔍 በሽታውን እና የመስኖ ምክር በድምፅ/በምስል መርምር", type="primary"):
    if not API_READY:
      st.error(
          "❌ የ Gemini API ቁልፍ አልተገኘም። እባክዎ በ Streamlit Secrets ወይም በ"
          " Environment Variable ውስጥ GEMINI_API_KEY ያዘጋጁ።"
      )
    else:
      with st.spinner("⏳ AI ፎቶውን እና የአየር ንብረት ሁኔታውን በመተንተን ላይ..."):
        current_location_name = weather.get("display_name", selected_city_name)
        weather_context = f"""
Current Weather Conditions in {current_location_name}:
- Temperature: {weather['temp']} °C
- Relative Humidity: {weather['humidity']}%
- Precipitation (Rain): {weather.get('rain', 0)} mm
"""
        farmer_text_query = st.session_state.get(
            "transcription", "No audio query provided."
        )

        base_prompt = f"""
You are an expert agricultural plant pathologist and irrigation specialist.
{weather_context}
Analyze the uploaded image very carefully. 

CRITICAL VALIDATION INSTRUCTION (የምስል ማረጋገጫ ሕግ):
1. First, check if the uploaded image actually shows a crop, plant, leaf, or agricultural field.
2. If the image shows a HOUSE, A BUILDING, A YARD/LAWN WITHOUT SPECIFIC CROP DISEASE, A HUMAN, AN ANIMAL, OR ANY NON-AGRICULTURAL OBJECT:
   - You MUST explicitly state in Amharic what is in the image (e.g., "ይህ የሰብል ፎቶ ሳይሆን የቤት እና የግቢ ሳር ነው" or "ይህ የሰው/የሌላ ነገር ፎቶ ነው።").
   - Politely refuse to give crop disease diagnoses and firmly instruct the user: "እባክዎ ትክክለኛ የሰብል ወይም የቅጠል ፎቶ ያስገቡ።"
3. Only if it is a genuine crop/plant leaf, proceed with the full agricultural and irrigation analysis based on the weather data from {current_location_name}.

User voice request: "{farmer_text_query}"
Please directly address this specific question in your diagnosis and advice.

CRITICAL INSTRUCTION FOR IRRIGATION (መስኖ):
- If precipitation (rain) > 0 mm, strongly advise farmers NOT to irrigate (ዝናብ ስላለ ውሃ እንዳያጠጡ እና የመስኖ ስራውን እንዲያቆሙ አስጠንቅቅ).
- If it is hot and sunny (high temperature), provide clear instructions on the best time to irrigate to prevent crop stress and disease (ፀሐያማና ሙቀት ካለ ሰብሉ በውሃ እጥረት እንዳይጠቃ ማስታወሻ ስጥ - ለምሳሌ ጥዋት ወይም ማታ ማጠጣት እንደሚገባ).

Respond in Amharic (keep official crop and disease names in English too).

Provide a structured and clear response covering:
1. 🌱 Crop / Plant (የሰብሉ ዓይነት - ወይም ፎቶው የተሳሳተ ከሆነ ስለ ስህተቱ የሚገልጽ ማስታወሻ)
2. 🦠 Disease / Problem (የበሽታው ስም ወይም የምስሉ ትክክለኛ መግለጫ)
3. 🔬 Disease Overview & Weather Connection (ስለ በሽታው ማብራሪያ እና ከአየር ጸባይ ጋር ያለው ዝምድና)
4. 💧 Irrigation & Water Advisory (የመስኖ እና የውሃ አጠቃቀም ምክር - ዝናብ አለ መኖሩን እና መቼ ማጠጣት እንዳለባቸው በግልጽ የሚገልጽ)
5. 💊 Treatment (የሕክምና እርምጃዎች እና ኬሚካሎች)
6. 🛡️ Prevention (የመከላከያ ስልቶች)
7. 🚨 Important Warning (ማስጠንቀቂያ)
8. 📋 Action Plan (የተወሰዱ እርምጃዎች)
"""

        contents = [image, base_prompt]
        if audio_bytes is not None and len(audio_bytes) > 0:
          audio_part = types.Part.from_bytes(
              data=audio_bytes, mime_type=audio_mime_type
          )
          contents.append(audio_part)

        try:
          response = generate_content_automatically(contents)
        except Exception as error:
          st.error(gemini_error_message(error))
        else:
          if response and response.text:
            bot_response_text = response.text
            st.session_state["chat_history"] = [{
                "role": "assistant",
                "content": bot_response_text,
            }]
            st.session_state["initial_analyzed"] = True

            # Save to diagnosis history (session state & SQLite database)
            current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.session_state["diagnosis_history"].append({
                "time": current_time_str,
                "city": current_location_name,
                "image": image,
                "summary": bot_response_text,
            })
            save_diagnosis_to_db(
                current_time_str, current_location_name, bot_response_text
            )

            st.success(
                "✅ አጠቃላይ ትንተናው እና የመስኖ ምክሩ ተጠናቆ ወደ ታሪክ ማህደር ተቀምጧል!"
            )
          else:
            st.error("ምላሽ ማግኘት አልተቻለም። እባክዎ እንደገና ይሞክሩ።")

# --------------------------------------------------
# 10. PERMANENT CHAT & FOLLOW-UP SECTION
# --------------------------------------------------
st.markdown("---")
st.subheader("💬 የባለሙያ ውይይት እና ጥያቄዎች (Chat Assistant)")

for message in st.session_state["chat_history"]:
  with st.chat_message(message["role"]):
    st.markdown(message["content"])

if user_chat_input := st.chat_input("ተጨማሪ ጥያቄዎን እዚህ ይጻፉ..."):
  if not API_READY:
    st.warning("⚠️ የ AI አገልግሎት አልተገናኘም።")
  elif not st.session_state["initial_analyzed"] and uploaded_file is None:
    st.warning("⚠️ እባክዎ በመጀመሪያ የሰብል ፎቶ ይጫኑ ወይም ይመርምሩ።")
  else:
    st.session_state["chat_history"].append(
        {"role": "user", "content": user_chat_input}
    )
    with st.chat_message("user"):
      st.markdown(user_chat_input)

    with st.chat_message("assistant"):
      with st.spinner("🤖 ባለሙያው ምላሽ እየጻፈ ነው..."):
        try:
          chat_context = "\n".join([
              f"{msg['role']}: {msg['content']}"
              for msg in st.session_state["chat_history"]
          ])
          follow_up_prompt = f"""
You are an expert agricultural plant pathologist and irrigation specialist continuing a consultation with a farmer.
Previous conversation context:
{chat_context}

Answer the user's latest follow-up question clearly and professionally in Amharic (keep technical terms in English too).
"""
          img_content = (
              image
              if "image" in locals() and image is not None
              else types.Part.from_text(text="General agriculture query")
          )

          chat_response = generate_content_automatically(
              [img_content, follow_up_prompt]
          )
          bot_reply = chat_response.text

          if bot_reply:
            st.markdown(bot_reply)
            st.session_state["chat_history"].append(
                {"role": "assistant", "content": bot_reply}
            )
          else:
            st.error("ባዶ ምላሽ ተገኝቷል።")
        except Exception as error:
          error_msg = gemini_error_message(error)
          st.error(error_msg)
          st.session_state["chat_history"].append(
              {"role": "assistant", "content": error_msg}
          )