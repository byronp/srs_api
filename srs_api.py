import datetime
from fastapi import FastAPI, HTTPException, Body # Added Body
from pydantic import BaseModel # Added BaseModel
import uvicorn
import os # Retained for potential future use, but not for date formatting here
import re # No longer needed for parsing input
from typing import Optional

# --- Configuration Constants ---
FACTOR_MODIFIER = 0.15
HARD_FACTOR = 1.2
MIN_FACTOR = 1.30

DEFAULT_INITIAL_FACTOR = 2.50
DEFAULT_INITIAL_INTERVAL = 0.0
# DEFAULT_SIGNAL_FOR_NEW_ITEM is no longer needed as signal is always required

app = FastAPI(
    title="Simplified Spaced Repetition System (SRS) Calculator",
    description="API to calculate next review date. Input and Output via JSON.",
    version="2.4.0" # Version bump for JSON I/O change
)

# --- Pydantic Model for JSON Output ---
class SRSOutput(BaseModel):
    next_review_date: str
    new_interval_days: float
    new_factor: float

# --- Core SRS Logic (remains the same) ---
def calculate_srs_logic(current_interval_days: float, current_factor: float, signal: int) -> tuple[float, float]:
    new_interval = float(current_interval_days)
    new_factor = float(current_factor)

    if not (0 <= signal <= 4): # Internal logic can still handle 0-4, API layer enforces 1-4 for input
        raise ValueError("Internal Logic Error: Signal must be an integer between 0 and 4.")
    if current_factor <= 0:
        raise ValueError("Current factor must be greater than 0.")
    if current_interval_days < 0:
        raise ValueError("Current interval days cannot be negative.")

    if signal == 0:
        pass
    elif signal == 1:
        new_factor = max(MIN_FACTOR, current_factor - 0.20)
        new_interval = 0
    elif signal == 2:
        new_factor = max(MIN_FACTOR, current_factor - FACTOR_MODIFIER)
        new_interval = current_interval_days * HARD_FACTOR
    elif signal == 3:
        if current_interval_days < 1:
            new_interval = 1.0
        else:
            new_interval = current_interval_days * current_factor
    elif signal == 4:
        new_factor = current_factor + FACTOR_MODIFIER
        if current_interval_days < 1:
            new_interval = max(1.0, 1.0 * current_factor)
        else:
            new_interval = current_interval_days * current_factor

    new_interval = round(max(0, new_interval), 2)
    new_factor = round(new_factor, 2)
    return new_interval, new_factor

# --- API Endpoint ---
@app.post("/calculate/", response_model=SRSOutput)
async def calculate_next_review_json(
    signal: int = Body(..., ge=1, le=4, description="User recall quality (1-4)."),
    current_interval_days: Optional[float] = Body(DEFAULT_INITIAL_INTERVAL, ge=0, description="Current interval in days. Defaults to 0.0 if not provided."),
    current_factor: Optional[float] = Body(DEFAULT_INITIAL_FACTOR, gt=0, description="Current ease factor. Defaults to 2.50 if not provided.")
) -> SRSOutput:
    """
    Calculates the next review details based on JSON input.

    Input JSON body example (existing item):
    {
        "current_interval_days": 10.0,
        "current_factor": 2.3,
        "signal": 3
    }

    Input JSON body example (new item, only signal provided):
    {
        "signal": 3
    }
    (current_interval_days will default to 0.0, current_factor to 2.50)


    Output JSON:
    {
        "next_review_date": "YYYY-MM-DD",
        "new_interval_days": 0.0,
        "new_factor": 0.0
    }
    """
    # FastAPI handles the defaulting if parameters are not in the body, based on Body(DEFAULT_VALUE, ...)
    # So, current_interval_days and current_factor will have their default values if not sent.

    try:
        new_interval_days, new_factor = calculate_srs_logic(
            current_interval_days, # Will be default if not provided
            current_factor,      # Will be default if not provided
            signal
        )

        days_to_add = round(new_interval_days)
        next_review_date_obj = datetime.date.today() + datetime.timedelta(days=days_to_add)

        # Format date to "YYYY-MM-DD"
        iso_date_str = next_review_date_obj.isoformat()

        return SRSOutput(
            next_review_date=iso_date_str,
            new_interval_days=new_interval_days,
            new_factor=new_factor
        )

    except ValueError as ve: # Catch specific errors from our logic
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        print(f"Error during calculation: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# --- Running the App (for local development) ---
if __name__ == "__main__":
    print("Starting Simplified SRS Backend API (v2.4.0)...")
    print("Access the docs at http://127.0.0.1:8000/docs")
    print("---")
    print("Example - Existing item (provide all fields):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"current_interval_days\\\": 10, \\\"current_factor\\\": 2.3, \\\"signal\\\": 3}\"")
    print("Expected JSON output: {\"next_review_date\":\"YYYY-MM-DD\",\"new_interval_days\":23.0,\"new_factor\":2.3}")
    print("---")
    print("Example - New item (only signal provided, others default):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"signal\\\": 3}\"")
    print("Expected JSON output: {\"next_review_date\":\"YYYY-MM-DD\",\"new_interval_days\":1.0,\"new_factor\":2.5}")
    print("---")
    print("Example - New item (signal and one default override):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"current_factor\\\": 2.0, \\\"signal\\\": 4}\"")
    print("Expected JSON output: {\"next_review_date\":\"YYYY-MM-DD\",\"new_interval_days\":1.0,\"new_factor\":2.15}")
    print("---")

    uvicorn.run("srs_api:app", host="127.0.0.1", port=8000, reload=True)