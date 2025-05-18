import datetime
from fastapi import FastAPI, HTTPException, Query
import uvicorn
import os
import re
from typing import Optional

# --- Configuration Constants ---
FACTOR_MODIFIER = 0.15
HARD_FACTOR = 1.2
MIN_FACTOR = 1.30

DEFAULT_INITIAL_FACTOR = 2.50
DEFAULT_INITIAL_INTERVAL = 0.0
DEFAULT_SIGNAL_FOR_NEW_ITEM = 3 # Good

app = FastAPI(
    title="Simplified Spaced Repetition System (SRS) Calculator",
    description="API to calculate next review date. Input via query parameters, output is a plain string.",
    version="2.2.0", # Version bump for new input format and optional input
    redirect_slashes=False
)

# --- Core SRS Logic (remains the same) ---
def calculate_srs_logic(current_interval_days: float, current_factor: float, signal: int) -> tuple[float, float]:
    new_interval = float(current_interval_days)
    new_factor = float(current_factor)

    # Signal validation inside logic (0-4)
    if not (0 <= signal <= 4):
        raise ValueError("Internal Logic Error: Signal must be an integer between 0 and 4.")
    if current_factor <= 0:
        raise ValueError("Current factor must be greater than 0.")
    if current_interval_days < 0:
        raise ValueError("Current interval days cannot be negative.")

    if signal == 0: # Complete failure
        pass
    elif signal == 1: # Incorrect, but recognized (Hard)
        new_factor = max(MIN_FACTOR, current_factor - 0.20)
        new_interval = 0
    elif signal == 2: # Partial recall, difficulty (OK/Medium)
        new_factor = max(MIN_FACTOR, current_factor - FACTOR_MODIFIER)
        new_interval = current_interval_days * HARD_FACTOR
    elif signal == 3: # Correct recall, some effort (Good)
        if current_interval_days < 1:
            new_interval = 1.0
        else:
            new_interval = current_interval_days * current_factor
    elif signal == 4: # Perfect, effortless recall (Easy)
        new_factor = current_factor + FACTOR_MODIFIER
        if current_interval_days < 1:
            new_interval = max(1.0, 1.0 * current_factor) # Ensure new cards get at least 1 day, influenced by factor
        else:
            new_interval = current_interval_days * current_factor

    new_interval = round(max(0, new_interval), 2)
    new_factor = round(new_factor, 2)
    return new_interval, new_factor

# --- API Endpoint ---

# Regex to parse "[[date:YYYY-MM-DD]] F.FF/I.II"
# Group 1: YYYY-MM-DD (date string)
# Group 2: F.FF (factor)
# Group 3: I.II (interval)
SRS_INPUT_PATTERN = re.compile(r"^\[\[date:(\d{4}-\d{2}-\d{2})\]\]\s+(\d+\.\d+)\/(\d+\.\d+)$")

@app.post("/calculate/") # Or @app.get
async def calculate_next_review_flexible(
    srs: Optional[str] = Query(None, description="Current SRS state: '[[date:YYYY-MM-DD]] F.FF/I.II'. Optional."),
    signal: Optional[int] = Query(None, ge=1, le=4, description="User recall quality (1-4). Required if 'srs' is provided. Defaults if 'srs' is absent.")
) -> str:
    """
    Calculates the next review details.
    - If 'srs' is provided, 'signal' (1-4) is also required.
    - If 'srs' is not provided, defaults are used for interval/factor,
      and 'signal' defaults to 3 (Good) if not provided.

    Output format: "Month Day, Year F.FF/I.II"
    """
    current_factor: float
    current_interval_days: float
    actual_signal: int

    if srs:
        # srs string is provided, parse it
        match = SRS_INPUT_PATTERN.match(srs)
        if not match:
            raise HTTPException(
                status_code=400,
                detail="Invalid SRS string format. Expected '[[date:YYYY-MM-DD]] F.FF/I.II', e.g., '[[date:2025-05-04]] 2.50/12.50'"
            )
        if signal is None:
            raise HTTPException(
                status_code=400,
                detail="Signal (1-4) is required when srs string is provided."
            )

        try:
            # prev_date_str = match.group(1) # Available if needed
            current_factor_str = match.group(2)
            current_interval_days_str = match.group(3)

            current_factor = float(current_factor_str)
            current_interval_days = float(current_interval_days_str)
            actual_signal = signal
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid numeric values for factor or interval in SRS string.")
        except IndexError:
            raise HTTPException(status_code=400, detail="Could not parse all components from SRS string.")
    else:
        # srs string is NOT provided, use defaults (new item scenario)
        current_factor = DEFAULT_INITIAL_FACTOR
        current_interval_days = DEFAULT_INITIAL_INTERVAL
        actual_signal = signal if signal is not None else DEFAULT_SIGNAL_FOR_NEW_ITEM

    try:
        # The core logic function expects signal 0-4. Our API ensures 1-4 input.
        # If we defaulted signal to 0 for new items, it would work, but problem specified 1-4
        new_interval_days, new_factor = calculate_srs_logic(
            current_interval_days,
            current_factor,
            actual_signal # actual_signal is now guaranteed to be 1-4, or our default for new item
        )

        days_to_add = round(new_interval_days)
        next_review_date_obj = datetime.date.today() + datetime.timedelta(days=days_to_add)

        human_readable_date_str = ""
        if os.name == 'nt':
             human_readable_date_str = next_review_date_obj.strftime("%B %#d, %Y")
        else:
            try:
                human_readable_date_str = next_review_date_obj.strftime("%B %-d, %Y")
            except ValueError: # Fallback for OS where %-d is not supported
                human_readable_date_str = next_review_date_obj.strftime("%B %e, %Y").lstrip()

        if not human_readable_date_str: # General fallback
            human_readable_date_str = next_review_date_obj.strftime("%B %d, %Y")

        output_string = f"[[{human_readable_date_str}]] {new_factor:.2f}/{new_interval_days:.2f}"
        return output_string

    except ValueError as ve: # Catch specific errors from our logic
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        print(f"Error during calculation: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# --- Running the App (for local development) ---
if __name__ == "__main__":
    print("Starting Simplified SRS Backend API (v2.2.0)...")
    print("Access the docs at http://127.0.0.1:8000/docs")
    print("---")
    print("Example - SRS string provided (URL Encoded for curl):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/?srs=%5B%5Bdate%3A2025-05-04%5D%5D%208.15%2F16.77&signal=1\"")
    print("Expected format: 'Month Day, Year F.FF/I.II'")
    print("---")
    print("Example - No SRS string (new item), signal provided:")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/?signal=3\"")
    print("Expected format: 'Month Day, Year F.FF/I.II' (based on defaults and today's date)")
    print("---")
    print("Example - No SRS string, no signal (new item, default signal):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\"")
    print("Expected format: 'Month Day, Year F.FF/I.II' (based on defaults and today's date)")
    print("---")

    uvicorn.run("srs_api:app", host="127.0.0.1", port=8000, reload=True)