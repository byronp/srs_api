import datetime
from fastapi import FastAPI, HTTPException, Query # Query for input
from pydantic import BaseModel # BaseModel for output
import uvicorn
import os # For potential future use, not date formatting here
import re # For parsing the input string
from typing import Optional

# --- Configuration Constants ---
FACTOR_MODIFIER = 0.15
HARD_FACTOR = 1.2
MIN_FACTOR = 1.30

DEFAULT_INITIAL_FACTOR = 2.50
DEFAULT_INITIAL_INTERVAL = 0.0
DEFAULT_SIGNAL_FOR_NEW_ITEM = 3 # If 'srs' and 'signal' are both absent

app = FastAPI(
    title="Simplified Spaced Repetition System (SRS) Calculator",
    description="API to calculate next review date. Input via query string, Output via JSON.",
    version="2.5.0" # Version bump for mixed I/O change
)

# --- Pydantic Model for JSON Output (remains the same) ---
class SRSOutput(BaseModel):
    next_review_date: str
    new_interval_days: float
    new_factor: float

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

# Regex to parse "[[date: DayAbbrev, MonAbbrev DayNum]] Factor/Interval"
# Example: "[[date: Sun, Jun 15]] 134.15/268.65"
# Group 1: DayOfWeekAbbrev (e.g., "Sun")
# Group 2: MonthAbbrev (e.g., "Jun")
# Group 3: DayNum (e.g., "15")
# Group 4: Factor (e.g., "134.15")
# Group 5: Interval (e.g., "268.65")
SRS_INPUT_PATTERN = re.compile(
    r"^\[\[date:\s*([A-Za-z]{3}),\s*([A-Za-z]{3})\s*(\d{1,2})\s*\]\]\s+(\d+\.\d+)\/(\d+\.\d+)$"
)

@app.post("/calculate/", response_model=SRSOutput) # Or @app.get
async def calculate_next_review_string_in_json_out(
    srs: Optional[str] = Query(None, description="Current SRS state: '[[date: Day, Mon DayNum]] F.FF/I.II'. Optional."),
    signal: Optional[int] = Query(None, ge=1, le=4, description="User recall quality (1-4). Required if 'srs' is provided. Defaults if 'srs' is absent.")
) -> SRSOutput:
    """
    Calculates the next review details.
    - Input 'srs' (string) and 'signal' (int) are via query parameters.
    - If 'srs' is provided, 'signal' (1-4) is also required.
    - If 'srs' is not provided, defaults are used for interval/factor,
      and 'signal' defaults to 3 (Good) if not provided.

    Output is JSON:
    {
        "next_review_date": "YYYY-MM-DD",
        "new_interval_days": 0.0,
        "new_factor": 0.0
    }
    """
    current_factor: float
    current_interval_days: float
    actual_signal: int

    if srs:
        match = SRS_INPUT_PATTERN.match(srs)
        if not match:
            raise HTTPException(
                status_code=400,
                detail="Invalid SRS string format. Expected '[[date: Day, Mon DayNum]] F.FF/I.II', e.g., '[[date: Sun, Jun 15]] 1.23/4.56'"
            )
        if signal is None:
            raise HTTPException(
                status_code=400,
                detail="Signal (1-4) is required when srs string is provided."
            )
        try:
            # We don't use day_of_week_abbrev, month_abbrev, day_num for calculation
            # day_of_week_abbrev = match.group(1)
            # month_abbrev = match.group(2)
            # day_num = match.group(3)
            current_factor_str = match.group(4)
            current_interval_days_str = match.group(5)

            current_factor = float(current_factor_str)
            current_interval_days = float(current_interval_days_str)
            actual_signal = signal
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid numeric values for factor or interval in SRS string.")
        except IndexError: # Should not happen if regex matches, but for safety
            raise HTTPException(status_code=400, detail="Could not parse all components from SRS string.")
    else:
        # srs string is NOT provided, use defaults (new item scenario)
        current_factor = DEFAULT_INITIAL_FACTOR
        current_interval_days = DEFAULT_INITIAL_INTERVAL
        actual_signal = signal if signal is not None else DEFAULT_SIGNAL_FOR_NEW_ITEM

    try:
        new_interval_days, new_factor = calculate_srs_logic(
            current_interval_days,
            current_factor,
            actual_signal
        )

        days_to_add = round(new_interval_days)
        next_review_date_obj = datetime.date.today() + datetime.timedelta(days=days_to_add)

        # Format date to "YYYY-MM-DD" for JSON output
        iso_date_str = next_review_date_obj.isoformat()

        return SRSOutput(
            next_review_date=iso_date_str,
            new_interval_days=new_interval_days,
            new_factor=new_factor
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        print(f"Error during calculation: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# --- Running the App (for local development) ---
if __name__ == "__main__":
    print("Starting Simplified SRS Backend API (v2.5.0)...")
    print("Access the docs at http://127.0.0.1:8000/docs")
    print("---")
    print("Example - SRS string provided (URL Encoded for curl):")
    srs_example_str = "[[date: Sun, Jun 15]] 134.15/268.65"
    # Manual URL encoding for example:
    # [[       -> %5B%5B
    # date:    -> date%3A
    # space    -> %20
    # ,        -> %2C
    # ]]       -> %5D%5D
    # /        -> %2F
    srs_example_encoded = "%5B%5Bdate%3A%20Sun%2C%20Jun%2015%5D%5D%20134.15%2F268.65"
    print(f"curl -X POST \"http://127.0.0.1:8000/calculate/?srs={srs_example_encoded}&signal=1\"")
    print("Expected JSON output: {\"next_review_date\":\"YYYY-MM-DD\",\"new_interval_days\":0.0,\"new_factor\":133.95}")
    print("---")
    print("Example - No SRS string (new item), signal provided:")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/?signal=3\"")
    print("Expected JSON output: {\"next_review_date\":\"YYYY-MM-DD\",\"new_interval_days\":1.0,\"new_factor\":2.5}")
    print("---")
    print("Example - No SRS string, no signal (new item, default signal):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\"")
    print("Expected JSON output: {\"next_review_date\":\"YYYY-MM-DD\",\"new_interval_days\":1.0,\"new_factor\":2.5}")
    print("---")

    uvicorn.run("srs_api:app", host="127.0.0.1", port=8000, reload=True)