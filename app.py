import requests
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# --------------------------------------------------
# 1. PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="AgriAI V2 - የድምፅ ግልባጭ ማስተካከያ", page_icon="🌿", layout="wide"
)

# --------------------------------------------------
# 2. API CONFIGURATION
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
# 3. APP HEADER
# --------------------------------------------------
st.title("🌿 AgriAI V2 - ስማርት የሰብል በሽታ መለያ (የተስተካከለ የድምፅ ግልባጭ)")
st.write(
    "የሰብል ፎቶ በመጫን፣ የአካባቢውን የአየር ጸባይ በማካተት እና ጥያቄዎን በድምፅ በመቅረጽ"
    " ትክክለኛ የባለሙያ ምክር ያግኙ።"
)

# --------------------------------------------------
# 4. LOCATION & WEATHER (Auto / Manual)
# --------------------------------------------------
st.subheader("📍 የአካባቢዎ እና የአየር ንብረት ሁኔታ")
col_w1, col_w2 = st.columns(2)
with col_w1:
  selected_city = st.selectbox(
      "ከተማ ይምረጡ:",
      [
          "ዲላ (Dilla)",
          "አዲስ አበባ (Addis Ababa)",
          "ሃዋሳ (Hawassa)",
          "ባህር ዳር (Bahir Dar)",
          "መቀሌ (Mekelle)",
      ],
  )
with col_w2:
  weather_mode = st.radio(
      "የአየር ንብረት መረጃ አቀራረብ:",
      ("በራስ-ሰር (Auto)", "በእጅ ማስገባት (Manual)"),
      horizontal=True,
  )

weather = {}
if weather_mode == "በራስ-ሰር (Auto)":
  coords = {
      "ዲላ (Dilla)": (6.4089, 38.3117),
      "አዲስ አበባ (Addis Ababa)": (9.03, 38.74),
      "ሃዋሳ (Hawassa)": (7.05, 38.47),
      "ባህር ዳር (Bahir Dar)": (11.59, 37.39),
      "መቀሌ (Mekelle)": (13.49, 39.47),
  }
  lat, lon = coords.get(selected_city, (6.4089, 38.3117))
  try:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,precipitation"
    res = requests.get(url, timeout=3)
    if res.status_code == 200:
      cur = res.json().get("current", {})
      weather = {
          "temp": cur.get("temperature_2m", 24),
          "humidity": cur.get("relative_humidity_2m", 65),
          "rain": cur.get("precipitation", 0),
      }
  except Exception:
    pass

if not weather:
  m_col1, m_col2 = st.columns(2)
  weather["temp"] = m_col1.number_input(
      "የሙቀት መጠን (°C) በእጅ ያስገቡ", value=24.0
  )
  weather["humidity"] = m_col2.number_input(
      "የእርጥበት መጠን (%) በእጅ ያስገቡ", value=65.0
  )
  weather["rain"] = 0.0

st.success(
    f"✅ አከባቢ: {selected_city} | የሙቀት መጠን: {weather['temp']}°C | እርጥበት:"
    f" {weather['humidity']}%"
)
st.markdown("---")

# --------------------------------------------------
# 5. INPUT METHODS: IMAGE & VOICE RECORDING WITH ROBUST TRANSCRIPTION
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
    uploaded_file = st.file_uploader("የቅጠል ፎቶ ይጫኑ", type=["jpg", "jpeg", "png"])
  else:
    uploaded_file = st.camera_input("ካሜራ በመጠቀም ፎቶ ያንሱ")

with col_in2:
  st.subheader("🎤 የድምፅ ጥያቄ እና ግልባጭ")
  st.write("ማይክሮፎኑን በመጫን ጥያቄዎን በአማርኛ በግልጽ ይናገሩ፦")

  if "reset_audio" not in st.session_state:
    st.session_state["reset_audio"] = False

  audio_key = (
      "audio_input_v6_reset"
      if st.session_state["reset_audio"]
      else "audio_input_v6_normal"
  )
  audio_file = st.audio_input("🎙️ ድምፅ ይቅረጹ", key=audio_key)

  if audio_file is not None:
    st.session_state["reset_audio"] = False

audio_bytes = None
if audio_file is not None:
  audio_bytes = audio_file.read()
  if len(audio_bytes) > 0:
    st.audio(audio_bytes, format="audio/wav")

    # የተሻሻለ እና አስተማማኝ የአማርኛ ድምፅ ግልባጭ (Transcription) በአዲሱ ሞዴል
    if (
        "last_audio_size" not in st.session_state
        or st.session_state["last_audio_size"] != len(audio_bytes)
    ):
      if API_READY:
        with st.spinner("🔄 ድምፁን በአማርኛ በትክክል በመተርጎም ላይ..."):
          try:
            # አዲሱን የተጠቆመውን gemini-3.8-flash ሞዴል እንጠቀማለን
            trans_response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[
                    types.Part.from_bytes(
                        data=audio_bytes, mime_type="audio/wav"
                    ),
                    (
                        "Listen to this audio recorded by an Ethiopian farmer."
                        " Transcribe what they said into accurate Amharic"
                        " text. Provide ONLY the exact Amharic transcribed"
                        " text."
                    ),
                ],
            )
            if trans_response and trans_response.text:
              st.session_state["transcription"] = trans_response.text.strip()
            else:
              st.session_state["transcription"] = (
                  "ድምፁ አልተሰማም ወይም ግልባጭ አልተገኘም።"
              )
            st.session_state["last_audio_size"] = len(audio_bytes)
          except Exception as e:
            st.session_state["transcription"] = (
                f"የግልባጭ ስህተት አጋጥሟል: {str(e)}"
            )

    if "transcription" in st.session_state:
      st.success("📝 **የተቀዳው ድምፅ ግልባጭ (Transcription):**")
      st.info(f"_{st.session_state['transcription']}_")

      # 🗑️ ድምፁን ሰርዞ እንደገና ለማስጀመር የሚያስችል ቁልፍ
      if st.button("🗑️ ግልባጩ ትክክል አይደለም (ድምፁን ሰርዞ እንደገና መቅረጽ)", type="secondary"):
        st.session_state.pop("transcription", None)
        st.session_state.pop("last_audio_size", None)
        st.session_state["reset_audio"] = not st.session_state["reset_audio"]
        st.rerun()
  else:
    audio_bytes = None

detailed_explanation = st.checkbox(
    "📖 ተጨማሪ ጥልቅ እና ዝርዝር ማብራሪያ አሳይ (Detailed Analysis)"
)
st.markdown("---")

# --------------------------------------------------
# 6. ANALYSIS SECTION WITH MULTIMODAL (IMAGE + AUDIO + WEATHER)
# --------------------------------------------------
if uploaded_file is not None:
  image = Image.open(uploaded_file)
  image.thumbnail((1024, 1024))
  st.image(image, caption="የተመረጠው የሰብል ፎቶ", use_container_width=True)

  if st.button("🔍 በሽታውን በምስል፣ በአየር ንብረት እና በድምፅ መርምር", type="primary"):
    if not API_READY:
      st.error("❌ Gemini API ዝግጁ አይደለም።")
    else:
      with st.spinner(
          "⏳ AI ፎቶውን፣ የድምፅ መልእክቱን እና የአየር ንብረት ሁኔታውን በመተንተን ላይ..."
      ):

        weather_context = f"""
Current Weather Conditions in {selected_city}:
- Temperature: {weather['temp']} °C
- Relative Humidity: {weather['humidity']}%
- Precipitation: {weather.get('rain', 0)} mm
"""

        farmer_text_query = st.session_state.get(
            "transcription", "No audio query provided."
        )

        base_prompt = f"""
You are an expert agricultural plant pathologist.
{weather_context}
Analyze the uploaded crop leaf image and the user's local weather data. 
The farmer's voice request was transcribed as: "{farmer_text_query}"
Please directly address this specific question in your diagnosis and advice.
Respond in Amharic (keep official crop and disease names in English too).

Provide a structured and clear response covering:
1. 🌱 Crop / Plant (የሰብሉ ዓይነት)
2. 🦠 Disease / Problem (የበሽታው ስም - English & Amharic)
3. 🔬 Disease Overview & Weather Connection (ስለ በሽታው ማብራሪያ እና ከአየር ጸባይ ጋር ያለው ዝምድና)
4. 💊 Treatment (የሕክምና እርምጃዎች እና ኬሚካሎች)
5. 🛡️ Prevention (የመከላከያ ስልቶች)
6. 🚨 Important Warning (ማስጠንቀቂያ)
7. 📋 Action Plan (የተወሰዱ እርምጃዎች)
"""

        contents = [image, base_prompt]

        if audio_bytes is not None:
          audio_part = types.Part.from_bytes(
              data=audio_bytes, mime_type="audio/wav"
          )
          contents.append(audio_part)

        response_text = None
        models_to_try = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]

        success = False
        for model_name in models_to_try:
          try:
            response = client.models.generate_content(
                model=model_name, contents=contents
            )
            response_text = response.text
            success = True
            break
          except Exception as e:
            continue

        if success and response_text:
          st.success("✅ አጠቃላይ ትንተናው በተሳካ ሁኔታ ተጠናቋል!")
          st.markdown("---")
          st.markdown(response_text)
        else:
          st.error(
              "❌ የጥያቄ ገደብ (Quota) አልቋል ወይም ስህተት ተፈጥሯል። እባክዎ ከጥቂት"
              " ሰዓታት በኋላ እንደገና ይሞክሩ።"
          )
else:
  st.info("ℹ️ እባክዎ ለመጀመር የሰብል ቅጠል ፎቶ ይጫኑ ወይም ያንሱ።")