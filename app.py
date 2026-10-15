import os
import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

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
def _configured_value(secret_key, env_key):
  """Read a private setting from Streamlit secrets or the process environment."""
  try:
    value = st.secrets.get(secret_key, "")
    if value is not None and str(value).strip():
      return str(value).strip()
  except Exception:
    # Streamlit secrets may be unavailable when running locally.
    pass

  value = os.environ.get(env_key, "")
  if value and value.strip():
    return value.strip()
  return ""


def get_api_key() -> str:
  key = _configured_value("GEMINI_API_KEY", "GEMINI_API_KEY")
  return "" if key == "YOUR_GEMINI_API_KEY" else key


def get_telegram_credentials():
  """Return Telegram credentials without exposing them to the Streamlit UI."""
  try:
    telegram_secrets = st.secrets.get("telegram", {})
  except Exception:
    telegram_secrets = {}
  if not hasattr(telegram_secrets, "get"):
    telegram_secrets = {}

  token = (
      str(telegram_secrets.get("bot_token", "") or "").strip()
      or _configured_value("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
  )
  chat_id = (
      str(telegram_secrets.get("expert_telegram_chat_id", "") or "").strip()
      or str(telegram_secrets.get("expert_chat_id", "") or "").strip()
      or str(telegram_secrets.get("chat_id", "") or "").strip()
      or _configured_value(
          "EXPERT_TELEGRAM_CHAT_ID", "EXPERT_TELEGRAM_CHAT_ID"
      )
      or _configured_value("TELEGRAM_EXPERT_CHAT_ID", "TELEGRAM_EXPERT_CHAT_ID")
  )
  return token, chat_id


def redact_configured_credentials(text):
  safe_text = str(text)
  credentials = (get_api_key(), *get_telegram_credentials())
  for credential in credentials:
    if credential:
      safe_text = safe_text.replace(credential, "[redacted]")
  return safe_text


def normalize_phone_number(phone_number):
  """Accept local ten-digit numbers or valid international E.164 numbers."""
  raw_value = str(phone_number or "").strip()
  if not raw_value:
    return ""
  if not re.fullmatch(r"[+0-9() .-]+", raw_value):
    return ""

  digits = re.sub(r"\D", "", raw_value)
  if re.fullmatch(r"0\d{9}", digits):
    return digits
  if raw_value.startswith("+"):
    return "+" + digits if re.fullmatch(r"[1-9]\d{7,14}", digits) else ""
  if re.fullmatch(r"[1-9]\d{7,14}", digits):
    return "+" + digits
  return ""


def validate_ethiopian_phone(phone_number):
  """Require an Ethiopian mobile number in 09XXXXXXXX or 07XXXXXXXX form."""
  value = str(phone_number or "").strip()
  return bool(re.fullmatch(r"0[79]\d{8}", value))


def validate_email(email_address):
  value = str(email_address or "").strip()
  if not value:
    return True
  return bool(
      re.fullmatch(
          r"[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
          value,
      )
  )


def hash_password(password, salt=None):
  salt = salt or secrets.token_bytes(16)
  digest = hashlib.pbkdf2_hmac(
      "sha256", password.encode("utf-8"), salt, 310_000
  )
  return salt.hex(), digest.hex()


def verify_password(password, salt_hex, password_hash):
  try:
    salt = bytes.fromhex(salt_hex)
    _, candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)
  except (TypeError, ValueError):
    return False


def _markdown_v2_escape(text):
  special_chars = r"_*[]()~`>#+-=|{}.!\\"
  return "".join("\\" + char if char in special_chars else char for char in text)


def _truncate_markdown_text(text, max_length):
  """Truncate before escaping so MarkdownV2 escape sequences stay intact."""
  output = []
  used = 0
  for char in text:
    escaped = _markdown_v2_escape(char)
    if used + len(escaped) > max_length:
      break
    output.append(escaped)
    used += len(escaped)
  result = "".join(output)
  if len(result) < len(_markdown_v2_escape(text)):
    result = result.rstrip() + "…"
  return result


def extract_alert_metadata(response_text):
  """Parse explicit model classification; missing or uncertain data never alerts."""
  pattern = re.compile(
      r"<ALERT_METADATA>\s*(.*?)\s*</ALERT_METADATA>",
      flags=re.IGNORECASE | re.DOTALL,
  )
  match = pattern.search(response_text or "")
  if not match:
    return (response_text or "").strip(), {
        "status": "UNCERTAIN",
        "crop": "Not identified",
        "pathology": "Not classified",
        "pathology_am": "በሽታው ገና አልተረጋገጠም።",
        "severity": "HIGH",
        "risk_context": "Weather risk requires expert assessment.",
        "risk_context_am": "የአየር ሁኔታው የባለሙያ ግምገማ ይፈልጋል።",
        "inspection": "Contact the farmer and assess the affected field area.",
        "inspection_am": "አርሶ አደሩን አነጋግረው የተጠቃውን የእርሻ ክፍል ይገምግሙ።",
        "treatment": "Confirm the diagnosis and authorize only locally registered treatment.",
        "treatment_am": "ምርመራውን አረጋግጠው በአካባቢው የተፈቀደ ሕክምና ብቻ ያጽድቁ።",
        "mitigation": "Provide the farmer with a case-specific sanitation and irrigation plan.",
        "mitigation_am": "ለአርሶ አደሩ ለዚህ ጉዳይ የተለየ የእርሻ ንጽህናና የመስኖ ዕቅድ ያዘጋጁ።",
    }

  fields = {}
  for line in match.group(1).splitlines():
    key, separator, value = line.partition(":")
    if separator:
      fields[key.strip().upper()] = value.strip()

  status_match = re.search(
      r"\b(DISEASE|HEALTHY|UNCERTAIN)\b",
      re.sub(r"[*_`\[\]]", "", fields.get("STATUS", "").upper()),
  )
  status = status_match.group(1) if status_match else "UNCERTAIN"
  severity_match = re.search(
      r"\b(HIGH|CRITICAL)\b",
      re.sub(r"[*_`\[\]]", "", fields.get("SEVERITY", "").upper()),
  )
  severity = severity_match.group(1) if severity_match else "HIGH"

  visible_report = (response_text[:match.start()] + response_text[match.end():]).strip()
  visible_report = re.sub(
      r"```(?:[a-zA-Z]*)?\s*```", "", visible_report
  ).strip()
  pathology_en = fields.get("PATHOLOGY_EN") or fields.get("PATHOLOGY") or "Not specified"
  def clean_field(key, default, max_chars):
    value = fields.get(key) or default
    return re.sub(r"\s+", " ", str(value)).strip()[:max_chars]

  metadata = {
      "status": status,
      "crop": fields.get("CROP", "Not identified")[:120],
      "pathology": re.sub(r"\s+", " ", pathology_en).strip()[:180],
      "pathology_am": clean_field(
          "PATHOLOGY_AM", "በሽታው ገና አልተረጋገጠም።", 120
      ),
      "severity": severity,
      "risk_context": clean_field(
          "RISK_EN", "Weather risk requires expert assessment.", 120
      ),
      "risk_context_am": clean_field(
          "RISK_AM", "የአየር ሁኔታው የባለሙያ ግምገማ ይፈልጋል።", 120
      ),
      "inspection": clean_field(
          "INSPECTION_EN", "Contact the farmer and assess the affected field area.", 120
      ),
      "inspection_am": clean_field(
          "INSPECTION_AM", "አርሶ አደሩን አነጋግረው የተጠቃውን የእርሻ ክፍል ይገምግሙ።", 120
      ),
      "treatment": clean_field(
          "TREATMENT_EN",
          "Confirm the diagnosis and authorize only locally registered treatment.",
          120,
      ),
      "treatment_am": clean_field(
          "TREATMENT_AM", "ምርመራውን አረጋግጠው በአካባቢው የተፈቀደ ሕክምና ብቻ ያጽድቁ።", 120
      ),
      "mitigation": clean_field(
          "MITIGATION_EN",
          "Provide a case-specific sanitation and irrigation plan.",
          120,
      ),
      "mitigation_am": clean_field(
          "MITIGATION_AM",
          "ለዚህ ጉዳይ የተለየ የእርሻ ንጽህናና የመስኖ ዕቅድ ያዘጋጁ።",
          120,
      ),
  }
  return visible_report, metadata


def send_alert_to_extension_worker(
    city,
    farmer_name,
    user_id,
    phone_number,
    email,
    disease_status,
    case_metadata,
    timestamp=None,
):
  """Send an urgent alert only for a positively classified crop disease."""
  pathology_name = str(case_metadata.get("pathology", "")).strip()
  if (
      str(disease_status).strip().upper() != "DISEASE"
      or pathology_name.lower()
      in {
          "", "none", "healthy", "no disease", "not detected", "unknown",
          "not specified", "not classified",
      }
  ):
    return False

  normalized_phone = normalize_phone_number(phone_number)
  if not normalized_phone:
    st.warning(
        "A crop disease was detected, but the registered phone number is invalid. "
        "The contact details must be corrected before dispatching the alert."
    )
    return False

  bot_token, expert_chat_id = get_telegram_credentials()
  if not bot_token or not expert_chat_id:
    st.error(
        "Telegram notification is not configured. Set TELEGRAM_BOT_TOKEN and "
        "EXPERT_TELEGRAM_CHAT_ID in Streamlit secrets or environment variables."
    )
    return False

  timestamp = str(
      timestamp
      or datetime.now(ZoneInfo("Africa/Addis_Ababa")).strftime(
          "%Y-%m-%d %H:%M:%S EAT"
      )
  )[:80]
  inspection_am = (
      f"በአፋጣኝ ከአርሶ አደሩ ጋር በስልክ {normalized_phone} ይገናኙ፤ "
      f"የተጠቃውን መጠን በእርሻው ላይ ይገምግሙ። {case_metadata['inspection_am']}"
  )[:220]
  inspection_en = (
      f"Contact the farmer at {normalized_phone} promptly and inspect the "
      f"affected area onsite. {case_metadata['inspection']}"
  )[:220]
  severity_en = "CRITICAL" if case_metadata["severity"] == "CRITICAL" else "HIGH"
  severity_am = "ወሳኝ" if severity_en == "CRITICAL" else "ከፍተኛ"
  email_value = str(email or "አልቀረበም / Not Provided")[:100]
  farmer_profile = f"{farmer_name or 'Unknown'} / {user_id or 'Unknown'}"
  details = [
      "🚨 *AGRE AI — ኦፊሴላዊ የመስክ ሕክምና ማዘዣ ሪፖርት*",
      "🚨 *OFFICIAL FIELD DISPATCH & PRESCRIPTION* 🚨",
      "",
      f"📋 *የኬዝ መለያ / Case Ref:* {_markdown_v2_escape(str(user_id or 'Unknown')[:32])}",
      f"👤 *አርሶ አደር / Registered Farmer:* {_markdown_v2_escape(farmer_profile[:120])}",
      f"📞 *የስልክ ቁጥር / Direct Phone:* {_markdown_v2_escape(normalized_phone[:40])}",
      f"✉️ *ኢሜይል / Email:* {_markdown_v2_escape(email_value)}",
      f"📍 *የእርሻ መገኛ / Farm Coordinates:* {_markdown_v2_escape(str(city or 'Unknown')[:150])}",
      f"⏰ *የምርመራ ሰዓት / Timestamp:* {_markdown_v2_escape(timestamp)}",
      "",
      "🦠 *የተረጋገጠ በሽታ / Diagnosed Pathology:*",
      _markdown_v2_escape(
          str(case_metadata["pathology_am"] or "በሽታው አልተገለጸም።")[:140]
      ),
      f"_{_markdown_v2_escape(str(case_metadata['pathology'] or 'Not specified')[:150])}_",
      "",
      r"📊 *የአካባቢ የአየር ንብረት ትንተና / Agro\-Climatic Context:*",
      f"{severity_am}: {_markdown_v2_escape(str(case_metadata['risk_context_am'])[:140])}",
      f"_{severity_en}: {_markdown_v2_escape(str(case_metadata['risk_context'])[:140])}_",
      "",
      r"🛠️ *ለባለሙያው የተሰጠ ኦፊሴላዊ የድርጊት ትዕዛዝ / Mandated Expert Action:*",
      "",
      r"• *የመስክ ምልከታ ትዕዛዝ / On\-Site Verification:*",
      _markdown_v2_escape(inspection_am),
      f"_{_markdown_v2_escape(inspection_en)}_",
      "",
      r"• *የኬሚካል ማዘዣ / Authorized Treatment:*",
      _markdown_v2_escape(str(case_metadata["treatment_am"])[:180]),
      f"_{_markdown_v2_escape(str(case_metadata['treatment'])[:180])}_",
      "",
      r"• *የመከላከል እና የቁጥጥር ስልት / Mitigation & Control Protocol:*",
      _markdown_v2_escape(str(case_metadata["mitigation_am"])[:180]),
      f"_{_markdown_v2_escape(str(case_metadata['mitigation'])[:180])}_",
  ]
  message = "\n".join(details)

  endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
  payload = {
      "chat_id": expert_chat_id,
      "text": message,
      "parse_mode": "MarkdownV2",
      "disable_web_page_preview": True,
  }

  try:
    response = requests.post(endpoint, json=payload, timeout=15)
    if response.status_code != 200:
      st.error(
          "Telegram API returned HTTP "
          f"{response.status_code}: {redact_configured_credentials(response.text)}"
      )
      return False

    try:
      telegram_result = response.json()
    except ValueError:
      st.error(
          "Telegram returned HTTP 200 with an unreadable response: "
          f"{redact_configured_credentials(response.text)}"
      )
      return False

    if telegram_result.get("ok") is not True:
      st.error(
          "Telegram rejected the message: "
          f"{redact_configured_credentials(response.text)}"
      )
      return False

    st.success("Telegram notification sent successfully.")
    return True
  except Exception as error:
    st.error(f"Telegram notification failed: {redact_configured_credentials(error)}")
    return False


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
  return f"የምርመራ ሂደቱ አልተሳካም: {redact_configured_credentials(error)}"


# --------------------------------------------------
# 4. DATABASE & HISTORY PERSISTENCE (SQLite)
# --------------------------------------------------
DB_PATH = "agriai_history.db"


def init_db():
  try:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
      conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone_number TEXT NOT NULL UNIQUE,
                email TEXT,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
      conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                crop_name TEXT,
                result_text TEXT,
                location_name TEXT,
                crop_pathology_details TEXT,
                ai_summary TEXT,
                user_id TEXT,
                phone_number TEXT,
                email TEXT
            )
        """)
      existing_columns = {
          row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()
      }
      new_columns = {
          "location_name": "TEXT",
          "crop_pathology_details": "TEXT",
          "ai_summary": "TEXT",
          "user_id": "TEXT",
          "phone_number": "TEXT",
          "email": "TEXT",
      }
      for column_name, column_type in new_columns.items():
        if column_name not in existing_columns:
          conn.execute(
              f"ALTER TABLE analyses ADD COLUMN {column_name} {column_type}"
          )
      # Keep older history readable after upgrading the schema.
      conn.execute(
          "UPDATE analyses SET location_name = crop_name "
          "WHERE location_name IS NULL"
      )
      conn.execute(
          "UPDATE analyses SET ai_summary = result_text WHERE ai_summary IS NULL"
      )
  except Exception as e:
    print(f"Database init error: {e}")


def save_to_db(
    timestamp,
    location_name,
    crop_pathology_details,
    ai_summary,
    user_id,
    phone_number="",
    email="",
):
  try:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
      conn.execute(
          """INSERT INTO analyses (
                 timestamp, crop_name, result_text, location_name,
                 crop_pathology_details, ai_summary, user_id, phone_number, email
             ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
          (
              timestamp,
              location_name,
              ai_summary,
              location_name,
              crop_pathology_details,
              ai_summary,
              user_id,
              phone_number,
              email,
          ),
      )
    return True
  except Exception as e:
    print(f"Database save error: {e}")
    return False


def create_user(full_name, phone_number, email, password):
  salt, password_hash = hash_password(password)
  user_id = f"AGRI-USER-{secrets.token_hex(8).upper()}"
  created_at = datetime.now(
      ZoneInfo("Africa/Addis_Ababa")
  ).strftime("%Y-%m-%d %H:%M:%S EAT")
  try:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
      conn.execute(
          """INSERT INTO users (
                 user_id, full_name, phone_number, email,
                 password_salt, password_hash, created_at
             ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
          (user_id, full_name.strip(), phone_number, email.strip() or None,
           salt, password_hash, created_at),
      )
    return {
        "user_id": user_id,
        "full_name": full_name.strip(),
        "phone_number": phone_number,
        "email": email.strip(),
        "created_at": created_at,
    }, None
  except sqlite3.IntegrityError:
    return None, "An account already exists for this phone number."
  except sqlite3.Error:
    return None, "Account registration could not be completed. Please try again."


def authenticate_user(phone_number, password):
  try:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
      row = conn.execute(
          """SELECT user_id, full_name, phone_number, email,
                    password_salt, password_hash, created_at
             FROM users WHERE phone_number = ?""",
          (phone_number,),
      ).fetchone()
    if row and verify_password(password, row[4], row[5]):
      return {
          "user_id": row[0],
          "full_name": row[1],
          "phone_number": row[2],
          "email": row[3] or "",
          "created_at": row[6],
      }
  except sqlite3.Error:
    return None
  return None


def load_diagnoses_from_db(user_id):
  try:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
      rows = conn.execute(
          """SELECT timestamp, COALESCE(location_name, crop_name),
                    COALESCE(ai_summary, result_text), crop_pathology_details
             FROM analyses WHERE user_id = ? ORDER BY id DESC""",
          (user_id,),
      ).fetchall()
    return [
        {"time": r[0], "city": r[1], "summary": r[2], "details": r[3]}
        for r in rows
    ]
  except Exception as e:
    print(f"Database load error: {e}")
    return []


def clear_db_history(user_id):
  try:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
      conn.execute("DELETE FROM analyses WHERE user_id = ?", (user_id,))
  except Exception as e:
    print(f"Database clear error: {e}")


init_db()

st.session_state.setdefault("auth_user", None)

if st.session_state["auth_user"] is None:
  st.title("Agre AI | Farmer and extension platform")
  st.caption("Dilla University • Secure account access")
  st.write("Sign in or create an account to access crop diagnosis and prescriptions.")
  login_tab, signup_tab = st.tabs(["Login", "Sign up"])

  with login_tab:
    with st.form("login_form"):
      login_phone = st.text_input(
          "Phone number", placeholder="09XXXXXXXX", max_chars=10
      )
      login_password = st.text_input(
          "Password", type="password", max_chars=128
      )
      login_submitted = st.form_submit_button("Log in", type="primary")
    if login_submitted:
      if not validate_ethiopian_phone(login_phone):
        st.error("Enter a valid Ethiopian mobile number: 10 digits starting with 09 or 07.")
      elif not login_password:
        st.error("Enter your password.")
      elif len(login_password) > 128:
        st.error("Password must not exceed 128 characters.")
      else:
        normalized_login_phone = re.sub(r"\D", "", login_phone)
        account = authenticate_user(normalized_login_phone, login_password)
        if account:
          st.session_state["auth_user"] = account
          st.session_state["auth_session_id"] = secrets.token_hex(8)
          st.rerun()
        st.error("Phone number or password is incorrect.")

  with signup_tab:
    with st.form("signup_form"):
      signup_name = st.text_input("Full name", max_chars=100)
      signup_phone = st.text_input(
          "Phone number *", placeholder="09XXXXXXXX", max_chars=10
      )
      signup_email = st.text_input(
          "Email address (optional)", max_chars=254
      )
      signup_password = st.text_input(
          "Password", type="password", max_chars=128
      )
      signup_password_confirm = st.text_input(
          "Confirm password", type="password", max_chars=128
      )
      signup_submitted = st.form_submit_button("Create account", type="primary")
    if signup_submitted:
      if not signup_name.strip():
        st.error("Enter your full name.")
      elif len(signup_name.strip()) > 100:
        st.error("Name must not exceed 100 characters.")
      elif not validate_ethiopian_phone(signup_phone):
        st.error("Enter a valid Ethiopian mobile number: exactly 10 digits starting with 09 or 07.")
      elif len(signup_email.strip()) > 254:
        st.error("Email address must not exceed 254 characters.")
      elif not validate_email(signup_email):
        st.error("Enter a valid email address or leave the field blank.")
      elif len(signup_password) < 8:
        st.error("Password must contain at least 8 characters.")
      elif len(signup_password) > 128:
        st.error("Password must not exceed 128 characters.")
      elif signup_password != signup_password_confirm:
        st.error("The passwords do not match.")
      else:
        account, registration_error = create_user(
            signup_name,
            signup_phone.strip(),
            signup_email,
            signup_password,
        )
        if account:
          st.session_state["auth_user"] = account
          st.session_state["auth_session_id"] = secrets.token_hex(8)
          st.success("Account created. Welcome to Agre AI.")
          st.rerun()
        st.error(registration_error)
  st.stop()

current_user = st.session_state["auth_user"]
user_id = current_user["user_id"]
phone_number = current_user["phone_number"]
email_address = current_user["email"]

st.sidebar.title("Agre AI")
st.sidebar.caption(f"Signed in as {current_user['full_name']}")
st.sidebar.caption(user_id)

diagnosis_tab, history_tab, profile_tab = st.tabs([
    "🌱 Crop Diagnosis & Weather",
    "📊 My History & Prescriptions",
    "👤 Profile / Logout",
])

# --------------------------------------------------
with diagnosis_tab:
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
          "የቅጠል ፎቶ ይጫኑ",
          type=["jpg", "jpeg", "png"],
          key=f"crop_upload_{st.session_state['auth_session_id']}",
      )
    else:
      uploaded_file = st.camera_input(
          "ካሜራ በመጠቀም ፎቶ ያንሱ",
          key=f"crop_camera_{st.session_state['auth_session_id']}",
      )

  with col_in2:
    st.subheader("🎤 የድምፅ ጥያቄ እና ግልባጭ")
    st.write("ማይክሮፎኑን በመጫን ጥያቄዎን በአማርኛ በግልጽ ይናገሩ፦")

    if "reset_audio" not in st.session_state:
      st.session_state["reset_audio"] = False

    audio_key = (
        f"audio_input_{st.session_state['auth_session_id']}_reset"
        if st.session_state["reset_audio"]
        else f"audio_input_{st.session_state['auth_session_id']}_normal"
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
          contact_method_available = bool(normalize_phone_number(phone_number))

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
  Farmer follow-up contact method available: {"Yes" if contact_method_available else "No"}.
  Do not repeat or infer any phone number or email address in your generated text.

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

  At the very end, append this machine-readable block exactly once, on separate lines,
  with no Markdown code fence around it. Use the exact field names shown below:
  <ALERT_METADATA>
  STATUS:
  CROP:
  PATHOLOGY_AM:
  PATHOLOGY_EN:
  SEVERITY:
  RISK_AM:
  RISK_EN:
  INSPECTION_AM:
  INSPECTION_EN:
  TREATMENT_AM:
  TREATMENT_EN:
  MITIGATION_AM:
  MITIGATION_EN:
  </ALERT_METADATA>

  Fill STATUS with exactly one of DISEASE, HEALTHY, or UNCERTAIN.
  Fill CROP with the crop or plant name, or Unknown if it cannot be identified.
  Fill PATHOLOGY_AM with the Amharic disease description/name. Fill PATHOLOGY_EN
  with the scientific name and English common name, for example "Cladosporium
  fulvum (Tomato leaf mold)". Use None in both pathology fields when absent.
  Fill SEVERITY with HIGH or CRITICAL based on visible disease severity and the
  weather context. This metadata and every action in it are written by this system
  to the agricultural extension expert; do not address the farmer or phrase any
  action as an instruction to the farmer. Be specific to the identified crop,
  pathology, visible symptoms, and supplied weather. Fill each *_AM field with
  concise, natural Amharic and the corresponding *_EN field with concise
  professional English. RISK_AM/EN should describe the case-specific disease risk
  and weather context without inventing a weather value. INSPECTION_AM/EN should
  direct the expert to contact the registered farmer, inspect the field and assess
  the affected area; do not invent contact details. TREATMENT_AM/EN should direct
  the expert to verify the diagnosis and recommend/authorize only crop-appropriate,
  locally registered treatment. Name an active ingredient only when appropriate,
  and require the expert to verify registration, label directions, PPE and
  pre-harvest interval. MITIGATION_AM/EN should direct the expert to give the
  farmer a case-specific sanitation, irrigation or other prevention plan. Do not
  invent symptoms, weather values, diagnoses, or contact details. When uncertain,
  recommend verification before treatment rather than unsupported chemical use.
  Set STATUS to DISEASE only when the image clearly shows a crop disease, pest,
  fungal infection, or bacterial infection. Use HEALTHY when a crop is visible and
  no disease is evident. Use UNCERTAIN for non-crop images or inconclusive evidence.
  Never classify a healthy crop as diseased. Set CRITICAL only for severe or rapidly
  spreading symptoms or a clearly high-risk weather context; otherwise use HIGH.
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
              bot_response_text, alert_metadata = extract_alert_metadata(response.text)
              st.session_state["chat_history"] = [{
                  "role": "assistant",
                  "content": bot_response_text,
              }]
              st.session_state["initial_analyzed"] = True

              # Persist the report before triggering the external notification.
              current_time_str = datetime.now(
                  ZoneInfo("Africa/Addis_Ababa")
              ).strftime("%Y-%m-%d %H:%M:%S EAT")
              pathology_details = (
                  f"Crop: {alert_metadata['crop']}; "
                  f"Status: {alert_metadata['status']}; "
                  f"Pathology (Amharic): {alert_metadata['pathology_am']}; "
                  f"Pathology (English): {alert_metadata['pathology']}; "
                  f"Severity: {alert_metadata['severity']}; "
                  f"Risk context (Amharic): {alert_metadata['risk_context_am']}; "
                  f"Risk context (English): {alert_metadata['risk_context']}; "
                  f"Expert inspection directive (Amharic): {alert_metadata['inspection_am']}; "
                  f"Expert inspection directive (English): {alert_metadata['inspection']}; "
                  f"Treatment directive (Amharic): {alert_metadata['treatment_am']}; "
                  f"Treatment directive (English): {alert_metadata['treatment']}; "
                  f"Mitigation directive (Amharic): {alert_metadata['mitigation_am']}; "
                  f"Mitigation directive (English): {alert_metadata['mitigation']}"
              )
              saved_to_db = save_to_db(
                  timestamp=current_time_str,
                  location_name=current_location_name,
                  crop_pathology_details=pathology_details,
                  ai_summary=bot_response_text,
                  user_id=user_id,
                  phone_number=phone_number,
                  email=email_address,
              )
              disease_detected = (
                  alert_metadata["status"] == "DISEASE"
                  and not re.search(
                      r"\b(none|healthy|no disease|not detected|unknown|not specified|not classified)\b",
                      alert_metadata["pathology"].strip().lower(),
                  )
                  and bool(alert_metadata["pathology"].strip())
              )
              if saved_to_db and disease_detected:
                send_alert_to_extension_worker(
                    current_location_name,
                    farmer_name=current_user["full_name"],
                    user_id=user_id,
                    phone_number=phone_number,
                    email=email_address,
                    disease_status=alert_metadata["status"],
                    case_metadata=alert_metadata,
                    timestamp=current_time_str,
                )
              elif saved_to_db:
                st.info("No confirmed crop disease was detected; no Telegram alert was sent.")

              st.success(
                  "✅ አጠቃላይ ትንተናው እና የመስኖ ምክሩ ተጠናቆ ወደ ታሪክ ማህደር ተቀምጧል!"
              )
              if not saved_to_db:
                st.warning("ሪፖርቱ በአሁኑ ጊዜ ወደ SQLite ታሪክ ማስቀመጥ አልተቻለም።")
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


with history_tab:
  st.subheader("My history and prescriptions")
  user_history = load_diagnoses_from_db(user_id)
  if st.button("Clear my history", key="clear_my_history"):
    clear_db_history(user_id)
    st.rerun()
  if not user_history:
    st.info("No crop analyses have been saved to this account yet.")
  else:
    for history_item in user_history:
      title = f"{history_item['time']} · {history_item['city']}"
      with st.expander(title):
        st.caption(history_item.get("details") or "Crop diagnosis")
        st.markdown(history_item["summary"] or "No report text was saved.")

with profile_tab:
  st.subheader("Profile")
  with st.container(border=True):
    st.write(f"**Name:** {current_user['full_name']}")
    st.write(f"**User ID:** {user_id}")
    st.write(f"**Phone:** {phone_number}")
    st.write(f"**Email:** {email_address or 'Not provided'}")
  if st.button("Log out", type="primary", key="profile_logout"):
    for state_key in (
        "chat_history", "initial_analyzed", "transcription",
        "transcription_error", "last_audio_size", "reset_audio",
    ):
      st.session_state.pop(state_key, None)
    st.session_state["auth_user"] = None
    st.rerun()
