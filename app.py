import io
import re
import os
import json
import time
from datetime import datetime

import streamlit as st
import speech_recognition as sr
from gtts import gTTS
from fpdf import FPDF
import research as R
from research import research

st.set_page_config(page_title="Deep Research", page_icon="🔎", layout="centered")
def check_password():
    pwd = st.secrets.get("APP_PASSWORD", "")
    if not pwd:
        return
    if st.session_state.get("authed"):
        return
    p = st.text_input("Password daalo", type="password")
    if p and p == pwd:
        st.session_state.authed = True
        st.rerun()
    if p:
        st.error("Galat password")
    st.stop()

check_password()
REPORT_DIR = "reports"
HISTORY_FILE = os.path.join(REPORT_DIR, "history.json")
os.makedirs(REPORT_DIR, exist_ok=True)

st.markdown(
    """
    <style>
    .block-container {max-width: 820px; padding-top: 2rem;}
    .src-line {font-size: 0.92rem; margin-bottom: 0.35rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔎 Deep Research")
st.caption("Web se jaankari dhoondh kar ek saaf report banata hai.")

SAMPLES = [
    "India mein fintech ka growth",
    "Indian history mein important decisions",
    "Stock market volatility ke karan",
]

for key, default in [("question", ""), ("result", None), ("last_q", ""), ("status_msg", "")]:
    if key not in st.session_state:
        st.session_state[key] = default


# ---------- HISTORY ----------
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(item):
    hist = load_history()
    hist.insert(0, item)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)


# ---------- PDF ----------
def make_pdf(question, text):
    font_path = "C:/Windows/Fonts/arial.ttf"
    bold_path = "C:/Windows/Fonts/arialbd.ttf"
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    if os.path.exists(font_path):
        pdf.add_font("Arial", "", font_path)
        pdf.add_font("Arial", "B", bold_path if os.path.exists(bold_path) else font_path)
        fam = "Arial"

        def clean(s):
            return s.replace("\u2013", "-").replace("\u2014", "-")
    else:
        fam = "Helvetica"

        def clean(s):
            return s.encode("latin-1", "replace").decode("latin-1")

    def write(h, txt, style="", size=10):
        pdf.set_font(fam, style, size)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, h, clean(txt), new_x="LMARGIN", new_y="NEXT")

    write(9, f"Research: {question}", "B", 16)
    write(6, datetime.now().strftime("%d %B %Y, %H:%M"), "", 9)
    pdf.ln(3)

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            pdf.ln(3)
            continue
        if line.startswith("**") and line.endswith("**"):
            write(7, line.strip("*"), "B", 12)
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        if line.startswith(("* ", "- ")):
            line = "- " + line[2:]
        write(6, line, "", 10)

    return bytes(pdf.output())

def save_pdf(fname, data):
    with open(os.path.join(REPORT_DIR, fname), "wb") as f:
        f.write(data)
    st.toast("PDF 'My PDFs' mein save ho gaya")


# ---------- RESEARCH ----------
def pick_sample(text):
    st.session_state.question = text


def run(q):
    start = time.time()
    report = None
    with st.status("Research chal rahi hai... 1-3 minute lag sakte hain", expanded=True) as status:
        try:
            report = research(q)
            if report:
                status.update(label=f"Ho gaya ({int(time.time() - start)} second)",
                              state="complete", expanded=False)
            else:
                status.update(label="Is sawaal par koi useful jaankari nahi mili",
                              state="error", expanded=False)
        except Exception as e:
            status.update(label="Kuch error aaya", state="error")
            st.session_state.status_msg = f"Error: {e}"
            report = None

    st.session_state.result = report
    st.session_state.last_q = q
    if report:
        st.session_state.status_msg = ""
        save_history({
            "q": q,
            "time": datetime.now().strftime("%d %b %Y, %H:%M"),
            "result": report,
        })
    else:
        st.session_state.status_msg = st.session_state.status_msg or (
            "Is sawaal par web pages se kaafi jaankari nahi mili. "
            "Sawaal ko thoda badal kar dobara try karo, jaise ek saaf English keyword."
        )


def compact_sources(body):
    urls = []

    def repl(m):
        nums = []
        for u in re.findall(r"https?://[^\s,)\]]+", m.group(1)):
            if u not in urls:
                urls.append(u)
            nums.append(f"[{urls.index(u) + 1}]")
        return " " + " ".join(nums) if nums else ""

    new_body = re.sub(r"\(\s*Source:?\s*([^)]*)\)", repl, body, flags=re.I)
    return new_body, urls


def get_summary(body):
    bullets, in_section = [], False
    for line in body.splitlines():
        s = line.strip()
        if "mukhya" in s.lower():
            in_section = True
            continue
        if in_section and s.startswith("**") and not s.lower().startswith("**mukhya"):
            break
        if in_section and s.startswith(("*", "-")):
            bullets.append(s.lstrip("*-• ").strip())
        if len(bullets) == 3:
            break
    return bullets


def speech_to_text(audio_bytes):
    rec = sr.Recognizer()
    with sr.AudioFile(io.BytesIO(audio_bytes)) as src:
        audio = rec.record(src)
    return rec.recognize_google(audio, language="hi-IN")


def text_to_speech(text, lang="hi"):
    clean = re.sub(r"https?://\S+", "", text)
    clean = re.sub(r"[*#\[\]()]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()[:3000]
    buf = io.BytesIO()
    gTTS(text=clean, lang=lang).write_to_fp(buf)
    return buf.getvalue()


# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("⚙️ Settings")
    R.PAGES_PER_QUESTION = st.slider(
        "Har sub-question ke liye pages", 1, 4, R.PAGES_PER_QUESTION
    )
    speech_lang = st.selectbox("Awaaz ki bhasha", ["hi", "en"], index=0)

    st.divider()
    st.header("🕘 History")
    hist = load_history()
    if not hist:
        st.caption("Abhi koi history nahi hai.")
    for i, h in enumerate(hist[:20]):
        label = f"{h['time']} · {h['q'][:30]}"
        if st.button(label, key=f"hist_{i}", use_container_width=True):
            st.session_state.result = h["result"]
            st.session_state.last_q = h["q"]
            st.session_state.status_msg = ""

    st.divider()
    st.header("📄 My PDFs")
    pdfs = sorted([f for f in os.listdir(REPORT_DIR) if f.endswith(".pdf")], reverse=True)
    if not pdfs:
        st.caption("Abhi koi PDF nahi hai. Report ke neeche PDF download karo.")
    for f in pdfs[:30]:
        with open(os.path.join(REPORT_DIR, f), "rb") as fh:
            st.download_button(f, data=fh.read(), file_name=f,
                               mime="application/pdf", key=f"pdf_{f}")

# ---------- SAMPLES ----------
st.write("**Sample sawaal:**")
cols = st.columns(len(SAMPLES))
for col, sample in zip(cols, SAMPLES):
    col.button(sample, on_click=pick_sample, args=(sample,))

# ---------- TEXT INPUT ----------
with st.form("search_form"):
    question = st.text_input(
        "Apna sawaal likho",
        key="question",
        placeholder="jaise: India mein fintech ka growth",
    )
    submitted = st.form_submit_button("Research shuru karo", type="primary")

if submitted:
    if not question.strip():
        st.warning("Pehle sawaal likho.")
    else:
        run(question.strip())

# ---------- VOICE INPUT ----------
st.write("**🎤 Bolkar poochho:**")
audio = st.audio_input("Record karke sawaal bolo")
if audio is not None and st.button("Bolne wale sawaal par research karo"):
    try:
        spoken = speech_to_text(audio.getvalue())
        st.info(f"Maine suna: {spoken}")
        run(spoken)
    except sr.UnknownValueError:
        st.warning("Awaaz samajh nahi aayi. Dobara saaf bolo.")
    except sr.RequestError:
        st.error("Speech service se connect nahi ho paya. Internet check karo.")

# ---------- RETRY ----------
if st.session_state.last_q:
    if st.button(f"🔁 Dobara try karo: {st.session_state.last_q}"):
        run(st.session_state.last_q)

# ---------- RESULT ----------
result = st.session_state.result

if result:
    body, _, sources_block = result.partition("**Sources:**")
    body = body.strip()

    compact_body, urls = compact_sources(body)
    for line in sources_block.splitlines():
        for u in re.findall(r"https?://\S+", line):
            if u not in urls:
                urls.append(u)

    summary = get_summary(body)
    if summary:
        with st.container(border=True):
            st.markdown("**⚡ Short summary**")
            for point in summary:
                st.markdown(f"- {point}")
            if st.button("🔊 Summary sunao"):
                st.audio(text_to_speech("\n".join(summary), lang=speech_lang), format="audio/mp3")

    st.divider()
    st.subheader("📝 Report")
    with st.container(border=True):
        st.markdown(compact_body)
        if st.button("🔊 Poori report sunao"):
            st.audio(text_to_speech(body, lang=speech_lang), format="audio/mp3")

    st.subheader("📚 Sources")
    if urls:
        for i, url in enumerate(urls, start=1):
            st.markdown(
                f"<div class='src-line'>[{i}] <a href='{url}' target='_blank'>{url}</a></div>",
                unsafe_allow_html=True,
            )
    else:
        st.write("Is report ke liye sources nahi mile.")

    plain_text = compact_body + "\n\nSources:\n" + "\n".join(f"[{i}] {u}" for i, u in enumerate(urls, start=1))
    with st.expander("📋 Text copy karne ke liye (copy icon par click karo)"):
        st.code(plain_text, language="markdown")

    slug = re.sub(r"[^A-Za-z0-9]+", "_", st.session_state.last_q)[:40].strip("_") or "report"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_name = f"{slug}_{stamp}.pdf"
    pdf_bytes = make_pdf(st.session_state.last_q, result)

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Report (.md) download",
            data=result,
            file_name="report.md",
            mime="text/markdown",
        )
    with c2:
        st.download_button(
            "📄 PDF download (My PDFs mein save hoga)",
            data=pdf_bytes,
            file_name=pdf_name,
            mime="application/pdf",
            on_click=save_pdf,
            args=(pdf_name, pdf_bytes),
        )
elif st.session_state.status_msg:
    st.warning(st.session_state.status_msg)