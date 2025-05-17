import datetime
from fastapi import FastAPI, HTTPException, Body
import uvicorn
import os # For platform-specific date formatting if needed

# --- Configuration Constants ---
FACTOR_MODIFIER = 0.15
HARD_FACTOR = 1.2
MIN_FACTOR = 1.30 # SM-2 typically has a minimum ease factor

app = FastAPI(
    title="Simplified Spaced Repetition System (SRS) Calculator",
    description="API to calculate next review date. Input via JSON body, output is a plain string.",
    version="2.0.0" # Version bump for significant change
)

# --- Core SRS Logic (remains the same, independent of FastAPI/Pydantic) ---

def calculate_srs_logic(current_interval_days: float, current_factor: float, signal: int) -> tuple[float, float]:
    """
    Calculates the new interval and factor based on the SM-2 like algorithm provided.

    Args:
        current_interval_days (float): Current interval in days.
        current_factor (float): Current ease factor.
        signal (int): User's recall quality (0-4).

    Returns:
        tuple[float, float]: (new_interval_days, new_factor)
    """
    new_interval = float(current_interval_days)
    new_factor = float(current_factor)

    # Signal validation (basic, can be enhanced)
    if not (0 <= signal <= 4):
        raise ValueError("Signal must be an integer between 0 and 4.")
    if current_factor <= 0: # Factor must be positive
        raise ValueError("Current factor must be greater than 0.")
    if current_interval_days < 0:
        raise ValueError("Current interval days cannot be negative.")


    if signal == 0:  # Complete failure
        # "No change to parameters in your implementation"
        pass # new_interval and new_factor remain as current_interval_days and current_factor

    elif signal == 1:  # Incorrect, but recognized (Hard)
        new_factor = max(MIN_FACTOR, current_factor - 0.20)
        new_interval = 0  # "Resets interval to 0 (immediate review)"

    elif signal == 2:  # Partial recall, difficulty (OK/Medium)
        new_factor = max(MIN_FACTOR, current_factor - FACTOR_MODIFIER) # factor - 0.15
        new_interval = current_interval_days * HARD_FACTOR

    elif signal == 3:  # Correct recall, some effort (Good)
        if current_interval_days < 1: # Handles new cards or cards just reset (interval 0)
            new_interval = 1.0
        else:
            new_interval = current_interval_days * current_factor

    elif signal == 4:  # Perfect, effortless recall (Easy)
        new_factor = current_factor + FACTOR_MODIFIER # factor + 0.15
        # Use current_factor for interval calculation before it's modified
        if current_interval_days < 1:
            new_interval = max(1.0, 1.0 * current_factor)
        else:
            new_interval = current_interval_days * current_factor


    # Ensure interval is not negative, and round to a practical number of decimal places.
    new_interval = round(max(0, new_interval), 2)
    new_factor = round(new_factor, 2)

    return new_interval, new_factor

# --- API Endpoint ---

@app.post("/calculate/")
async def calculate_next_review(
    current_interval_days: float = Body(..., ge=0, description="Current interval in days. E.g., 0, 1, 10.5"),
    current_factor: float = Body(..., gt=0, description="Current ease factor. E.g., 2.5"),
    signal: int = Body(..., ge=0, le=4, description="User recall quality: 0-4")
) -> str: # The endpoint now directly returns a string
    """
    Calculates the next review details and returns a formatted string.

    Input JSON body example:
    {
        "current_interval_days": 10,
        "current_factor": 2.3,
        "signal": 3
    }

    Output format: "Month Day, Year Factor/Interval"
    Example: "June 5, 2025 1.15/1.00"
    """
    try:
        # Basic validation (FastAPI's Body with ge/le/gt handles some of this)
        # Additional custom validation could be added here if needed beyond what Body provides.
        # The calculate_srs_logic function also has some internal validation.

        new_interval_days, new_factor = calculate_srs_logic(
            current_interval_days,
            current_factor,
            signal
        )

        # Calculate the next review date
        days_to_add = round(new_interval_days)
        next_review_date_obj = datetime.date.today() + datetime.timedelta(days=days_to_add)

        # Format the date string: "Month Day, Year"
        # Using %d for wider compatibility for day part if %-d or %#d causes issues.
        # %-d (Unix) or %#d (Windows) for non-padded day, %e for space-padded.
        # A common, usually safe way:
        human_readable_date_str = ""
        if os.name == 'nt': # Windows
             human_readable_date_str = next_review_date_obj.strftime("%B %#d, %Y")
        else: # Linux/macOS
            try:
                human_readable_date_str = next_review_date_obj.strftime("%B %-d, %Y")
            except ValueError: # Fallback if %-d is not supported
                human_readable_date_str = next_review_date_obj.strftime("%B %e, %Y").lstrip() # %e might add leading space

        # Fallback to zero-padded day if specific non-padded options fail or for simplicity
        if not human_readable_date_str:
            human_readable_date_str = next_review_date_obj.strftime("%B %d, %Y")


        # Format the final output string
        # Example: "June 5, 2025 1.15/1.00"
        output_string = f"{human_readable_date_str} {new_factor:.2f}/{new_interval_days:.2f}"

        return output_string

    except ValueError as ve: # Catch specific errors from our logic or invalid inputs
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        # Log the exception e for debugging
        import traceback
        print(f"Error during calculation: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# --- Running the App (for local development) ---
if __name__ == "__main__":
    print("Starting Simplified SRS Backend API (v2.0.0)...")
    print("Access the docs at http://127.0.0.1:8000/docs")
    print("The endpoint expects a JSON body with 'current_interval_days', 'current_factor', and 'signal'.")
    print("---")
    print("Example Usage with curl (run in a new terminal):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"current_interval_days\\\": 10, \\\"current_factor\\\": 2.3, \\\"signal\\\": 3}\"")
    print("---")
    print("Expected output is a plain string, e.g., 'August 15, 2024 2.30/23.00' (date will vary)")

    uvicorn.run(app, host="127.0.0.1", port=8000)