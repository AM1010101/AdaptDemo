from pydantic_ai import Agent, RunContext
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.providers.google_gla import GoogleGLAProvider

from config import get_settings, Settings
from httpx import AsyncClient
from dataclasses import dataclass
from enum import Enum
import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from models import RawProductScrapeData
from typing import List


settings = get_settings()


@dataclass
class Deps:
    client: AsyncClient
    agent_id: str | None
    user_id: str | None = None

def get_deps(agent_id:str, user_id:str) -> Deps:
    return Deps(client=AsyncClient(), agent_id=agent_id, user_id=user_id)

# https://ai.google.dev/gemini-api/docs/models
class GeminiModelName(Enum):
    GEMINI_2_0_FLASH_EXP = "gemini-2.0-flash-exp" # Default
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_2_0_FLASH_LITE = "gemini-2.0-flash-lite"
    GEMINI_2_5_FLASH_PREVIEW = "gemini-2.5-flash-preview-04-17"
    GEMINI_2_5_PRO_PREVIEW = "gemini-2.5-pro-preview-05-06" # paid
    GEMINI_2_5_PRO_EXP = "gemini-2.5-pro-exp-03-25" # free


def create_gemini_model(model_name: GeminiModelName | str, api_settings: Settings) -> GeminiModel:
    """Creates and returns a GeminiModel instance."""
    model_id = model_name.value if isinstance(model_name, GeminiModelName) else model_name
    return GeminiModel(
        model_id,
        provider=GoogleGLAProvider(api_key=api_settings.GEMINI_API_KEY)
    )

model: GeminiModel = create_gemini_model(GeminiModelName.GEMINI_2_5_FLASH_PREVIEW, settings)

system_prompt = """Your role is to take the messages passed to you and then parse out the information so that it can returned.
The data is for mobile phones, most likely either samsung or apple. do your best to match up fragmented information into the expected output format.
Tidy up text by capitalising appropriatly. For example 512gb -> 512GB. iphone -> iPhone. 

Try to stick to the following list of colours or state unknown:
[Black, Red, Blue, Green, Yellow, White, Silver, Grey, Purple, Lime, Beige, Unknown]

When Stating the items condition try to capitilise appropriatly. a -> A, new -> New.
"""

agent = Agent(
    model=model,
    deps_type=Deps,
    system_prompt=system_prompt,
    model_settings={"temperature": 0.5},
    output_type=List[RawProductScrapeData]
)


@agent.tool
def get_current_datetime(
    ctx: RunContext[Deps], # ctx is part of the pydantic-ai tool signature
    timezone_str: str | None = "UTC",
    format_str: str | None = None
) -> str:
    """
    Agent Tool: Retrieves the current date and time, with options for specifying timezone and output format.

    Args:
        timezone_str: Optional. The IANA timezone string (e.g., 'Europe/London', 'America/New_York').
                      Defaults to 'UTC'. If 'local' is provided, it uses the server's local timezone.
        format_str: Optional. A Python strftime format string (e.g., '%Y-%m-%d %H:%M:%S').
                    If None (default), the output will be in ISO 8601 format.

    Returns:
        A string representing the current date and time, formatted as requested,
        or an error message if issues occur (e.g., invalid timezone or format string).
    """
    try:
        # Call the synchronous core logic

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        target_datetime = now_utc

        if timezone_str:
            if timezone_str.lower() == "local":
                target_datetime = datetime.datetime.now().astimezone()
            elif timezone_str.lower() != "utc":
                try:
                    tz = ZoneInfo(timezone_str)
                    target_datetime = now_utc.astimezone(tz)
                except ZoneInfoNotFoundError:
                    # Logged by the wrapper tool, but good to be specific here too if used directly
                    return f"Error: Invalid timezone string '{timezone_str}'."
                except Exception:
                    # Catching generic exception for ZoneInfo issues
                    return f"Error: Could not apply timezone '{timezone_str}'."

        if format_str:
            try:
                formatted_time = target_datetime.strftime(format_str)
            except ValueError as e:
                return f"Error: Invalid format string '{format_str}'. Details: {e}"
        else:
            formatted_time = target_datetime.isoformat()
        return formatted_time
    except Exception as e:
        # Logged by the wrapper tool, but good to be specific here too if used directly
        return f"Error: An unexpected error occurred: {str(e)}"

# # tool to search suppliers
# @agent.tool
# def search_sources(ctx: RunContext[Deps],search_term:str):
#     pass


# # tool to insert rows
# @agent.tool
# def insert_records(ctx: RunContext[Deps],records):
#     pass