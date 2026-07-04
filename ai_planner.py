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

    try:
        from openai import OpenAI as NewOpenAI
        client = NewOpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Reply with only the word SUCCESS"}],
            temperature=0,
            max_tokens=10,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Connection failed: {e}"

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

    # ── Load custom scheduling rules file ───────────────────────────────────
    rules_text = ""
    rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduling_rules.md")
    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as _rf:
            raw_rules = _rf.read()
        # Strip comment lines and blank lines for a compact prompt injection
        rule_lines = [
            ln for ln in raw_rules.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        rules_text = "\n".join(rule_lines)

    # ── Derived scaling hints ────────────────────────────────────────────────
    if area <= 500:
        area_band = "very small (≤500 sqm) — use short durations, single crew"
    elif area <= 1500:
        area_band = "small-medium (500–1500 sqm) — standard durations, 1–2 crews"
    elif area <= 5000:
        area_band = "medium-large (1500–5000 sqm) — scale durations up ~30–50%, multiple crews"
    else:
        area_band = f"large (>{area:.0f} sqm) — significantly longer durations, parallel work fronts"

    # ── Project-type activity hints ──────────────────────────────────────────
    ptype_hints = {
        "residential": [
            "Apartments/villas: include room-wise plastering, tiling, kitchen & bathroom fit-out, balcony works.",
            "Include lift shaft and staircase works if floors > 3.",
            "External: boundary wall, driveway, landscaping, gate.",
        ],
        "commercial": [
            "Include façade/curtain wall, lobby flooring, retail shell & core fit-out, escalator/lift works.",
            "Include raised flooring, false ceiling, fire suppression system, and BMS (Building Management System).",
            "External: parking structure, signage, utility connections.",
        ],
        "hospital": [
            "Include medical gas piping, clean-room partitioning, lead lining for X-ray rooms, nurse call system.",
            "ICU, OT, and pharmacy areas need dedicated finishing and validation activities.",
            "Include HVAC validation, infection-control commissioning, and regulatory inspection activities.",
            "External: ambulance bay, emergency power (DG set), medical waste handling area.",
        ],
    }
    ptype_key = ptype.lower()
    type_hints = ptype_hints.get(ptype_key, [f"Follow standard {ptype} building construction practice."])

    lines = []
    lines.append("You are a senior construction planner with 20+ years of experience.")
    lines.append("Generate a detailed, realistic construction activity list strictly based on ALL project parameters below.")
    lines.append("")
    lines.append("=== PROJECT PARAMETERS (MUST ALL BE REFLECTED IN THE OUTPUT) ===")
    if pname:
        lines.append(f"  Project Name     : {pname}")
    lines.append(f"  Project Type     : {ptype}")
    lines.append(f"  Structural System: {ssys}")
    lines.append(f"  Floors           : {floors}")
    lines.append(f"  Basements        : {basements}  {'← NO basement activities if this is 0' if basements == 0 else f'← generate separate activities for each of the {basements} basement(s)'}")
    lines.append(f"  Built-up Area    : {area:.0f} sqm  ({area_band})")
    if notes.strip():
        lines.append(f"  Special Requirements: {notes.strip()}  ← MUST be reflected in activities")
    lines.append("")

    lines.append("=== MANDATORY RULES ===")
    lines.append(f"1. Generate up to {max_activities} activities covering the FULL project lifecycle for THIS specific project.")
    lines.append("2. WBS phases MUST be: Pre-Construction > Substructure > Superstructure > Finishing > MEP > External Works > Commissioning.")
    lines.append(f"3. FLOORS: Create individual activities for each of the {floors} floor(s). Never merge floors.")
    if basements == 0:
        lines.append("4. BASEMENTS: There are 0 basements. Do NOT generate any basement excavation or basement slab activities.")
    else:
        bsmt_acts = "Excavation, PCC, Raft/Footing RCC, Basement Slab, Basement Waterproofing" if ssys.lower() != "steel" else "Excavation, PCC, Concrete Raft/Isolated Footings, Basement Slab, Waterproofing"
        lines.append(f"4. BASEMENTS: Generate separate activities for each of the {basements} basement level(s). Each must include: {bsmt_acts}.")
    lines.append("5. STRUCTURAL SYSTEM — strictly follow the system selected:")
    if ssys.lower() == "steel":
        lines.append("   • Superstructure = STEEL ONLY: Steel Column Erection, Steel Beam Erection, Metal Deck, Composite Slab, Bolted Connections, Steel Fireproofing.")
        lines.append("   • Do NOT use 'RCC Columns', 'RCC Slab', or 'Shuttering' for the superstructure.")
        lines.append("   • Substructure (foundations only) may use concrete/RCC.")
    else:
        lines.append("   • Superstructure = CONCRETE/RCC ONLY: Shuttering, RCC Columns, RCC Beams, RCC Slab, Deshuttering, Curing.")
        lines.append("   • Do NOT use 'Steel Column Erection', 'Metal Deck', or 'Composite Slab' for the superstructure.")
    lines.append("6. PROJECT TYPE — include activities specific to this building type:")
    for hint in type_hints:
        lines.append(f"   • {hint}")
    if notes.strip():
        lines.append(f"7. SPECIAL REQUIREMENTS: The following client/site requirements MUST generate specific activities: \"{notes.strip()}\"")
        lines.append("   Do not just acknowledge them in Notes — create actual activities addressing each requirement.")
        base_rule = 8
    else:
        base_rule = 7
    lines.append(f"{base_rule}. AREA SCALING: All durations must be scaled for {area:.0f} sqm ({area_band}).")
    lines.append(f"   Per-floor finishing duration guide: ≤500 sqm→10–15 days, 500–1500→15–25 days, 1500–5000→25–40 days, >5000→40+ days.")
    lines.append(f"{base_rule+1}. IDs must be unique strings (e.g. 'MOB', 'EXC_B1', 'COL_F3'). Predecessor = comma-separated IDs or empty string.")
    lines.append(f"{base_rule+2}. NOTES field for EVERY activity: 1–2 sentences stating exactly why this activity exists for THIS project")
    lines.append(f"   (reference project type='{ptype}', structural system='{ssys}', floors={floors}, basements={basements}, area={area:.0f} sqm)")
    lines.append(f"   AND why the duration is realistic for this scale.")
    lines.append(f"{base_rule+3}. Output ONLY a valid JSON array. No prose, no markdown fences, no explanation.")
    lines.append("")
    if rules_text:
        lines.append("=== SCHEDULING LOGIC RULES (MUST BE FOLLOWED) ===")
        lines.append(rules_text)
        lines.append("")
    lines.append("=== REQUIRED JSON SCHEMA ===")
    lines.append('{ "ID": "string", "Activity": "string", "Duration": integer, "Predecessor": "comma-separated IDs or empty", "WBS": "string", "Notes": "rationale referencing project parameters" }')
    lines.append("")

    if ssys.lower() == "steel":
        lines.append(f"=== EXAMPLE SNIPPET ({ptype}, steel, 1 floor) ===")
        example = [
            {"ID": "MOB",    "Activity": "Mobilization & Site Setup",      "Duration": 7,  "Predecessor": "",        "WBS": "1. Pre-Construction",        "Notes": f"Required for all projects; 7 days is appropriate for a {area:.0f} sqm {ptype} building to establish site hoarding, temporary utilities, and crane positions for steel erection."},
            {"ID": "EXC",    "Activity": "Excavation",                     "Duration": 12, "Predecessor": "MOB",     "WBS": "2. Substructure",             "Notes": f"Excavation for isolated pad footings suited to a steel-frame {ptype} building; duration scaled to {area:.0f} sqm footprint."},
            {"ID": "FTG",    "Activity": "Concrete Isolated Footings",     "Duration": 10, "Predecessor": "EXC",     "WBS": "2. Substructure",             "Notes": f"Concrete pad footings are standard for steel frames regardless of superstructure material; 10 days covers formwork, pour, and curing for {area:.0f} sqm."},
            {"ID": "ACOL_F1","Activity": "Steel Column Erection Floor 1",  "Duration": 6,  "Predecessor": "FTG",     "WBS": "3. Superstructure > Floor 1", "Notes": f"Steel columns erected with mobile crane; 6 days per floor reflects standard productivity for a {area:.0f} sqm {ptype} floor plate."},
            {"ID": "ABEM_F1","Activity": "Steel Beam Erection Floor 1",    "Duration": 5,  "Predecessor": "ACOL_F1", "WBS": "3. Superstructure > Floor 1", "Notes": f"Primary and secondary steel beams bolted to columns; 5 days is typical for this floor area and steel erection gang size."},
            {"ID": "ADEK_F1","Activity": "Metal Deck & Composite Slab F1", "Duration": 8,  "Predecessor": "ABEM_F1", "WBS": "3. Superstructure > Floor 1", "Notes": f"Profiled metal decking fixed then concrete poured for composite action; 8 days covers deck fixing, rebar, pour, and initial curing for {area:.0f} sqm."},
        ]
    else:
        lines.append(f"=== EXAMPLE SNIPPET ({ptype}, concrete/RCC, 1 floor) ===")
        example = [
            {"ID": "MOB",    "Activity": "Mobilization & Site Setup",  "Duration": 7,  "Predecessor": "",       "WBS": "1. Pre-Construction",        "Notes": f"Required for all projects; 7 days covers hoarding, temporary services, and batching plant setup for a {area:.0f} sqm {ptype} building."},
            {"ID": "EXC",    "Activity": "Excavation",                 "Duration": 12, "Predecessor": "MOB",    "WBS": "2. Substructure",             "Notes": f"Excavation for RCC foundations of a {ptype} building; duration scaled to {area:.0f} sqm footprint and assumed medium soil conditions."},
            {"ID": "FTG",    "Activity": "Footing RCC",                "Duration": 10, "Predecessor": "EXC",    "WBS": "2. Substructure",             "Notes": f"RCC isolated footings for concrete-frame {ptype}; 10 days covers shuttering, reinforcement, pour, and 3-day initial curing at {area:.0f} sqm scale."},
            {"ID": "COL_F1", "Activity": "RCC Columns Floor 1",        "Duration": 8,  "Predecessor": "FTG",    "WBS": "3. Superstructure > Floor 1", "Notes": f"RCC columns are the structural system for this {ptype} project; 8 days covers shuttering, rebar, pour, and deshuttering for floor area of {area:.0f} sqm."},
            {"ID": "SLB_F1", "Activity": "RCC Slab Floor 1",           "Duration": 10, "Predecessor": "COL_F1", "WBS": "3. Superstructure > Floor 1", "Notes": f"Two-way RCC slab with beams; 10 days is standard for {area:.0f} sqm {ptype} floor allowing formwork, rebar, pour, and initial curing before striking."},
            {"ID": "FIN_F1", "Activity": "Internal Finishing Floor 1", "Duration": 20, "Predecessor": "SLB_F1", "WBS": "4. Finishing > Floor 1",      "Notes": f"Plastering, flooring, painting, and fixtures for a {ptype} building; 20 days reflects two finishing gangs working the {area:.0f} sqm floor area."},
        ]
    lines.append(json.dumps(example, indent=2))
    lines.append("")
    lines.append(f"Now generate the COMPLETE activity list for the above {ptype} project.")
    lines.append(f"CHECKLIST before outputting — verify your array:")
    lines.append(f"  ✓ Structural system is {ssys.upper()} throughout the superstructure")
    lines.append(f"  ✓ Exactly {floors} above-ground floor(s) have individual activities")
    lines.append(f"  ✓ {'No basement activities present' if basements == 0 else f'Exactly {basements} basement level(s) have individual activities'}")
    lines.append(f"  ✓ Activities reflect {ptype} building type (not generic)")
    lines.append(f"  ✓ Durations are scaled for {area:.0f} sqm ({area_band})")
    if notes.strip():
        lines.append(f"  ✓ Special requirements addressed: \"{notes.strip()[:80]}{'…' if len(notes.strip()) > 80 else ''}\"")
    lines.append(f"  ✓ Every activity has a Notes field referencing the project parameters")
    lines.append("Output ONLY the JSON array.")

    prompt = "\n".join(lines)

    if template_seed:
        prompt += "\n\n=== SEED TEMPLATE (use as reference for activity names / structure) ===\n"
        prompt += json.dumps(template_seed, indent=2)

    return prompt


def extract_json_from_text(text: str) -> Optional[str]:
    # Greedy match: find the outermost JSON array in the text
    m = re.search(r"(\[[\s\S]*\])", text)
    if m:
        return m.group(1)
    # Fallback: try to repair a truncated array by closing it
    m2 = re.search(r"(\[[\s\S]+)", text)
    if m2:
        fragment = m2.group(1).rstrip().rstrip(",")
        # Close any open object then close the array
        if not fragment.endswith("}"):
            # drop the last incomplete entry
            last_close = fragment.rfind("}")
            if last_close != -1:
                fragment = fragment[: last_close + 1]
        if not fragment.endswith("]"):
            fragment += "]"
        return fragment
    return None


def call_llm(prompt: str, model: str = "gpt-4o", temperature: float = 0.0, max_tokens: int = 4096) -> str:
    """Call OpenAI chat.completions (openai>=1.0.0 required).
    The function reads OPENAI_API_KEY from environment."""
    if openai is None:
        raise RuntimeError("openai package not installed. Install via 'pip install openai'.")
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment. Please set it before calling the AI planner.")
    if not hasattr(openai, "OpenAI"):
        raise RuntimeError("openai>=1.0.0 is required. Run: pip install --upgrade openai")

    client = openai.OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a strict JSON generator for construction activity lists."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")


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


def generate_activities(user_inputs: Dict[str, Any], max_activities: int = 50, template_seed: Optional[List[Dict]] = None, model: str = "gpt-4o", temperature: float = 0.0) -> List[Dict[str, Any]]:
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
