import datetime
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
import uvicorn
import os
import re
from typing import Optional
from starlette.responses import PlainTextResponse  # Keep this for plain text output

# --- Configuration Constants ---
FACTOR_MODIFIER = 0.15
HARD_FACTOR = 1.2
MIN_FACTOR = 1.30

DEFAULT_INITIAL_FACTOR = 2.50
DEFAULT_INITIAL_INTERVAL = 0.0

app = FastAPI(
    title="Simplified Spaced Repetition System (SRS) Calculator",
    description="API to calculate next review date. Input via JSON, Output is a plain string.",
    version="2.8.0"  # Version bump (from 2.7.0 base, new input srs format)
)


# --- Pydantic Model for JSON Input ---
class SRSInput(BaseModel):
    srs: Optional[str] = Field(
        None,
        description="SRS string: '[[date:YYYY-MM-DD]] F.FF/I.II'. Optional for new items.",  # UPDATED description
        examples=["[[date:2028-04-09]] 23.30/1056.10"]  # ADDED example
    )
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

# UPDATED Regex to parse input "[[date:YYYY-MM-DD]] Factor/Interval"
# Example: "[[date:2028-04-09]] 23.30/1056.10"
# Group 1: YYYY-MM-DD (date string)
# Group 2: Factor
# Group 3: Interval
SRS_STRING_PATTERN = re.compile(
    r"^\[\[date:(\d{4}-\d{2}-\d{2})\]\]\s+(\d+\.\d+)\/(\d+\.\d+)$"
)


@app.post("/calculate/", response_class=PlainTextResponse)
async def calculate_next_review_json_in_string_out(
        input_data: SRSInput = Body(...)
) -> str:
    """
    Calculates the next review details based on JSON input.
    Outputs a plain string: "[[date:YYYY-MM-DD]] NewFactor/NewInterval"

    Input JSON body example (existing item):
    {
       "srs": "[[date:2028-04-09]] 23.30/1056.10", // New format
       "signal": 1
    }

    Input JSON body example (new item, srs field absent or null):
    {
       "signal": 3
    }
    """
    current_factor: float
    current_interval_days: float
    actual_signal: int = input_data.signal

    if input_data.srs:
        match = SRS_STRING_PATTERN.match(input_data.srs)
        if not match:
            error_detail = f"Invalid 'srs' string format: '{input_data.srs}'. Expected '[[date:YYYY-MM-DD]] F.FF/I.II'"  # UPDATED error message
            # print(f"ERROR: {error_detail}") # Optional basic print logging
            raise HTTPException(status_code=400, detail=error_detail)
        try:
            # date_string = match.group(1) # We don't use this for calculation
            current_factor_str = match.group(2)  # UPDATED group index
            current_interval_days_str = match.group(3)  # UPDATED group index
            current_factor = float(current_factor_str)
            current_interval_days = float(current_interval_days_str)
        except ValueError:
            # print(f"ERROR: Invalid numeric values in srs string: {input_data.srs}") # Optional
            raise HTTPException(status_code=400,
                                detail="Invalid numeric values for factor or interval in 'srs' string.")
        except IndexError:
            # print(f"ERROR: Could not parse components from srs string: {input_data.srs}") # Optional
            raise HTTPException(status_code=400, detail="Could not parse all components from 'srs' string.")
    else:
        # print("INFO: No 'srs' string provided, using defaults.") # Optional
        current_factor = DEFAULT_INITIAL_FACTOR
        current_interval_days = DEFAULT_INITIAL_INTERVAL

    try:
        new_interval_days, new_factor = calculate_srs_logic(
            current_interval_days,
            current_factor,
            actual_signal
        )

        days_to_add = round(new_interval_days)
        next_review_date_obj = datetime.date.today() + datetime.timedelta(days=days_to_add)
        iso_date_str = next_review_date_obj.isoformat()  # Format date to "YYYY-MM-DD"

        output_string = f"[[date:{iso_date_str}]] {new_factor:.2f}/{new_interval_days:.2f}"
        # print(f"INFO: Generated output: {output_string}") # Optional
        return output_string

    except ValueError as ve:
        # print(f"ERROR: ValueError during calculation: {ve}") # Optional
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        # print(f"ERROR: Unexpected exception: {e}") # Optional
        # import traceback
        # print(traceback.format_exc()) # For more detailed local debugging if needed
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# --- Running the App (for local development) ---
if __name__ == "__main__":
    print("Starting Simplified SRS Backend API (v2.8.0)...")
    print("Access the docs at http://127.0.0.1:8000/docs")
    print("---")
    print("Example - Existing item (srs string provided in JSON):")
    # UPDATED srs string in curl example
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"srs\\\": \\\"[[date:2028-04-09]] 23.30/1056.10\\\", \\\"signal\\\": 1}\"")
    print(
        "Expected output string: e.g., '[[date:2024-04-26]] 23.10/0.00' (date YYYY-MM-DD format, will depend on current date)")
    print("---")
    print("Example - New item (srs field absent or null in JSON):")
    print("curl -X POST \"http://127.0.0.1:8000/calculate/\" \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -d \"{\\\"signal\\\": 3}\"")
    print(
        "Expected output string: e.g., '[[date:2024-04-27]] 2.50/1.00' (date YYYY-MM-DD format, will depend on current date)")
    print("---")
    uvicorn.run("srs_api:app", host="127.0.0.1", port=8000, reload=True)