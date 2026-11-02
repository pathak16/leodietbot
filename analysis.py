import json
import os
import typing_extensions as typing

# import google.generativeai as genai
# from google.api_core.exceptions import ResourceExhausted
import time
from groq import Groq
import base64

# genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Vision models to try, in order, comma-separated (Railway variable VISION_MODELS).
# Groq's daily token limit (TPD) is per model, so when one model's daily
# allowance runs out we switch to the next one for the rest of the day.
VISION_MODELS = [m.strip() for m in os.getenv("VISION_MODELS", "qwen/qwen3.8-27b").split(",") if m.strip()]
_exhausted_models = {}  # model -> time.time() when its daily limit was hit
_EXHAUSTED_FOR_SECONDS = 6 * 3600


def _is_daily_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "429" in msg and ("per day" in msg or "(tpd)" in msg or "(rpd)" in msg)


def _available_models():
    now = time.time()
    return [m for m in VISION_MODELS
            if now - _exhausted_models.get(m, 0) > _EXHAUSTED_FOR_SECONDS]


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


class MacroAnalysis(typing.TypedDict):
    identified_items: list[str]
    meal_type: str  # "Breakfast", "Lunch", "Snack", "Dinner", "Beverage"
    food_source_type: (
        str  # "Home-cooked", "Packaged_Ultra_Processed", "Restaurant_Delivery"
    )
    staple_format: (
        str  # "Roti_Atta", "Rice", "Poha_Breakfast", "Dal", "Biscuits_Snack",
        # "Beverage", "Other"
    )
    estimated_protein_grams: float
    estimated_carbs_grams: float
    estimated_fat_grams: float
    estimated_fiber_grams: float
    protein_source_present: bool
    protein_source_type: str  # "Dairy", "Dal_Legumes", "Eggs", "Meat", "Soy", "None"
    is_caffeine_or_sugar_crutch: bool
    primary_fuel_source: str  # "Carbohydrate-Dominant", "Fat-Dominant", "Balanced"
    crash_risk_level: str  # "High", "Medium", "Low"


# def run_gemini_vision_pipeline(image_path: str, caption: str = "") -> dict:
#     """Sends the local image to Gemini 3.5 Flash and returns parsed JSON."""
#     model = genai.GenerativeModel("gemini-3.5-flash")

#     # 1. Upload temporary image to Google API
#     uploaded_file = genai.upload_file(path=image_path)

#     prompt = f"""
#     You are a nutritional research scientist analyzing everyday Indian diets.
#     Participant's caption: "{caption}".

#     Examine this photo and extract the nutritional profile and behavioral indicators.
#     - If packaged, evaluate brand/nutrition indicators if visible.
#     - If home-cooked or street food, estimate portions based on standard Indian household servings (e.g., standard katori = 150g, 1 roti = ~30g flour).
#     - Flag quick energy fixes (chai with sugar, cola, biscuits, energy drinks) under is_caffeine_or_sugar_crutch.
#     - Assess glycemic crash risk based on the balance of carbs vs protein and fiber.
#     """

#     try:
#         max_retries = 3
#         for attempt in range(max_retries):
#             try:
#                 response = model.generate_content(
#                     [uploaded_file, prompt],
#                     generation_config=genai.GenerationConfig(
#                         response_mime_type="application/json",
#                         response_schema=MacroAnalysis,
#                         temperature=0.2,
#                     ),
#                 )
#                 return json.loads(response.text)

#             except ResourceExhausted:
#                 if attempt < max_retries - 1:
#                     print(
#                         f"[Rate Limit] 5 RPM hit on attempt {attempt + 1}. Waiting 20s..."
#                     )
#                     time.sleep(20)
#                 else:
#                     raise

#     finally:
#         # 2. Delete the remote file only once when done (success or final failure)
#         try:
#             uploaded_file.delete()
#         except Exception as e:
#             print(f"[Cleanup Warning] Could not delete remote file: {e}")


def run_gemini_vision_pipeline(image_path: str, caption: str = "") -> dict:
    """Sends the local image to Groq (Llama 3.2 Vision) and returns parsed JSON."""
    base64_image = encode_image(image_path)

    prompt = f"""You are a nutritional research scientist analyzing everyday Indian diets.
Participant's caption: "{caption}".

Examine this photo and extract the nutritional profile and behavioral indicators.
- If packaged, evaluate brand/nutrition indicators if visible.
- If home-cooked or street food, estimate portions based on standard Indian household servings (e.g., standard katori = 150g, 1 roti = ~30g flour).
- Flag quick energy fixes (chai with sugar, cola, biscuits, energy drinks) under is_caffeine_or_sugar_crutch.
- Assess glycemic crash risk based on the balance of carbs vs protein and fiber.

Return ONLY a valid JSON object matching this schema:
{{
    "identified_items": ["item 1", "item 2"],
    "meal_type": "Breakfast" | "Lunch" | "Snack" | "Dinner" | "Beverage",
    "food_source_type": "Home-cooked" | "Packaged_Ultra_Processed" | "Restaurant_Delivery",
    "staple_format": "Roti_Atta" | "Rice" | "Poha_Breakfast" | "Dal" | "Biscuits_Snack" | "Beverage" | "Other",
    "estimated_protein_grams": float,
    "estimated_carbs_grams": float,
    "estimated_fat_grams": float,
    "estimated_fiber_grams": float,
    "protein_source_present": boolean,
    "protein_source_type": "Dairy" | "Dal_Legumes" | "Eggs" | "Meat" | "Soy" | "None",
    "is_caffeine_or_sugar_crutch": boolean,
    "primary_fuel_source": "Carbohydrate-Dominant" | "Fat-Dominant" | "Balanced",
    "crash_risk_level": "High" | "Medium" | "Low"
}}
"""

    models = _available_models()
    if not models:
        raise RuntimeError("Daily Groq limit reached on every model in VISION_MODELS; try again later.")

    last_error = None
    for model in models:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    },
                                },
                            ],
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                return json.loads(response.choices[0].message.content)

            except Exception as e:
                last_error = e
                if _is_daily_limit_error(e):
                    print(f"[Groq] Daily limit hit on {model}; switching to the next model.")
                    _exhausted_models[model] = time.time()
                    break
                if attempt < max_retries - 1:
                    print(f"[Groq Retry] {model} attempt {attempt + 1} failed: {e}. Retrying...")
                    time.sleep(2)
                else:
                    raise
    raise last_error
