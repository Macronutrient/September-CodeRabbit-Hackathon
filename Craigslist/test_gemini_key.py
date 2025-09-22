import os
import sys
import time
from dotenv import load_dotenv

# Minimal, safe smoke test for Gemini API key.
# Exits 0 on success, non-zero on failure with a helpful message.


def main() -> int:
    load_dotenv()
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        print("[config] Missing GOOGLE_API_KEY or GEMINI_API_KEY. Set it in your shell or .env.")
        print("Example (zsh): export GOOGLE_API_KEY=\"your_key\"")
        return 2

    try:
        import google.generativeai as genai
    except Exception as e:
        print(f"[deps] Missing google-generativeai package: {e}\nInstall with: pip install -r requirements.txt")
        return 3

    try:
        genai.configure(api_key=key)
        # Use a fast, lightweight model; adjust if needed.
        model = genai.GenerativeModel("gemini-2.5-flash")
        start = time.time()
        resp = model.generate_content("hello")
        elapsed = time.time() - start
        text = (resp.text or "").strip() if hasattr(resp, "text") else str(resp)
        print("[ok] Gemini API call succeeded.")
        print(f"[timing] {elapsed:.2f}s")
        # Sanitize and shorten without using backslashes inside f-string expressions
        snippet = text.replace("\n", " ")
        if len(snippet) > 200:
            snippet_display = snippet[:200] + "…"
        else:
            snippet_display = snippet
        print(f"[response] {snippet_display}")
        return 0
    except Exception as e:
        # Provide a hint for some common failure modes
        msg = str(e)
        if "API key" in msg or "permission" in msg.lower():
            print("[error] Authentication failed. Check that your API key is valid and has access to the model.")
        elif "quota" in msg.lower():
            print("[error] Quota or rate limit issue.")
        else:
            print("[error] Gemini test failed.")
        print(f"[detail] {msg}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
