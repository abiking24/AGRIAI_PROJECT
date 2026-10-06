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
            with st.container():
                # Main prediction summary
                if result == "healthy":
                    st.success(f"የሰብሉ ሁኔታ፦ {info['disease_name']}")
                else:
                    st.error(f"የተገኘው ሁኔታ፦ {info['disease_name']}")

                st.markdown("**ምክንያት / ማስታወሻ**")
                st.write(info["cause"])

                st.markdown("**የሚመከሩ እርምጃዎች**")
                st.markdown("\n".join(f"- {remedy}" for remedy in info.get("remedies", [])))

                st.caption(info.get("limitation", ""))

                # If a generic "diseased" result, offer common tomato-disease advice in Amharic
                tomato_dict = DISEASE_INFO.get("tomato_common", {})
                if result == "diseased" and tomato_dict:
                    with st.expander("ተጨማሪ የቲማቲም ምክር (አማርኛ)"):
                        # build options excluding the note key
                        options = [k for k in tomato_dict.keys() if k != "note"]
                        if options:
                            choice = st.selectbox("እባኮትን ከዚህ ውስጥ አንዱን ይምረጡ:", options)
                            chosen = tomato_dict.get(choice, {})

                            st.subheader(chosen.get("amharic_name", choice))
                            st.markdown("**ምክንያት**")
                            st.write(chosen.get("cause", "-") )

                            if chosen.get("remedies"):
                                st.markdown("**ሕክምና / የሚመከሩ እርምጃዎች**")
                                st.markdown("\n".join(f"- {r}" for r in chosen["remedies"]))

                            if chosen.get("prevention"):
                                st.markdown("**መከላከያ (Prevention)**")
                                st.markdown("\n".join(f"- {p}" for p in chosen["prevention"]))

                            # global note/disclaimer
                            note = tomato_dict.get("note")
                            if note:
                                st.info(note)
                        else:
                            st.write("ከተዘርዘሩ የቲማቲም በሽታዎች መረጃ ለማቅረብ አልተገኘም።")
