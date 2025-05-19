import datetime
from fastapi import FastAPI, HTTPException, Body # Body for input
from pydantic import BaseModel, Field # BaseModel and Field for input model
import uvicorn
import os
import re # For parsing the srs string from JSON
from typing import Optional

# --- Configuration Constants ---
FACTOR_MODIFIER = 0.15
HARD_FACTOR = 1.2
MIN_FACTOR = 1.30

DEFAULT_INITIAL_FACTOR = 2.50
DEFAULT_INITIAL_INTERVAL = 0.0
# DEFAULT_SIGNAL_FOR_NEW_ITEM is not needed as signal is always required in input JSON

app = FastAPI(
    title="Simplified Spaced Repetition System (SRS) Calculator",
    description="API to calculate next review date. Input via JSON, Output is a plain string.",
    version="2.6.0" # Version bump for new JSON input and string output
)

# --- Pydantic Model for JSON Input ---
class SRSInput(BaseModel):
    srs: Optional[str] = Field(None, description="SRS string: 'Day, Mon DayNum F.FF/I.II'. Optional for new items.")
    signal: int = Field(..., ge=1, le=4, description="User recall quality (1-4). Required.")


# --- Core SRS Logic (remains the same) ---
def calculate_srs_logic(current_interval_days: float, current_factor: float, signal: int) -> tuple[float, float]:
    new_interval = float(current_interval_days)
    new_factor = float(current_factor)

    if not (0 <= signal <= 4):
        raise ValueError("Internal Logic Error: Signal must be an integer between 0 and 4.")
    if current_factor <= 0:
        raise ValueError("Current factor must be greater than 0.")
    if current_interval_days < 0:
        raise ValueError("Current interval days cannot be negative.")

    if signal == 0: # Not used by API directly due to 1-4 input constraint, but logic supports it
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

# Regex to parse "DayAbbrev, MonAbbrev DayNum Factor/Interval"
# Example: "Fri, Apr 25 23.15/45.62"
# Group 1: DayOfWeekAbbrev (e.g., "Fri")
# Group 2: MonthAbbrev (e.g., "Apr")
# Group 3: DayNum (e.g., "25")
# Group 4: Factor (e.g., "23.15")
# Group 5: Interval (e.g., "45.62")
SRS_STRING_PATTERN = re.compile(
    r"^([A-Za-z]{3}),\s*([A-Za-z]{3})\s+(\d{1,2})\s+(\d+\.\d+)\/(\d+\.\d+)$"
)

@app.post("/calculate/", response_class=str) # Explicitly setting response_class to str for plain text
async def calculate_next_review_json_in_string_out(
    input_data: SRSInput = Body(...) # Use Body for the whole Pydantic model
) -> str:
    """
    Calculates the next review details based on JSON input.
    Outputs a plain string: "Day, Mon DayNum NewFactor/NewInterval"

    Input JSON body example (existing item):
    {
       "srs": "Fri, Apr 25 23.15/45.62",
       "signal": 1
    }

    Input JSON body example (new item, srs field absent or null):
    {
       "signal": 3
    }
    """
    current_factor: float
    current_interval_days: float
    actual_signal: int = input_data.signal # Signal is always present from input_data

    if input_data.srs:
        # srs string is provided, parse it
        match = SRS_STRING_PATTERN.match(input_data.srs)
        if not match:
            raise HTTPException(
                status_code=400,
                detail="Invalid 'srs' string format in JSON. Expected 'Day, Mon DayNum F.FF/I.II', e.g., 'Fri, Apr 25 23.15/45.62'"
            )
        try:
            # We don't use date parts (group 1, 2, 3) for calculation itself
            current_factor_str = match.group(4)
            current_interval_days_str = match.group(5)

            current_factor = float(current_factor_str)
            current_interval_days = float(current_interval_days_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid numeric values for factor or interval in 'srs' string.")
        except IndexError: # Should not happen if regex matches
            raise HTTPException(status_code=400, detail="Could not parse all components from 'srs' string.")
    else:
        # srs string is NOT provided (or null), use defaults for a new item
        current_factor = DEFAULT_INITIAL_FACTOR
        current_interval_days = DEFAULT_INITIAL_INTERVAL

    try:
        new_interval_days, new_factor = calculate_srs_logic(
            current_interval_days,
            current_factor,
            actual_signal # This is input_data.signal
        )

        days_to_add = round(new_interval_days)
        next_review_date_obj = datetime.date.today() + datetime.timedelta(days=days_to_add)

        # Format the date string: "DayAbbrev, MonthAbbrev DayNum" (non-padded day)
        human_readable_date_str = ""
        if os.name == 'nt': # Windows
             human_readable_date_str = next_review_date_obj.strftime("%a, %b %#d")
        else: # Linux/macOS
            try:
                human_readable_date_str = next_review_date_obj.strftime("%a, %b %-d")
            except ValueError: # Fallback if %-d is not supported
                try:
                    human_readable_date_str = next_review_date_obj.strftime("%a, %b %e").lstrip() # %e might add leading space
                except ValueError: # Further fallback if %e also fails (unlikely for modern Python)
                     human_readable_date_str = next_review_date_obj.strftime("%a, %b %d")


        # Fallback to zero-padded day if specific non-padded options fail
        if not human_readable_date_str:
            human_readable_date_str = next_review_date_obj.strftime("%a, %b %d")


        # Format the final output string
        # Example: "Sun, Jun 15 22.95/0.00"
        output_string = f"{human_readable_date_str} {new_factor:.2f}/{new_interval_days:.2f}"
        return output_string

    except ValueError as ve: # Catch specific errors from our logic
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        print(f"Error during calculation: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# --- Running the App (for local development) ---
if __name__ == "__main__":
    print("Starting Simplified SRS Backend API (v2.6.0)...")
    print("Access the docs at http://127.0.0.1:8000/docs")
    print("---")
    print("Example - Existing item (srs string provided in JSON):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"srs\\\": \\\"Fri, Apr 25 23.15/45.62\\\", \\\"signal\\\": 1}\"")
    print("Expected output string: e.g., 'Sat, Apr 26 22.95/0.00' (date will be today's date for interval 0)")
    print("---")
    print("Example - New item (srs field absent or null in JSON):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"signal\\\": 3}\"")
    print("Expected output string: e.g., 'Sun, Apr 27 2.50/1.00' (date will be tomorrow if today is Sat, Apr 26)")
    print("---")
    print("Example - New item (srs field explicitly null):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"srs\\\": null, \\\"signal\\\": 4}\"")
    print("Expected output string: e.g., 'Sun, Apr 27 2.65/1.00' (date will be tomorrow if today is Sat, Apr 26)")
    print("---")

    uvicorn.run("srs_api:app", host="127.0.0.1", port=8000, reload=True)