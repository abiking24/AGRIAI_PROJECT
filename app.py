from pathlib import Path

import streamlit as st
from PIL import Image

from src.predictor import DiseasePredictor
from src.disease_info import DISEASE_INFO


st.set_page_config(page_title="AgriAI - Crop Disease Detection", layout="centered")


@st.cache_resource
def load_predictor(checkpoint_mtime):
    return DiseasePredictor(
        model_path=Path(__file__).resolve().parent / "crop_disease_model.pth"
    )


st.title("AgriAI: የሰብል በሽታ መለያ")
st.write("የሰብሉን ፎቶ ያስገቡ እና የሞዴሉን ግምት ከአጠቃላይ መረጃ ጋር ይመልከቱ።")

checkpoint_path = Path(__file__).resolve().parent / "crop_disease_model.pth"
checkpoint_mtime = (
    checkpoint_path.stat().st_mtime_ns if checkpoint_path.is_file() else None
)
predictor = load_predictor(checkpoint_mtime)
if not predictor.is_ready:
    st.warning(predictor.status_message)
    st.stop()

uploaded_file = st.file_uploader(
    "የሰብል ፎቶ እዚህ ይስቀሉ...",
    type=["jpg", "jpeg", "png"],
)

if uploaded_file is not None:
    image = Image.open(uploaded_file).convert("RGB")
    st.image(image, caption="የተሰቀለው ፎቶ", use_container_width=True)

    if st.button("በሽታውን መርምር"):
        result, status = predictor.predict(image)
        if status != "Success":
            st.warning(status)
        elif result not in DISEASE_INFO:
            st.error("ስህተት ተፈጥሯል፤ እባክዎ እንደገና ይሞክሩ።")
        else:
            info = DISEASE_INFO[result]
            with st.container(border=True):
                if result == "healthy":
                    st.success(f"የሰብሉ ሁኔታ፦ {info['disease_name']}")
                else:
                    st.error(f"የተገኘው ሁኔታ፦ {info['disease_name']}")

                st.markdown("**ምክንያት / ማስታወሻ**")
                st.write(info["cause"])
                st.markdown("**የሚመከሩ እርምጃዎች**")
                st.markdown("\n".join(f"- {remedy}" for remedy in info["remedies"]))
                st.caption(info["limitation"])