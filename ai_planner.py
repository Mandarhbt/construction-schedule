"""
AI Planner - generate activity JSON from user inputs using an LLM.

Usage:
- Set environment variable `OPENAI_API_KEY` with your key, or configure OpenAI client in your environment.
- Call `generate_activities(user_inputs, max_activities=50, template_seed_path=None)`

Security: This module does NOT use any hardcoded API keys. Do NOT paste secrets into source files.
"""
from dotenv import load_dotenv
import os

load_dotenv()

def test_connection():
    """Check OpenAI connectivity. Returns a short status string.

    This helper is resilient: it will not raise on import-time if OpenAI
    client libraries or the API key are missing. It attempts the new
    `openai.OpenAI` client first, then falls back to the legacy `openai`
    package if available.
    """
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return "OPENAI_API_KEY not set"

    # Try new OpenAI client
    try:
        from openai import OpenAI as NewOpenAI
        client = NewOpenAI(api_key=key)
        try:
            resp = client.responses.create(model="gpt-4", input="Reply with only the word SUCCESS")
            if hasattr(resp, "output_text"):
                return resp.output_text
            # fallback: try to stringify
            return str(resp)
        except Exception as e:
            # fall through to legacy if the new client call fails
            legacy_err = e
    except Exception:
        legacy_err = None

    # Try legacy openai package
    try:
        import openai as legacy_openai
        legacy_openai.api_key = key
        res = legacy_openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Reply with only the word SUCCESS"}],
            temperature=0
        )
        return res['choices'][0]['message']['content']
    except Exception as e:
        msg = f"Connection failed. new_client_error={legacy_err}, legacy_error={e}"
        return msg

from typing import List, Union, Optional, Any, Dict
import os
import re
import json
import logging

try:
    import openai
except Exception:
    openai = None

from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class PredItem(BaseModel):
    id: str
    type: str = Field(default="FS")
    lag: int = Field(default=0)

    @validator('type')
    def type_upper(cls, v):
        return str(v).upper()


class ActivityModel(BaseModel):
    ID: str
    Activity: str
    Duration: int
    Predecessor: Optional[Union[str, List[Union[str, Dict[str, Any]]]]] = Field(default="")
    WBS: Optional[Union[str, List[str]]] = Field(default="General")
    Notes: Optional[str] = None

    @validator('ID', pre=True)
    def id_to_str(cls, v):
        return str(v)

    @validator('Duration', pre=True)
    def dur_to_int(cls, v):
        if v is None or v == "":
            return 0
        try:
            return int(v)
        except Exception:
            # try extract number
            s = re.sub(r"[^0-9]", "", str(v))
            return int(s) if s else 0

    @validator('WBS', pre=True)
    def normalize_wbs(cls, v):
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "General"
        if isinstance(v, list):
            return [str(x) for x in v]
        s = str(v).strip()
        # split by common separators into list OR keep string — templates and UI support both
        if any(sep in s for sep in ['>', '/', '|', '\\']):
            parts = [p.strip() for p in re.split(r"[>/|\\\\]", s) if p.strip()]
            return parts if parts else s
        return s


def build_prompt(user_inputs: Dict[str, Any], max_activities: int = 100, template_seed: Optional[List[Dict]] = None) -> str:
    """Construct the LLM prompt from structured project inputs.

    user_inputs expected keys:
        project_name, project_type, structural_system, floors, basements,
        built_up_area, notes  (all optional except at least one present)
    """
    ptype   = user_inputs.get("project_type", "Commercial")
    ssys    = user_inputs.get("structural_system", "Concrete")
    floors  = int(user_inputs.get("floors", 5))
    basements = int(user_inputs.get("basements", 0))
    area    = float(user_inputs.get("built_up_area", 1000))
    pname   = user_inputs.get("project_name", "")
    notes   = user_inputs.get("notes", "")

    lines = []
    lines.append("You are an expert construction planner and scheduler.")
    lines.append("Generate a detailed, realistic construction activity list as a JSON array.")
    lines.append("")
    lines.append("=== PROJECT DETAILS ===")
    if pname:
        lines.append(f"Project Name    : {pname}")
    lines.append(f"Project Type    : {ptype}")
    lines.append(f"Structural System: {ssys}")
    lines.append(f"Floors          : {floors}")
    lines.append(f"Basements       : {basements}")
    lines.append(f"Built-up Area   : {area} sqm")
    if notes.strip():
        lines.append(f"Additional Info : {notes.strip()}")

    lines.append("")
    lines.append("=== INSTRUCTIONS ===")
    lines.append(f"1. Generate up to {max_activities} activities covering the full project lifecycle.")
    lines.append("2. Use a multi-level WBS. Typical phases for a building project:")
    lines.append("   Pre-Construction, Substructure, Superstructure (per floor), Finishing, MEP, External Works, Commissioning.")
    lines.append(f"3. For each of the {floors} floor(s), create separate activities")
    lines.append("   (e.g. 'Columns Floor 1', 'Slab Floor 1', 'Finishing Floor 1').")
    if basements > 0:
        lines.append(f"4. For each of the {basements} basement(s), include: Excavation, PCC, Raft/Footing RCC, Basement Slab, Waterproofing.")
    lines.append("5. Every activity MUST have a unique string ID (e.g. 'A1', 'A2' … or 'MOB', 'EXC_B1').")
    lines.append("6. Predecessor field must contain a comma-separated list of IDs the activity depends on (empty string if none).")
    lines.append("   All referenced IDs must exist in the same array.")
    lines.append("7. Duration values are in working days. Use realistic durations scaled to the project size.")
    lines.append(f"   (Rough guide: small project ≤1000 sqm, large >{area:.0f} sqm needs longer durations.)")
    lines.append("8. WBS field: use dot-separated or plain text levels, e.g. '2. Substructure > 2.1 Excavation'.")
    lines.append("9. Output ONLY valid JSON — a single top-level array. No prose, no markdown fences, no explanation.")
    lines.append("")
    lines.append("=== REQUIRED JSON SCHEMA (each object) ===")
    lines.append('{ "ID": "string", "Activity": "string", "Duration": integer, "Predecessor": "comma-separated IDs or empty", "WBS": "string" }')
    lines.append("")
    lines.append("=== EXAMPLE (2-floor residential, concrete) ===")

    example = [
        {"ID": "MOB",    "Activity": "Mobilization & Site Setup",   "Duration": 7,  "Predecessor": "",           "WBS": "1. Pre-Construction"},
        {"ID": "EXC",    "Activity": "Excavation",                  "Duration": 12, "Predecessor": "MOB",        "WBS": "2. Substructure"},
        {"ID": "PCC",    "Activity": "PCC",                         "Duration": 3,  "Predecessor": "EXC",        "WBS": "2. Substructure"},
        {"ID": "FTG",    "Activity": "Footing RCC",                 "Duration": 10, "Predecessor": "PCC",        "WBS": "2. Substructure"},
        {"ID": "COL_F1", "Activity": "Columns Floor 1",             "Duration": 8,  "Predecessor": "FTG",        "WBS": "3. Superstructure > Floor 1"},
        {"ID": "SLB_F1", "Activity": "Slab RCC Floor 1",           "Duration": 10, "Predecessor": "COL_F1",     "WBS": "3. Superstructure > Floor 1"},
        {"ID": "COL_F2", "Activity": "Columns Floor 2",             "Duration": 8,  "Predecessor": "SLB_F1",    "WBS": "3. Superstructure > Floor 2"},
        {"ID": "SLB_F2", "Activity": "Slab RCC Floor 2",           "Duration": 10, "Predecessor": "COL_F2",     "WBS": "3. Superstructure > Floor 2"},
        {"ID": "FIN_F1", "Activity": "Internal Finishing Floor 1",  "Duration": 20, "Predecessor": "SLB_F1",    "WBS": "4. Finishing > Floor 1"},
        {"ID": "FIN_F2", "Activity": "Internal Finishing Floor 2",  "Duration": 20, "Predecessor": "SLB_F2",    "WBS": "4. Finishing > Floor 2"},
        {"ID": "MEP",    "Activity": "MEP Works",                   "Duration": 25, "Predecessor": "FIN_F1,FIN_F2", "WBS": "5. MEP"},
        {"ID": "EXT",    "Activity": "External Works & Landscaping","Duration": 15, "Predecessor": "MEP",        "WBS": "6. External Works"},
        {"ID": "COM",    "Activity": "Testing & Commissioning",     "Duration": 7,  "Predecessor": "EXT",        "WBS": "7. Commissioning"},
    ]
    lines.append(json.dumps(example, indent=2))
    lines.append("")
    lines.append(f"Now generate the full activity list for the {ptype} ({ssys}) project described above.")
    lines.append("Remember: output ONLY the JSON array, nothing else.")

    prompt = "\n".join(lines)

    if template_seed:
        prompt += "\n\n=== SEED TEMPLATE (use as reference for activity names / structure) ===\n"
        prompt += json.dumps(template_seed, indent=2)

    return prompt


def extract_json_from_text(text: str) -> Optional[str]:
    # try to find first JSON array
    m = re.search(r"(\[\s*\{[\s\S]*?\}\s*\])", text)
    if m:
        return m.group(1)
    # fallback: find a top-level JSON object
    m2 = re.search(r"(\{[\s\S]*?\})", text)
    if m2:
        return m2.group(1)
    return None


def call_llm(prompt: str, model: str = "gpt-4", temperature: float = 0.0, max_tokens: int = 1500) -> str:
    """Call OpenAI ChatCompletion (or raise helpful error if openai not installed).
    The function reads OPENAI_API_KEY from environment."""
    if openai is None:
        raise RuntimeError("openai package not installed. Install via 'pip install openai'.")
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment. Please set it before calling the AI planner.")

    # First try the new openai-python client (OpenAI.responses)
    new_client_err = None
    try:
        # Some installs expose an OpenAI client class on the module
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(api_key=api_key)
            try:
                # Use the Responses API (new client). Use max_output_tokens instead of max_tokens.
                resp = client.responses.create(model=model, input=prompt, temperature=temperature, max_output_tokens=max_tokens)
                # New client may provide a convenience 'output_text'
                if hasattr(resp, "output_text") and resp.output_text:
                    return resp.output_text
                # Try to extract textual content from response.output
                out = getattr(resp, "output", None)
                if out:
                    texts = []
                    # output is typically a list of dicts with 'content' arrays
                    for item in out:
                        if isinstance(item, dict):
                            for c in item.get("content", []):
                                # c may be a dict like {'type': 'output_text', 'text': '...'} or a string
                                if isinstance(c, dict) and "text" in c:
                                    texts.append(c["text"])
                                elif isinstance(c, str):
                                    texts.append(c)
                    if texts:
                        return "\n".join(texts)
                # Fallback: try to stringify response
                return str(resp)
            except Exception as e:
                new_client_err = e
        else:
            new_client_err = None
    except Exception as e:
        new_client_err = e

    # Fall back to legacy ChatCompletion API if present
    legacy_err = None
    try:
        # Some environments still have legacy `openai` module behavior
        openai.api_key = api_key
        # Prepare chat-style messages as fallback
        messages = [
            {"role": "system", "content": "You are a strict JSON generator for construction activity lists."},
            {"role": "user", "content": prompt}
        ]
        if hasattr(openai, "ChatCompletion"):
            resp = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            text = resp['choices'][0]['message']['content']
            return text
        else:
            legacy_err = RuntimeError("openai module doesn't provide ChatCompletion. Consider installing legacy openai or use the new client.")
    except Exception as e:
        legacy_err = e

    # If we reach here, both attempts failed — raise an informative error
    raise RuntimeError(f"LLM call failed. new_client_error={new_client_err}, legacy_error={legacy_err}")


def parse_and_validate(raw_text: str) -> List[ActivityModel]:
    """Extract JSON array from raw_text and validate items.
    Returns list of ActivityModel objects or raises ValueError with details.
    """
    jtext = extract_json_from_text(raw_text)
    if not jtext:
        raise ValueError("No JSON array found in model output.")
    try:
        data = json.loads(jtext)
    except Exception as e:
        # try to clean common mistakes: trailing commas
        cleaned = re.sub(r",\s*\]", "]", jtext)
        cleaned = re.sub(r",\s*\}", "}", cleaned)
        try:
            data = json.loads(cleaned)
        except Exception:
            raise ValueError(f"Failed to parse JSON from model output: {e}")

    if not isinstance(data, list):
        raise ValueError("Parsed JSON is not an array of activities.")

    validated = []
    errors = []
    for i, item in enumerate(data):
        try:
            act = ActivityModel(**item)
            validated.append(act)
        except Exception as e:
            errors.append((i, str(e), item))

    if errors:
        raise ValueError(f"Validation errors for generated activities: {errors}")

    # additional checks: unique IDs
    ids = [a.ID for a in validated]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate IDs detected in generated activities.")

    return validated


def generate_activities(user_inputs: Dict[str, Any], max_activities: int = 50, template_seed: Optional[List[Dict]] = None, model: str = "gpt-4", temperature: float = 0.0) -> List[Dict[str, Any]]:
    """High-level entry point: build prompt, call LLM, parse and validate, return list of dicts.
    Note: this function will raise RuntimeError if OPENAI_API_KEY is not set.
    """
    prompt = build_prompt(user_inputs, max_activities=max_activities, template_seed=template_seed)
    raw = call_llm(prompt, model=model, temperature=temperature)
    validated = parse_and_validate(raw)
    # return plain dicts
    return [json.loads(v.json()) for v in validated]


if __name__ == '__main__':
    # quick local test scaffold (won't call LLM unless key present)
    ui = {"description": "Small test", "floors": 1, "basements": 0}
    try:
        acts = generate_activities(ui, max_activities=10)
        print(json.dumps(acts, indent=2))
    except Exception as e:
        print("AI Planner test failed:", e)
