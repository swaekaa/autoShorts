"""
Quick Diagnostic: Check Gemini API Key and Model Access
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from google import genai

api_key = os.getenv("GEMINI_API_KEY", "").strip()
model_name = os.getenv("GEMINI_TEXT_MODEL", "gemini-flash-latest").strip()

print(f"API Key prefix: {api_key[:12]}... (Total length: {len(api_key)})")
print(f"Target model: {model_name}")

client = genai.Client(api_key=api_key)

print("\nTesting text generation with Gemini...")
try:
    response = client.models.generate_content(
        model=model_name,
        contents="Say 'Namaste! Gemini is ready.' in 5 words.",
    )
    print("\n[SUCCESS] Response from Gemini:")
    print(response.text)
except Exception as exc:
    print(f"\n[FAILED] Generation with {model_name} failed: {exc}")
    print("\nListing available models for this key:")
    try:
        models = list(client.models.list())
        for m in models:
            print(f" - {getattr(m, 'name', str(m))}")
    except Exception as list_err:
        print(f"ListModels also failed: {list_err}")
