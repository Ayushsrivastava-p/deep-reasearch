import io
import re
import time
import contextlib
import requests
from bs4 import BeautifulSoup
from groq import Groq

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# ---------- SETTINGS ----------
import os
try:
    import streamlit as st
    GROQ_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
PAGES_PER_QUESTION = 2
PAGE_CHARS = 2500
SKIP_SITES = ["youtube.com", "youtu.be", "facebook.com", "instagram.com",
              "twitter.com", "x.com", "linkedin.com", "pinterest.com",
              "jiosaavn.com", "gaana.com", "dailymotion.com", "translate.google"]

SYSTEM_PROMPT = """Tum ek strict research assistant ho.
Niyam:
1. Sirf wahi likho jo diye gaye text mein clearly likha ho. Apni taraf se kuch mat jodo.
2. Andaza mat lagao. Naam, tareekh, aankde jaise hain waise hi likho.
3. Agar text mein jaankari nahi hai, to sirf likho: NO_INFO
4. Jawab chhota aur seedha ho. Bhasha wahi rakho jo sawaal ki bhasha ho.
"""

client = Groq(api_key=GROQ_KEY)


def pick_model():
    # Reasoning models ko skip karta hai, kyunki wo khali jawab de sakte hain
    try:
        ids = [m.id for m in client.models.list().data]
    except Exception:
        return "llama-3.3-70b-versatile"

    skip_words = ["guard", "whisper", "tts", "embed", "prompt", "gpt-oss", "reason", "distil"]
    candidates = [i for i in ids if not any(w in i.lower() for w in skip_words)]

    preferred = ["llama-3.3-70b", "llama-3.1-70b", "70b", "qwen", "versatile", "instant", "llama"]
    for word in preferred:
        for c in candidates:
            if word in c.lower():
                return c
    return candidates[0] if candidates else "llama-3.1-8b-instant"


MODEL = pick_model()


def ask_ai(prompt, max_tokens=800):
    global MODEL
    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            msg = str(e)
            print(f"   (AI error, retry {attempt + 1}: {msg[:120]})")
            if "404" in msg or "does not exist" in msg or "decommissioned" in msg:
                MODEL = pick_model()
                print("   Model badla gaya:", MODEL)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("AI abhi available nahi hai. Kuch minute baad dobara chalao.")


def to_english_keywords(question):
    prompt = f"""Is sawaal ka English mein 3-5 shabdon ka search query banao.
Sirf query likho, koi extra text nahi.

Sawaal: {question}"""
    result = ask_ai(prompt, max_tokens=200).strip().strip('"')
    return result if result else question


def make_sub_questions(question):
    prompt = f"""Is sawaal ko 3 chhote research sawaalon mein todo.
Har sawaal ek alag line mein ho, English mein. Koi number ya URL mat likho.

Sawaal: {question}"""
    text = ask_ai(prompt, max_tokens=300)
    lines = [l.strip().lstrip("-*0123456789.) ").strip() for l in text.split("\n")]
    lines = [l for l in lines if len(l) > 10 and "http" not in l.lower()]
    return lines[:3] if lines else [question]


def search_web(query, seen_urls):
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=8):
            url = r.get("href", "")
            if not url or url in seen_urls:
                continue
            if any(site in url for site in SKIP_SITES):
                continue
            results.append({"title": r.get("title", ""), "url": url})
            if len(results) == PAGES_PER_QUESTION:
                break
    return results

def read_page(url):
    try:
        page = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if "text/html" not in page.headers.get("Content-Type", ""):
            return ""
        soup = BeautifulSoup(page.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(p for p in paragraphs if len(p) > 40)
        if len(text) < 200:
            text = " ".join(soup.get_text(" ", strip=True).split())
        return text[:PAGE_CHARS]
    except Exception:
        return ""


def make_notes(sub_question, page_text, url):
    if len(page_text) < 100:
        return ""
    prompt = f"""Sawaal: "{sub_question}"
Neeche diye text se is sawaal ke 2-3 points likho.
Har point ke end mein likho: (Source: {url})
Agar text mein is sawaal se related jaankari nahi hai to sirf likho: NO_INFO

Text:
{page_text}"""
    answer = ask_ai(prompt, max_tokens=400)
    if not answer or "NO_INFO" in answer:
        return ""
    return answer


def write_report(question, all_notes):
    prompt = f"""Neeche diye notes se ek chhoti report likho.
Sirf notes ki baatein likho. Har point ke saath Source URL rakho.
Format:
**Mukhya Baatein**
**Karan aur Vajah**
**Nishkarsh**

Main sawaal: {question}

Notes:
{all_notes[:8000]}"""
    return ask_ai(prompt, max_tokens=1000)


def research(question):
    start = time.time()
    seen_urls = set()

    print("\n0. Search keywords bana raha hoon...")
    search_query = to_english_keywords(question)
    print(f"   Keywords: {search_query}")

    print("\n1. Sub-questions bana raha hoon...")
    sub_questions = make_sub_questions(search_query)
    print(sub_questions)

    all_notes = ""
    all_sources = []

    for sq in sub_questions:
        print(f"\n2. Search kar raha hoon: {sq}")
        try:
            results = search_web(sq, seen_urls)
        except Exception as e:
            print(f"   Search error: {e}")
            continue

        for r in results:
            seen_urls.add(r["url"])
            print(f"   3. Padh raha hoon: {r['url']}")
            text = read_page(r["url"])
            notes = make_notes(sq, text, r["url"])
            if notes:
                all_notes += f"\n\n[{sq}]\n{notes}"
                if r["url"] not in all_sources:
                    all_sources.append(r["url"])

    if not all_notes.strip():
        print("\nKoi useful jaankari nahi mili. Sawaal badal kar dobara try karo.")
        return None

    print("\n4. Final report likh raha hoon...\n")
    report = write_report(question, all_notes)
    final = report + "\n\n**Sources:**\n" + "\n".join(f"- {u}" for u in all_sources)

    with open("report.txt", "w", encoding="utf-8") as f:
        f.write(final)

    print(final)
    print(f"\nKul time: {int(time.time() - start)} seconds")
    print("(Report 'report.txt' file mein bhi save ho gaya hai)")
    return final 

def run_research(question):
    # Streamlit ke liye: saara print output ek string mein wapas deta hai
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        research(question)
    return buf.getvalue()