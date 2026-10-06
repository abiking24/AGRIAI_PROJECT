from PIL import Image
import streamlit as st
from transformers import pipeline

# የሞዴል ስም (በቲማቲም ቅጠል በሽታዎች ላይ የሰለጠነ ResNet50 ሞዴል)
MODEL_NAME = "wellCh4n/tomato-leaf-disease-classification-resnet50"
MIN_CONFIDENCE = 60.0  # ከዚህ በታች ከሆነ ማስጠንቀቂያ ያሳያል

# ገጽ ማዋቀር
st.set_page_config(page_title="AgriAI - የሰብል በሽታ ምርመራ", page_icon="🍅")

st.title("🍅 AgriAI: የቲማቲም በሽታ ምርመራ እና መፍትሄ መድረክ")
st.caption(
    "የቲማቲም ቅጠል ፎቶ በመጫን ወይም በካሜራ በማንሳት በሽታውን ይለዩ እና የአማርኛ መፍትሄዎችን"
    " ያግኙ።"
)


# ሞዴሉን በመጫን ላይ (Memorization እንዳይፈጠር በ cache ይያዛል)
@st.cache_resource(show_spinner="AI ሞዴል በመጫን ላይ... እባክዎ ይጠብቁ...")
def load_model():
  return pipeline("image-classification", model=MODEL_NAME)


try:
  clf = load_model()
except Exception as e:
  st.error(f"ሞዴሉን በመጫን ላይ ስህተት ተፈጥሯል: {e}")
  st.stop()

# የበሽታዎች የአማርኛ ትርጉም እና የመፍትሄ/መከላከያ ምክር መዝገብ (Dictionary)
DISEASE_ADVICE_AMHARIC = {
    "Tomato Early blight": {
        "name": "የቀድሞ ጥቁር ነጠብጣብ በሽታ (Early Blight)",
        "description": (
            "በፈንገስ የሚመጣ ሲሆን፣ በቅጠሎች ላይ ቡናማ እስከ ጥቁር ክብ ቅርጽ ያላቸው ነጠብጣቦችን"
            " ይፈጥራ፤ ከታች ባሉት ቅጠሎች ላይ በብዛት ይጀምራል።"
        ),
        "treatment": (
            "1. የተጠቃቁ ዎችን ቅጠሎች ወዲያውኑ ሰብስቦ ማቃጠል ወይም መቀበር።\n2. ለፈንገስ የሚሆን"
            " ተስማሚ ፀረ-ፈንገስ (Fungicide) መድኃኒት በባለሙያ ድጋፍ መርጨት።"
        ),
        "prevention": (
            "1. የሰብል ማሽከርከር (Crop rotation) መጠቀም።\n2. ተክሎችን በበቂ ርቀት መትከል"
            " እና አየር እንዲያገኙ ማድረግ።\n3. ውሃ ሲያጠጡ ቅጠሉ ላይ ሳይሆን ከስር (ከመሬት"
            " ጋር) ማጠጣት።"
        ),
    },
    "Tomato Late blight": {
        "name": "የዘገየ የፈንገስ በሽታ (Late Blight)",
        "description": (
            "በጣም አጥፊ ፈንገስ ሲሆን፣ በቅጠሎች እና ግንዶች ላይ የውሃ የረጠበባቸው የሚመስሉ ግራጫማ"
            " ወይም ጥቁር መልክ ያላቸው ቦታዎችን ይፈጥራል።"
        ),
        "treatment": (
            "1. በሽታው የታየባቸውን እፅዋት ወዲያውኑ አስወግዶ ማጥፋት (ሌሎች ላይ እንዳይዛመት)።\n2."
            " ፈጣን እርምጃ የሚወስዱ የተፈቀዱ ፀረ-ፈንገስ መድኃኒቶችን መጠቀም።"
        ),
        "prevention": (
            "1. በሽታን የሚቋቋሙ የቲማቲም ዝርያዎችን መጠቀም።\n2. እርጥበትን መቀነስ እና አየር"
            " ዝውውር እንዲኖር ማድረግ።"
        ),
    },
    "Tomato healthy": {
        "name": "ጤናማ ሰብል (Healthy)",
        "description": "የተመረመረው የቲማቲም ቅጠል ሙሉ በሙሉ ጤናማ ነው ምንም አይነት የበሽታ ምልክት የለውም።",
        "treatment": "ምንም ዓይነት ሕክምና አያስፈልገውም።",
        "prevention": (
            "1. አዘውትሮ መከታተል።\n2. ተስማሚ የሆነ ማዳበሪያ እና ውሃ አሰጣጥ ስርዓት"
            " መጠበቅ።"
        ),
    },
    "Leaf Mold": {
        "name": "የቅጠል ፈንገስ (Leaf Mold)",
        "description": (
            "በቅጠል ላይ ከላይ ቢጫማ ወይም π-ቅርጽ ያላቸው ትናንሽ ቦታዎች ሲኖሩ ከታችኛው ክፍል ደግሞ"
            " የβεልቬት (Velvet) መሰል ግራጫማ ሹርባ ይኖረዋል።"
        ),
        "treatment": (
            "1. የግሪንሃውስ (Greenhouse) ከሆነ አየር እንዲገባ ማድረግ።\n2. እርጥበትን"
            " መቀነስ።"
        ),
        "prevention": "እርጥበትን መቆጣጠር እና የሰብል ዝውውር ማድረግ።",
    },
}

# የፎቶ ምንጭ መረጫ
source = st.radio(
    "ፎቶ የሚጫኑበትን መንገድ ይምረጡ:", ["ፋይል ጫን (Upload)", "ካሜራ ተጠቀም"], horizontal=True
)

file = None
if source == "ፋይል ጫን (Upload)":
  file = st.file_uploader(
      "የቲማቲም ቅጠል ፎቶ ይምረጡ (JPG, JPEG, PNG)", type=["jpg", "jpeg", "png"]
  )
else:
  file = st.camera_input("የቅጠል ፎቶ ያንሱ")

if file is not None:
  img = Image.open(file).convert("RGB")
  st.image(img, caption="የተጫነው ፎቶ", use_container_width=True)

  with st.spinner("AI ፎቶውን በመመርመር ላይ ነው..."):
    results = clf(img, top_k=3)
    best = results[0]
    raw_label = best["label"]
    conf = best["score"] * 100

    # ውጤቱን ማሳየት
    st.markdown("---")
    st.subheader("📊 የምርመራ ውጤት")

    # የጥንቃቄ ገደብ ማረጋገጫ (Confidence Threshold)
    if conf < MIN_CONFIDENCE:
      st.warning(
          f"⚠️ የእርግጠኛነት መጠኑ ዝቅተኛ ነው ({conf:.1f}%). ፎቶው ግልጽ"
          " አለመሆኑን፣ ወይም ቅጠል ብቻ የሌለበት መሆኑን ያረጋግጡ። እባክዎ የተሻለ እና ግልጽ"
          " የቅጠል ፎቶ እንደገና ያስገቡ።"
      )
    else:
      # ከተቻለ የአማርኛ መግለጫ ማምጣት፣ ካልሆነ የራሱን NewLabel ማሳየት
      matched_disease = None
      for key in DISEASE_ADVICE_AMHARIC:
        if key.lower() in raw_label.lower() or raw_label.lower() in key.lower():
          matched_disease = DISEASE_ADVICE_AMHARIC[key]
          break

      if not matched_disease:
        # ካልተገኘ ነባሩን እንጠቀማለን
        matched_disease = {
            "name": raw_label.replace("_", " "),
            "description": "ይህ የተለየ የበሽታ ዓይነት በስርዓቱ ተለይቷል።",
            "treatment": "እባክዎ የአካባቢዎን የግብርና ባለሙያ ያማክሩ።",
            "prevention": "ንጹህ የጸዳ አሰራር መከተል።",
        }

      st.success(f"**የተገኘው ችግር:** {matched_disease['name']}")
      st.progress(
          min(int(conf), 100), text=f"እርግጠኛነት (Confidence): {conf:.1f}%"
      )

      # የአማርኛ ምክር ማዕቀፍ (Box)
      st.markdown("### 💡 የአማርኛ የባለሙያ ምክር እና መፍትሄዎች")
      st.info(f"**ስለ በሽታው:**\n{matched_disease['description']}")

      col1, col2 = st.columns(2)
      with col1:
        st.warning(f"**💊 የሕክምና እርምጃዎች:**\n{matched_disease['treatment']}")
      with col2:
        st.success(f"**🛡️ የመከላከያ መንገዶች:**\n{matched_disease['prevention']}")

    # ሌሎች ግምቶችን ማሳየት (Expander)
    with st.expander("🔍 ሌሎች የ AI ግምቶች (Top Predictions)"):
      for r in results:
        st.write(
            f"• **{r['label'].replace('_', ' ')}** — {r['score'] * 100:.1f}%"
        )

  st.markdown("---")
  st.info(
      "ማሳሰቢያ፡ ይህ መተግበሪያ የተሰራው በ AI ሞዴል ግምት ላይ በመመስረት ሲሆን፣ ለተሻለ"
      " እና ትክክለኛ ውሳኔ ሁልጊዜ የአካባቢዎን የግብርና ባለሙያ ምክር ያክሉ።"
  )