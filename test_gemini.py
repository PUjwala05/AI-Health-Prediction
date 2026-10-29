
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load the API key from .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY is missing. Check your .env file."
    )

# Connect to Gemini
client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=60000),
)

try:
    print("Connecting to Gemini API...")

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=(
            "You are an assistant for a health-record demonstration. "
            "Write two short educational sentences explaining that "
            "blood test results require clinical interpretation. "
            "Do not diagnose a disease."
        ),
    )

    if response.text and response.text.strip():
        print("\nGemini response:\n")
        print(response.text.strip())
        print("\nSUCCESS: Gemini generated a response.")

    else:
        print("Gemini returned an empty response.")

except Exception as error:
    print("\nGEMINI API REQUEST FAILED")
    print("Error type:", type(error).__name__)
    print("Error details:", str(error))
