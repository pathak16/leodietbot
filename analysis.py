import json
import os
import typing_extensions as typing
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


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


def run_gemini_vision_pipeline(image_path: str, caption: str = "") -> dict:
    """Sends the local image to Gemini 1.5 Flash and returns parsed JSON."""
    model = genai.GenerativeModel("gemini-1.5-flash-001")

    # Upload temporary image to Google API
    uploaded_file = genai.upload_file(path=image_path)

    prompt = f"""
    You are a nutritional research scientist analyzing everyday Indian diets.
    Participant's caption: "{caption}".
    
    Examine this photo and extract the nutritional profile and behavioral indicators.
    - If packaged, evaluate brand/nutrition indicators if visible.
    - If home-cooked or street food, estimate portions based on standard Indian household servings (e.g., standard katori = 150g, 1 roti = ~30g flour).
    - Flag quick energy fixes (chai with sugar, cola, biscuits, energy drinks) under is_caffeine_or_sugar_crutch.
    - Assess glycemic crash risk based on the balance of carbs vs protein and fiber.
    """

    try:
        response = model.generate_content(
            [uploaded_file, prompt],
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=MacroAnalysis,
                temperature=0.2,
            ),
        )
        result = json.loads(response.text)
    finally:
        # Always delete from Google's temporary storage
        try:
            uploaded_file.delete()
        except Exception:
            pass

    return result
