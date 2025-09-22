# web.py - Kraig (Minimal Frontend, Flask) orchestrating the Agent backend (ENV-separated)
# ---------------------------------------------------------------------------------
# Goals:
# - Only ask the user for: email, full address, exactly 4 photos, and (later) the login link if needed
# - Keep web env fully separate from the Agent env
# - Launch the existing Agent (script.py) as a subprocess and stream logs to the browser (SSE)
# - Provide a page to paste the email magic link when the Agent asks for it
# - Show a full "Posting Preview" (all fields that will be sent to the backend) before posting
# - Dark mode, improved UI, and branding as "Kraig"
#
# Web app env (separate):
#   - Put web-only settings in .env.web (sibling file)
#     OPENAI_API_KEY (optional; only needed if you want the web to call OpenAI)
#     AGENT_ENV_FILE=./Craigslist/.env   (which Agent .env to use)
#
# Agent env (existing, separate):
#   - AGENT_ENV_FILE points to the .env the Agent uses (ENV-only config)
#   - We will provide required variables to the Agent through the subprocess environment
#     deriving city and postal from the full address.
#
# Run:
#   pip install -r requirements.txt
#   python web.py
#   Visit http://127.0.0.1:5000/
# ---------------------------------------------------------------------------------

import os
import re
import json
import base64
import uuid
import queue
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import time

from flask import Flask, request, render_template_string, Response, redirect, url_for
from dotenv import load_dotenv, dotenv_values
from openai import OpenAI

# Load ONLY the web app env (kept separate from Agent env)
WEB_ENV_PATH = Path(__file__).with_name(".env.web")
load_dotenv(dotenv_path=str(WEB_ENV_PATH), override=False)

app = Flask(__name__)

ROOT_DIR = Path(__file__).resolve().parent
LISTINGS_DIR = ROOT_DIR / "listings"
JOBS_DIR = ROOT_DIR / "jobs"
LISTINGS_DIR.mkdir(exist_ok=True)
JOBS_DIR.mkdir(exist_ok=True)

# Live job registry (job_id -> {queue, proc, magic_link_file})
_job_registry: Dict[str, Dict[str, Any]] = {}

# Path to Agent .env for subprocesses (Agent backend still uses its own .env)
AGENT_ENV_FILE = os.environ.get("AGENT_ENV_FILE", str(ROOT_DIR / ".env"))

# Optional OpenAI client for vision/pricing/categorization in the web app
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Craigslist category list (single source of truth)
CATEGORIES = [
    "antiques",
    "appliances",
    "arts & crafts",
    "atvs, utvs, snowmobiles",
    "auto parts",
    "auto wheels & tires",
    "aviation",
    "baby & kid stuff",
    "barter",
    "bicycle parts",
    "bicycles",
    "boat parts",
    "boats",
    "books & magazines",
    "business/commercial",
    "cars & trucks ($5)",
    "cds / dvds / vhs",
    "cell phones",
    "clothing & accessories",
    "collectibles",
    "computer parts",
    "computers",
    "electronics",
    "farm & garden",
    "free stuff",
    "furniture",
    "garage & moving sales",
    "general for sale",
    "health and beauty",
    "heavy equipment",
    "household items",
    "jewelry",
    "materials",
    "motorcycle parts",
    "motorcycles/scooters ($5)",
    "musical instruments",
    "photo/video",
    "rvs ($5)",
    "sporting goods",
    "tickets",
    "tools",
    "toys & games",
    "trailers",
    "video gaming",
    "wanted"
]

# ---------------------------------------------------------------------------------
# HTML (Dark mode + improved UI/branding as Kraig)
# ---------------------------------------------------------------------------------

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Kraig</title>
  <style>
    :root{
      --bg:#0b1021;
      --bg-2:#0d1330;
      --card:#121831;
      --card-2:#0f162d;
      --text:#e5e7eb;
      --muted:#93a4bf;
      --accent:#00e5ff;
      --accent-2:#60a5fa;
      --border:#1f2a44;
      --ok:#22c55e;
      --warn:#f59e0b;
      --err:#ef4444;
    }
    *{box-sizing:border-box}
    body{
      font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
      background:linear-gradient(180deg,var(--bg) 0%,var(--bg) 35%,var(--bg-2) 100%);
      color:var(--text);
      max-width:980px;margin:32px auto;padding:0 16px;
    }
    .brand{display:flex;align-items:center;gap:12px;margin-bottom:8px}
    .logo{
      width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,var(--accent),var(--accent-2));
      display:inline-block;box-shadow:0 6px 24px rgba(0,229,255,.25)
    }
    h1{margin:0}
    .subtitle{color:var(--muted);margin:0 0 16px}
    .card{
      border:1px solid var(--border);border-radius:14px;padding:16px;margin:12px 0;
      background:radial-gradient(1200px 500px at 100% -20%,rgba(0,229,255,0.06),transparent 60%),var(--card);
      box-shadow:0 1px 3px rgba(0,0,0,.25)
    }
    .card.soft{background:var(--card-2)}
    .grid{display:grid;gap:12px}
    .grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}
    .muted{color:var(--muted)}
    .warn{color:var(--warn)}
    input, textarea{
      background:#0b1120;color:var(--text);
      border:1px solid var(--border);border-radius:10px;padding:10px;width:100%
    }
    input[type=file]{padding:8px;background:#0b1120;border:1px dashed var(--border)}
    button{
      padding:10px 16px;border-radius:10px;border:1px solid #0ea5b7;background:linear-gradient(135deg,#0ea5b7,#0369a1);color:#fff;cursor:pointer
    }
    button.secondary{
      border-color:#334155;background:#0b1120;color:var(--text)
    }
    .hint{font-size:12px;color:var(--muted)}
    pre{background:#0b1120;color:var(--text);padding:12px;border-radius:12px;overflow:auto}
    .krow{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
    .pill{font-size:12px;border:1px solid var(--border);border-radius:999px;padding:4px 10px;background:#0b1120;color:var(--muted)}
    .kv{display:grid;grid-template-columns:160px 1fr;gap:8px;align-items:center}
    .thumbs{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
    .thumb{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:10px;border:1px solid var(--border);background:#0b1120}
    details{border:1px solid var(--border);border-radius:12px;padding:10px;background:#0b1120}
    summary{cursor:pointer}
    a{color:var(--accent)}
  </style>
</head>
<body>
  <div class="brand">
    <span class="logo"></span>
    <div>
      <h1>Kraig</h1>
      <p class="subtitle">Post to Craigslist with just your email, address, and 4 photos. We infer the rest.</p>
    </div>
  </div>

  {% if error_msg %}
    <div class="card soft"><p class="warn"><b>Error:</b> {{ error_msg }}</p></div>
  {% endif %}

  <form class="card" method="POST" action="/analyze" enctype="multipart/form-data">
    <h2>Listing Details</h2>
    <div class="grid grid-2">
      <div>
        <label><b>Email (Craigslist account)</b></label>
        <input name="email" placeholder="you@example.com" required>
      </div>
      <div>
        <label><b>Full Address</b></label>
        <input name="address" placeholder="123 Main St, San Francisco, CA 94110" required>
      </div>
    </div>
    <div style="margin-top:12px">
      <label><b>Photos (choose exactly 4)</b></label>
      <input type="file" name="images" accept="image/*" multiple required>
      <p class="hint">Select exactly four images in a single selection.</p>
    </div>
    <div style="margin-top:16px" class="krow">
      <button type="submit">Analyze</button>
      <span class="pill">Vision + pricing inference happens locally in the browser app</span>
    </div>
  </form>

  {% if combined %}
    <div class="card">
      <h2>Combined Top 3 Guesses</h2>
      <form method="POST" action="/choose">
        {% for row in combined %}
          <div>
            <input type="radio" id="g{{ loop.index0 }}" name="choice" value="{{ row['label'] }}" {% if loop.first %}checked{% endif %}>
            <label for="g{{ loop.index0 }}"><b>{{ row['label'] }}</b> — weight {{ '%.3f' % row['weight'] }}</label>
          </div>
        {% endfor %}
        <div style="margin-top:10px" class="krow">
          <div style="flex:1">
            <input type="radio" id="other" name="choice" value="__other__">
            <label for="other">Other:</label>
            <input type="text" name="other_text" placeholder="Brand + model">
          </div>
          <button type="submit" class="secondary">Get Price & Description</button>
        </div>
        <input type="hidden" name="session_payload" value='{{ session_payload|tojson }}'>
      </form>
    </div>

    <div class="card soft">
      <details>
        <summary>Per-image top-3 (expand)</summary>
        {% for guesses in per_image %}
          <p><b>Image {{ loop.index }}</b></p>
          <ul>
          {% for g in guesses %}
            <li>{{ g['label'] }} — conf {{ '%.3f' % g['confidence'] }}</li>
          {% endfor %}
          </ul>
        {% endfor %}
      </details>
    </div>

    {% if debug_entries %}
      <div class="card soft">
        <details>
          <summary><b>Debug (expand)</b></summary>
          {% for d in debug_entries %}
            <p><b>{{ d.title }}</b></p>
            <pre><code>{{ d.payload | tojson(indent=2) }}</code></pre>
            {% if not loop.last %}<hr>{% endif %}
          {% endfor %}
        </details>
      </div>
    {% endif %}
  {% endif %}

  {% if result %}
    <div class="card">
      <h2>Proposed Listing</h2>
      <div class="krow">
        <span class="pill">Estimated Market: {{ result['market_price'] }}</span>
        <span class="pill">Suggested Price: {{ result['selling_price'] }}</span>
        <span class="pill">Category: {{ result['category'] }}</span>
      </div>
      <p class="muted" style="margin-top:8px">{{ result['description'] }}</p>

      {% if preview %}
      <div class="card soft" style="margin-top:12px">
        <h3>Posting Preview</h3>
        <div class="kv">
          <div>Email</div><div>{{ preview.email }}</div>
          <div>Address</div><div>{{ preview.address }}</div>
          <div>City</div><div>{{ preview.city or '(parsed from address)' }}</div>
          <div>Postal Code</div><div>{{ preview.postal_code or '(parsed from address)' }}</div>
          <div>Category</div><div>{{ preview.category }}</div>
          <div>Title</div><div>{{ preview.title }}</div>
          <div>Condition</div><div>{{ preview.condition }}</div>
          <div>Price</div><div>${{ preview.price }}</div>
          <div>Description</div><div>{{ preview.description }}</div>
          <div>Images</div>
          <div>
            <div class="thumbs">
              {% for img in preview.images %}
                <img class="thumb" src="data:{{ img.mimetype }};base64,{{ img.bytes }}" alt="{{ img.filename }}">
              {% endfor %}
            </div>
            <p class="hint" style="margin-top:6px">{{ preview.images|length }} images selected.</p>
          </div>
        </div>
      </div>
      {% endif %}

      <div class="card soft" style="margin-top:12px">
        <h3>Post to Craigslist</h3>
        <form method="POST" action="/post_listing">
          <input type="hidden" name="session_payload" value='{{ session_payload|tojson }}'>
          <button type="submit">Post Now</button>
        </form>
        <p class="hint">If the backend needs an email login link, you'll be prompted on the next page.</p>
      </div>

      {% if result['sources'] %}
        <details style="margin-top:16px">
          <summary class="muted">Sources</summary>
          <ul>
            {% for s in result['sources'] %}
              <li><a href="{{ s['url'] }}" target="_blank" rel="noopener">{{ s['title'] }}</a></li>
            {% endfor %}
          </ul>
        </details>
      {% endif %}
    </div>
  {% endif %}

  {% if saved_listing %}
    <div class="card" style="background:#022c22;border-color:#065f46">
      <h2>✅ Listing Saved!</h2>
      <p><b>Listing ID:</b> {{ saved_listing['id'] }}</p>
      <p><b>Files saved:</b> {{ saved_listing['files']|join(', ') }}</p>
      <p><b>Location:</b> {{ saved_listing['path'] }}</p>
      <a href="/">Create another listing</a>
    </div>
  {% endif %}
</body>
</html>
"""

JOB_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Kraig — Job {{ job_id }}</title>
  <style>
    :root{
      --bg:#0b1021;--bg-2:#0d1330;--card:#121831;--text:#e5e7eb;--muted:#93a4bf;--border:#1f2a44;--accent:#00e5ff;
    }
    *{box-sizing:border-box}
    body{
      font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
      background:linear-gradient(180deg,var(--bg) 0%,var(--bg) 35%,var(--bg-2) 100%);
      color:var(--text);max-width:980px;margin:32px auto;padding:0 16px
    }
    .brand{display:flex;align-items:center;gap:12px;margin-bottom:8px}
    .logo{width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,#00e5ff,#60a5fa);display:inline-block;box-shadow:0 6px 24px rgba(0,229,255,.25)}
    .card{border:1px solid var(--border);border-radius:14px;padding:16px;margin:12px 0;background:var(--card);box-shadow:0 1px 3px rgba(0,0,0,.25)}
    .muted{color:var(--muted)}
    pre{background:#0b1120;color:var(--text);padding:12px;border-radius:12px;max-height:420px;overflow:auto}
    input, textarea{border:1px solid var(--border);border-radius:8px;padding:10px;width:100%;background:#0b1120;color:var(--text)}
    button{padding:10px 16px;border-radius:10px;border:1px solid #0ea5b7;background:linear-gradient(135deg,#0ea5b7,#0369a1);color:#fff;cursor:pointer}
  </style>
</head>
<body>
  <div class="brand">
    <span class="logo"></span>
    <div>
      <h1>Kraig — Posting Job {{ job_id }}</h1>
      <p class="muted">Live logs and magic link submission</p>
    </div>
  </div>

  <div class="card">
    <h3>Backend Progress</h3>
    <pre id="log"></pre>
    <p class="muted">This updates live while the backend runs.</p>
  </div>

  <div class="card">
    <h3>Paste Magic Link (if prompted)</h3>
    <form method="POST" action="/submit_magic_link/{{ job_id }}">
      <textarea name="magic_link" placeholder="https://accounts.craigslist.org/login/..." rows="3"></textarea>
      <button type="submit" style="margin-top:8px">Submit Magic Link</button>
    </form>
    <p class="muted">If the agent asks for a login link, paste it here. The backend will detect it automatically.</p>
  </div>

  <script>
    const logEl = document.getElementById('log');
    const es = new EventSource('/events/{{ job_id }}');
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'line') {
          logEl.textContent += data.value + "\\n";
          logEl.scrollTop = logEl.scrollHeight;
        } else if (data.type === 'done') {
          logEl.textContent += "\\n[done]\\n";
          es.close();
        }
      } catch (e) {
        logEl.textContent += ev.data + "\\n";
      }
    };
  </script>
</body>
</html>
"""

# ---------------------------------------------------------------------------------
# Helpers: vision + JSON utils (from original scaffold)
# ---------------------------------------------------------------------------------

def canonicalize(label: str) -> str:
    """Basic canonical label for dedupe (lowercase, strip, squash spaces)."""
    return " ".join((label or "").lower().strip().split())

class DebugEntry:
    def __init__(self, title: str, payload):
        self.title = title
        self.payload = payload

def try_parse_json(raw_text: str):
    """Best-effort to pretty capture JSON text."""
    try:
        return json.loads(raw_text)
    except Exception:
        return {"non_json_text": raw_text}

def extract_json_fallback(text: str):
    """
    Robustly extract the first JSON object from an arbitrary string.
    - Tries fenced ```json blocks first.
    - Then scans for the first balanced {...} and parses it.
    Returns dict or {}.
    """
    if not text:
        return {}
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            text = candidate
    starts = [m.start() for m in re.finditer(r"\{", text)]
    for si in starts:
        depth = 0
        for ei in range(si, len(text)):
            ch = text[ei]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[si:ei+1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
    return {}

# ---------------------------------------------------------------------------------
# Vision: identify product (kept from original)
# ---------------------------------------------------------------------------------

def ask_o3_for_top3(image_bytes: bytes, filename: str, mime: str, debug_list):
    """
    Send ONE image to vision model and ask for top-3 JSON.
    First tries gpt-4o (vision), then falls back to gpt-4o-mini.
    Append structured debug info to debug_list.
    """
    schema = {
        "type": "object",
        "properties": {
            "guesses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                    },
                    "required": ["label", "confidence"],
                    "additionalProperties": False
                },
                "minItems": 3,
                "maxItems": 3
            }
        },
        "required": ["guesses"],
        "additionalProperties": False
    }

    system = (
        "You identify retail products from a single image.\n"
        "Return EXACT JSON with keys: guesses: [{label, confidence} x3].\n"
        "Label must be 'Brand Model Variant' if possible (e.g., 'Meta Quest Pro').\n"
        "Confidence is 0..1. If unsure, include best-guess labels with lower confidence."
    )
    prompt = "Identify the item in this photo. Return your top 3 distinct guesses with confidences."

    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    image_url = f"data:{mime or 'image/jpeg'};base64,{image_base64}"

    debug_list.append(DebugEntry(
        "Vision request (gpt-4o)",
        {
            "model": "gpt-4o",
            "schema": schema,
            "system_prompt_excerpt": system[:240],
            "user_prompt": prompt,
            "image_meta": {"filename": filename or "upload", "mimetype": mime, "bytes": len(image_bytes)},
        }
    ))

    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",
                     "content": [
                         {"type": "text", "text": prompt},
                         {"type": "image_url", "image_url": {"url": image_url}}
                     ]}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            raw = resp.choices[0].message.content
            debug_list.append(DebugEntry("Vision raw JSON (gpt-4o)", {"attempt": attempt + 1, "raw": try_parse_json(raw)}))
            data = json.loads(raw)
            return data.get("guesses", [])
        except Exception as e:
            debug_list.append(DebugEntry("Vision error (gpt-4o)", {"attempt": attempt + 1, "error": repr(e)}))
            if attempt == 0:
                time.sleep(0.8)
                continue

    # Fallback: text-only guess
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Return JSON: {\"guesses\":[{\"label\":\"Generic\", \"confidence\":0.34},{\"label\":\"Product\", \"confidence\":0.33},{\"label\":\"Unknown\", \"confidence\":0.33}]}"}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        return data.get("guesses", [])
    except Exception:
        return []

def classify_category_with_llm(label: str, debug_entries):
    """
    Ask ChatGPT (Responses API) to choose ONE category from CATEGORIES for the given label.
    Returns a string category (always one of CATEGORIES), with a few keyword fallbacks.
    Ex. Oculus Quest = "Electronics"
    """
    system = (
        "You are a marketplace category classifier for Craigslist.\n"
        "Given only an item name, choose the SINGLE closest category from the provided list.\n"
        "Return JSON only: {\"category\":\"<one>\"}."
    )
    cat_list = "\n".join(f"- {c}" for c in CATEGORIES)
    user = f"Item name: {label}\n\nChoose a category from this list:\n{cat_list}\n\nReturn JSON only."

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0
        )
        raw_text = getattr(resp, "output_text", None)
        data = extract_json_fallback(raw_text or "")
        cat = (data.get("category") or "").strip().lower()
        for c in CATEGORIES:
            if c.lower() == cat:
                return c
    except Exception as e:
        debug_entries.append(DebugEntry("Category classification error", {"error": repr(e)}))

    # Simple heuristics
    l = (label or "").lower()
    def has(*words): return any(w in l for w in words)
    if has("chair","sofa","table","dresser","stool","couch","desk","bed","cabinet"): return "furniture"
    if has("iphone","samsung","pixel","android","smartphone","cell"): return "cell phones"
    if has("laptop","macbook","surface","notebook"): return "computers"
    if has("camera","lens","dslr","mirrorless","tripod"): return "photo/video"
    if has("guitar","piano","keyboard","drum","synth"): return "musical instruments"
    if has("ps5","xbox","nintendo","switch","gaming"): return "video gaming"
    if has("microwave","fridge","refrigerator","washer","dryer","oven","dishwasher"): return "appliances"
    if has("hammer","drill","saw","wrench","tool"): return "tools"
    if has("speaker","headphones","tv","monitor","tablet","smartwatch"): return "electronics"
    return "general for sale"

# ---------------------------------------------------------------------------------
# Web routes: analyze -> choose (pricing/description/category) -> post_listing
# ---------------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML, categories=CATEGORIES)

@app.route("/analyze", methods=["POST"])
def analyze():
    debug_entries: List[DebugEntry] = []
    email = (request.form.get("email") or "").strip()
    address = (request.form.get("address") or "").strip()
    if not email or not address:
        return render_template_string(
            INDEX_HTML,
            error_msg="Please provide email and full address.",
            combined=None, per_image=None, session_payload=None, debug_entries=[],
            categories=CATEGORIES
        )

    images = request.files.getlist("images")
    if not images or len(images) != 4:
        return render_template_string(
            INDEX_HTML,
            error_msg="Please select exactly 4 images in a single selection.",
            combined=None, per_image=None, session_payload=None, debug_entries=[],
            categories=CATEGORIES
        )

    # Store images for later saving
    session_images: List[Dict[str, Any]] = []
    per_image: List[List[Dict[str, Any]]] = []
    for f in images:
        img_bytes = f.read()  # in-memory only
        session_images.append({
            "filename": f.filename,
            "mimetype": f.mimetype,
            "bytes": base64.b64encode(img_bytes).decode("utf-8")
        })
        guesses = ask_o3_for_top3(img_bytes, f.filename, f.mimetype, debug_entries) or []
        clean: List[Dict[str, Any]] = []
        for g in guesses[:3]:
            try:
                label = str(g["label"])[:140]
                conf = float(g["confidence"])
                conf = max(0.0, min(conf, 1.0))
                clean.append({"label": label, "confidence": conf})
            except Exception as e:
                debug_entries.append(DebugEntry("Clean guess error", {"raw_guess": g, "error": repr(e)}))
                continue
        while len(clean) < 3:
            clean.append({"label": "Unknown", "confidence": 0.0})
        per_image.append(clean)

    # Combine: sum normalized weights across images per canonical label
    weights: Dict[str, float] = {}
    label_map: Dict[str, str] = {}
    for guesses in per_image:
        s = sum(g["confidence"] for g in guesses) or 1.0
        for g in guesses:
            w = g["confidence"] / s
            key = canonicalize(g["label"])
            weights[key] = weights.get(key, 0.0) + w
            label_map.setdefault(key, g["label"])

    combined = [{"label": label_map[k], "weight": v} for k, v in weights.items()]
    combined.sort(key=lambda x: x["weight"], reverse=True)
    combined = combined[:3]

    session_payload = {"per_image": per_image, "combined": combined, "images": session_images, "email": email, "address": address}

    return render_template_string(
        INDEX_HTML,
        combined=combined,
        per_image=per_image,
        session_payload=session_payload,
        debug_entries=debug_entries,
        categories=CATEGORIES
    )

@app.route("/choose", methods=["POST"])
def choose():
    # Determine selected product label
    debug_entries: List[DebugEntry] = []
    choice = request.form.get("choice")
    other = (request.form.get("other_text") or "").strip()
    label = other if (choice == "__other__" and other) else (choice or "Unknown")

    listing_id = str(uuid.uuid4())[:8]

    # Ask OpenAI for price + description + sources (web-side)
    price_system = (
        "You are a Craigslist listing generator.\n"
        "TASKS:\n"
        "1) Estimate a reasonable US market price for the given product name (used-good condition) and include a couple of sources.\n"
        "2) Write a short Craigslist-style description (2-4 sentences).\n"
        "Return JSON only with keys: {\"label\":string,\"market_price\":number,\"description\":string,\"sources\":[{\"title\":string,\"url\":string}]}.\n"
    )
    price_user = f"Product: {label}. Return strict JSON only."

    result: Dict[str, Any] = {}
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": price_system},
                {"role": "user", "content": price_user}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        raw = resp.choices[0].message.content
        data = extract_json_fallback(raw or "") or {}

        lbl = str(data.get("label") or label)
        mk = data.get("market_price")
        try:
            market_price_num = float(mk)
        except Exception:
            market_price_num = None

        descr = str(data.get("description") or "").strip()
        sources = data.get("sources") or []
        clean_sources = []
        for s in sources[:5]:
            try:
                title = str(s.get("title") or "")[:140]
                url = str(s.get("url") or "")
                if title and url:
                    clean_sources.append({"title": title, "url": url})
            except Exception:
                continue

        selling_price = "N/A"
        market_price_label = "N/A"
        if market_price_num is not None:
            selling_price = f"${int(market_price_num * 0.8)}"
            market_price_label = f"${market_price_num:.2f}".rstrip('0').rstrip('.')

        result = {
            "label": lbl,
            "listing_id": listing_id,
            "market_price": market_price_label,
            "selling_price": selling_price,
            "description": descr if descr else "Could not fetch details.",
            "sources": clean_sources
        }

    except Exception as e:
        result = {
            "label": label,
            "listing_id": listing_id,
            "market_price": "N/A",
            "selling_price": "N/A",
            "description": "Could not fetch details.",
            "sources": []
        }

    # Category classification
    category = classify_category_with_llm(result["label"], debug_entries)
    result["category"] = category

    # Bundle session data (persist image bytes + user info)
    try:
        prev = json.loads(request.form.get("session_payload", "{}")) or {}
    except Exception:
        prev = {}
    session_data = {
        "result": result,
        "images": prev.get("images", []),
        "email": prev.get("email", ""),
        "address": prev.get("address", "")
    }

    # Build a Posting Preview (everything that will be sent to backend)
    email = session_data["email"]
    address = session_data["address"]
    city, postal = _parse_city_postal(address)
    condition = "like new"  # default used by backend if not overridden
    # Convert "$123" -> 123 as int, fallback to 0
    price_str = str(result.get("selling_price") or "").replace("$", "").strip()
    try:
        price_int = int(float(price_str)) if price_str else 0
    except Exception:
        price_int = 0
    preview = {
        "email": email,
        "address": address,
        "city": city,
        "postal_code": postal,
        "category": result["category"],
        "title": result["label"],
        "condition": condition,
        "price": price_int,
        "description": result["description"],
        "images": session_data["images"],
    }

    # Save a listing record (optional)
    try:
        listing_dir = LISTINGS_DIR / listing_id
        listing_dir.mkdir(parents=True, exist_ok=True)
        (listing_dir / "meta.json").write_text(json.dumps({
            "created_at": datetime.utcnow().isoformat() + "Z",
            "result": result,
            "email": email,
            "address": address,
            "preview": preview
        }, indent=2), encoding="utf-8")
    except Exception:
        pass

    return render_template_string(
        INDEX_HTML,
        result=result,
        combined=None,
        per_image=None,
        session_payload=session_data,
        preview=preview,
        debug_entries=debug_entries,
        categories=CATEGORIES
    )

# ---------------------------------------------------------------------------------
# Backend orchestration (launch Agent + SSE + magic link submission)
# ---------------------------------------------------------------------------------

def _parse_city_postal(address: str) -> Tuple[str, str]:
    try:
        m = re.search(r",\s*([A-Za-z .'-]+),\s*[A-Z]{2}\s*(\d{5})", address)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        m2 = re.search(r"(\d{5})(?:-\d{4})?$", address)
        postal = m2.group(1) if m2 else ""
        parts = [p.strip() for p in address.split(",") if p.strip()]
        city = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
        return city, postal
    except Exception:
        return "", ""

def _load_agent_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    for k in ["PATH","HOME","SHELL","LANG","LC_ALL","SSL_CERT_FILE","REQUESTS_CA_BUNDLE","PYTHONPATH"]:
        v = os.environ.get(k)
        if v:
            env[k] = v
    env["PYTHONUNBUFFERED"] = "1"
    vals = dotenv_values(AGENT_ENV_FILE) if AGENT_ENV_FILE and Path(AGENT_ENV_FILE).exists() else {}
    for k, v in (vals or {}).items():
        if isinstance(v, str):
            env[k] = v
    return env

def _save_images_for_job(job_dir: Path, session_images: List[Dict[str, Any]]) -> List[str]:
    paths: List[str] = []
    img_dir = job_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(session_images or []):
        try:
            b64 = (img or {}).get("bytes", "")
            if not isinstance(b64, str):
                continue
            data = base64.b64decode(b64)
            name = (img or {}).get("filename") or f"image_{i+1}.jpg"
            safe = "".join(c for c in name if c.isalnum() or c in "._-")[:64] or f"image_{i+1}.jpg"
            p = img_dir / safe
            with open(p, "wb") as f:
                f.write(data)
            paths.append(str(p.resolve()))
        except Exception:
            continue
    return paths

def _start_agent(job_id: str, payload: Dict[str, Any]) -> None:
    job = _job_registry[job_id]
    q: "queue.Queue[str]" = job["queue"]

    result = payload.get("result", {}) or {}
    email = payload.get("email", "") or ""
    address = payload.get("address", "") or ""
    images = payload.get("images", []) or []


    title = str(result.get("label") or "For sale")
    category = str(result.get("category") or "general for sale")
    selling = str(result.get("selling_price") or "").replace("$","").strip()
    try:
        price = str(int(float(selling))) if selling else "0"
    except Exception:
        price = "0"
    description = str(result.get("description") or "Great condition. Pickup only.")

    env = _load_agent_env()
    env["EMAIL"] = email
    env["CATEGORY"] = category
    env["POSTING_TITLE"] = title
    env["CONDITION"] = env.get("CONDITION", "like new")
    env["PRICE"] = price
    env["ADDRESS"] = address
    env["DESCRIPTION"] = description
    env["IMAGES"] = ",".join(images)
    env["HEADLESS"] = env.get("HEADLESS", "false")
    env["HIGHLIGHT"] = env.get("HIGHLIGHT", "true")
    env["MAGIC_LINK_FILE"] = str(job["magic_link_file"])

    cmd = ["python", "script.py"]
    try:
        subprocess.run(["uv", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        cmd = ["uv", "run", "script.py"]
    except Exception:
        pass

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        job["proc"] = proc
        assert proc.stdout is not None
        for line in proc.stdout:
            q.put(line.rstrip("\n"))
    except Exception as e:
        q.put(f"[web] Failed to start agent: {e}")
    finally:
        if job.get("proc"):
            ret = job["proc"].wait()
            q.put(f"[web] Agent exited with code {ret}")
        q.put("__DONE__")

@app.route("/post_listing", methods=["POST"])
def post_listing():
    try:
        payload = {}
        try:
            payload = json.loads(request.form.get("session_payload", "{}")) or {}
        except Exception:
            payload = {}
        if not payload:
            return render_template_string(INDEX_HTML, categories=CATEGORIES, error_msg="Missing session payload; please start over.")

        # Create job directory
        job_id = str(uuid.uuid4())[:8]
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Save images for agent
        saved_paths = _save_images_for_job(job_dir, payload.get("images", []))
        if not saved_paths:
            return render_template_string(INDEX_HTML, categories=CATEGORIES, error_msg="No images available to post; please start over.")

        # Prepare magic link file
        magic_link_file = job_dir / "magic_link.txt"
        magic_link_file.write_text("", encoding="utf-8")

        # Register job
        q: "queue.Queue[str]" = queue.Queue()
        _job_registry[job_id] = {"queue": q, "proc": None, "magic_link_file": magic_link_file}

        # Payload for agent thread
        payload_for_agent = {
            "result": payload.get("result", {}),
            "email": payload.get("email", ""),
            "address": payload.get("address", ""),
            "images": saved_paths,
        }

        t = threading.Thread(target=_start_agent, args=(job_id, payload_for_agent), daemon=True)
        t.start()

        return redirect(url_for("job", job_id=job_id))
    except Exception as e:
        return render_template_string(INDEX_HTML, categories=CATEGORIES, error_msg=f"Failed to start job: {e}")

@app.route("/job/<job_id>", methods=["GET"])
def job(job_id: str):
    if job_id not in _job_registry:
        return render_template_string(INDEX_HTML, categories=CATEGORIES, error_msg="Unknown job ID.")
    return render_template_string(JOB_HTML, job_id=job_id)

@app.route("/events/<job_id>", methods=["GET"])
def events(job_id: str):
    if job_id not in _job_registry:
        return Response("data: {\"type\":\"line\",\"value\":\"Unknown job\"}\n\n", mimetype="text/event-stream")

    q: "queue.Queue[str]" = _job_registry[job_id]["queue"]

    def gen():
        try:
            yield f"data: {json.dumps({'type':'line','value':'[web] Streaming started'})}\n\n"
            while True:
                try:
                    line = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if line == "__DONE__":
                    yield f"data: {json.dumps({'type':'done','value':'done'})}\n\n"
                    break
                yield f"data: {json.dumps({'type':'line','value':line})}\n\n"
        except GeneratorExit:
            pass
        except Exception as e:
            yield f"data: {json.dumps({'type':'line','value':f'[web] SSE error: {e}'})}\n\n"

    return Response(gen(), mimetype="text/event-stream")

@app.route("/submit_magic_link/<job_id>", methods=["POST"])
def submit_magic_link(job_id: str):
    if job_id not in _job_registry:
        return render_template_string(INDEX_HTML, categories=CATEGORIES, error_msg="Unknown job ID.")
    magic_link = (request.form.get("magic_link") or "").strip()
    file_path: Path = _job_registry[job_id]["magic_link_file"]
    try:
        file_path.write_text(magic_link, encoding="utf-8")
        return redirect(url_for("job", job_id=job_id))
    except Exception as e:
        return render_template_string(INDEX_HTML, categories=CATEGORIES, error_msg=f"Failed to submit magic link: {e}")

# ---------------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set host="0.0.0.0" if running in a container or remote
    app.run(debug=True)
