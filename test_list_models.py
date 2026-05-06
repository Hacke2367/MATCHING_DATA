"""List every Gemini model available to this API key and filter for generateContent support."""
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ERROR: GEMINI_API_KEY not set"); exit(1)

for api_ver in ("v1beta", "v1"):
    client = genai.Client(api_key=api_key, http_options={"api_version": api_ver})
    print(f"\n{'='*60}")
    print(f"  API version: {api_ver}")
    print(f"{'='*60}")
    try:
        models = list(client.models.list())
        flash_models = [m for m in models if "flash" in m.name.lower() or "pro" in m.name.lower()]
        for m in sorted(flash_models, key=lambda x: x.name):
            methods = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", [])
            can_generate = "generateContent" in str(methods)
            print(f"  {'✓' if can_generate else '✗'}  {m.name}  —  {methods}")
    except Exception as exc:
        print(f"  ERROR: {exc}")
