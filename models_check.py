import os
import sys
from google import genai
from google.genai import errors as genai_errors
from dotenv import load_dotenv
load_dotenv()

# Ensure API key is loaded (assuming it's in your environment or .env)
# Make sure your virtual environment is active!
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ API Key nahi mili! Pehle GEMINI_API_KEY set karo.")
    sys.exit(1)

client = genai.Client(api_key=api_key)

# The list of best candidate models for your Matching Engine
models_to_test = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-flash-latest"
]

print("=" * 60)
print(" 🚀 PRO-MATCH MODEL TESTER (LIVE CHECK)")
print("=" * 60)

for model_name in models_to_test:
    print(f"⏳ Testing: {model_name}...")
    try:
        # Ek chota sa dummy prompt bhej kar check kar rahe hain
        response = client.models.generate_content(
            model=model_name,
            contents="Reply with exactly one word: 'YES' if you are active."
        )
        print(f"  ✅ WORKING! (Response: {response.text.strip()})")
        print(f"  👉 Use this in your code: model=\"{model_name}\"\n")
    except genai_errors.ClientError as e:
        print(f"  ❌ BLOCKED or ERROR: {e.code} - {e.message}\n")
    except Exception as e:
        print(f"  ❌ UNKNOWN ERROR: {type(e).__name__} - {str(e)}\n")

print("=" * 60)
print("Test Complete. Jiske aage '✅ WORKING' aaya hai, chup-chap wahi model apni app.py/llm_service.py mein daal lo!")