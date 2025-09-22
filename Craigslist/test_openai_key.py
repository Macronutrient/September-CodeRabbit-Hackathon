#!/usr/bin/env python3
"""Test OpenAI API key functionality."""

import os
import sys
import time
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("[config] Missing OPENAI_API_KEY. Set it in your shell or .env.")
        print("Example (zsh): export OPENAI_API_KEY=\"your_key\"")
        return 2

    try:
        from openai import OpenAI
    except Exception as e:
        print(f"[deps] Missing openai package: {e}\nInstall with: pip install openai")
        return 3

    try:
        client = OpenAI(api_key=key)
        start = time.time()
        response = client.chat.completions.create(
            model="gpt-4.1",  # Using gpt-4.1 as specified
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=50
        )
        elapsed = time.time() - start
        
        text = response.choices[0].message.content.strip() if response.choices else "No response"
        print("[ok] OpenAI GPT-4.1 API call succeeded.")
        print(f"[timing] {elapsed:.2f}s")
        
        # Sanitize and shorten response
        snippet = text.replace("\n", " ")
        if len(snippet) > 200:
            snippet_display = snippet[:200] + "…"
        else:
            snippet_display = snippet
        print(f"[response] {snippet_display}")
        return 0
    except Exception as e:
        # Provide hints for common failure modes
        msg = str(e)
        if "API key" in msg or "authentication" in msg.lower():
            print("[error] Authentication failed. Check that your API key is valid and has access to GPT-4.1.")
        elif "quota" in msg.lower() or "limit" in msg.lower():
            print("[error] Quota or rate limit issue.")
        elif "model" in msg.lower() and "not found" in msg.lower():
            print("[error] Model gpt-4.1 not found. Check if the model name is correct or try 'gpt-4' instead.")
        else:
            print("[error] OpenAI test failed.")
        print(f"[detail] {msg}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
