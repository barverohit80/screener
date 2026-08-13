import google.generativeai as genai
import time
import os
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# GEMINI CONFIGURATION
# =====================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Prioritized list of models to try
FALLBACK_MODELS = [
    'gemini-2.5-flash',
    'gemini-1.5-flash',
    'gemini-pro'
]

def analyze_with_llm(prompt_text, max_retries_per_model=3):
    """
    Analyzes text using Gemini API with model fallback and retries.
    
    Args:
        prompt_text (str): The prompt to send to the LLM.
        max_retries_per_model (int): Number of retries for EACH model before falling back.
        
    Returns:
        str: The analysis result or None if all models fail.
    """
    if not GEMINI_API_KEY:
        print("❌ Error: GEMINI_API_KEY is not set.")
        return None

    print("Initializing Gemini API...")
    genai.configure(api_key=GEMINI_API_KEY)

    for model_name in FALLBACK_MODELS:
        print(f"\n--- Attempting with Model: {model_name} ---")
        
        for attempt in range(max_retries_per_model):
            try:
                print(f"Sending prompt (Attempt {attempt+1}/{max_retries_per_model})...")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt_text)
                
                if response and response.text:
                    print(f"✅ Success with {model_name}!")
                    return response.text
                else:
                    print(f"⚠️ Empty response from {model_name}.")
            
            except Exception as e:
                print(f"⚠️ Attempt {attempt+1} failed for {model_name}: {e}")
                
                # Check for common error types
                error_msg = str(e).lower()
                if "404" in error_msg or "not found" in error_msg:
                    print(f"🚫 Model {model_name} not available. Moving to next fallback.")
                    break # Skip retries for this model and move to next
                
                if "429" in error_msg or "rate limit" in error_msg:
                    wait_time = (attempt + 1) * 20
                    print(f"⏳ Rate limited. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    # General network or API error
                    time.sleep(5)
        
    print("\n❌ All models and retries exhausted. Analysis failed.")
    return None

if __name__ == "__main__":
    # Connectivity and Fallback Test
    print("🚀 Running LLM Connectivity and Fallback Test...")
    test_prompt = "Say 'Hello, the AI system is operational' in a creative way."
    
    result = analyze_with_llm(test_prompt)
    if result:
        print("\n--- TEST RESULT ---")
        print(result)
        print("-------------------")
    else:
        print("\n❌ Test failed. Check API key and model availability.")
