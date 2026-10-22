"""
Diagnostic Tool: Provider & Model Capability Checker
===================================================
Checks exact capabilities of the user's GEMINI_API_KEY:
1. Model listing from Google AI Studio.
2. Text generation (Gemini Flash).
3. Image generation (Imagen 3 / Gemini).
4. Video generation (Veo 2.0 / Veo 3.1).
"""

import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types as genai_types

api_key = os.getenv("GEMINI_API_KEY", "").strip()
print(f"[*] API Key: {api_key[:12]}... (length: {len(api_key)})")

client = genai.Client(api_key=api_key)

print("\n" + "=" * 60)
print("1. QUERYING AVAILABLE MODELS FOR THIS ACCOUNT")
print("=" * 60)
try:
    models = list(client.models.list())
    print(f"[+] Total models accessible: {len(models)}")
    for m in models:
        name = getattr(m, "name", str(m))
        methods = getattr(m, "supported_generation_methods", [])
        print(f"  - {name} | methods: {methods}")
except Exception as exc:
    print(f"[-] models.list() failed: {exc}")

print("\n" + "=" * 60)
print("2. TESTING TEXT GENERATION (Gemini 2.5 Flash / Flash Lite)")
print("=" * 60)
for text_m in ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-3.8-flash"]:
    try:
        resp = client.models.generate_content(
            model=text_m,
            contents="Say 'Jai Shree Ram' in 3 words.",
        )
        print(f"[SUCCESS] {text_m} response: {resp.text.strip()}")
        break
    except Exception as exc:
        print(f"[-] {text_m} failed: {exc}")

print("\n" + "=" * 60)
print("3. TESTING GEMINI FLASH IMAGE GENERATION (generate_content)")
print("=" * 60)
for img_model in ["gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"]:
    try:
        print(f"Testing model: {img_model}...")
        resp = client.models.generate_content(
            model=img_model,
            contents="Generate an image of a sacred golden glowing lotus flower in water, cinematic vertical 9:16",
        )
        # Check for image parts in candidates
        img_bytes = None
        if hasattr(resp, "candidates") and resp.candidates:
            for part in getattr(resp.candidates[0].content, "parts", []):
                if hasattr(part, "inline_data") and part.inline_data:
                    img_bytes = part.inline_data.data
                    print(f"[SUCCESS] Got inline image ({len(img_bytes)} bytes, mime: {part.inline_data.mime_type})!")
                    break

        if img_bytes:
            out_test = os.path.join("storage", "generated", "test_gemini_image.jpg")
            os.makedirs(os.path.dirname(out_test), exist_ok=True)
            with open(out_test, "wb") as f:
                f.write(img_bytes)
            print(f"[+] Saved test image to {out_test}")
            break
        else:
            print(f"[-] {img_model} returned text instead of image: {getattr(resp, 'text', '')[:100]}")
    except Exception as exc:
        print(f"[-] {img_model} failed: {exc}")

print("\n" + "=" * 60)
print("4. TESTING VEO VIDEO GENERATION")
print("=" * 60)
for veo_model in ["veo-2.0-generate-001", "veo-3.1-fast-generate-preview"]:
    try:
        print(f"Testing model: {veo_model}...")
        op = client.models.generate_videos(
            model=veo_model,
            prompt="Cinematic vertical shot of golden divine energy rising into stormy sky, 9:16",
            config=genai_types.GenerateVideosConfig(
                aspect_ratio="9:16",
                resolution="720p",
            ),
        )
        print(f"[SUCCESS] Veo operation submitted: {getattr(op, 'name', op)}")
        break
    except Exception as exc:
        print(f"[-] Veo ({veo_model}) failed: {exc}")

print("=" * 60)
