import os
import sys
import json
import argparse
from typing import Any, Dict, List
from unittest import result

from openai import OpenAI
from dotenv import load_dotenv

# Try LaTeX → text conversion (CLI-friendly)
try:
    from pylatexenc.latex2text import LatexNodes2Text
    def latex_to_text(s: str) -> str:
        return LatexNodes2Text().latex_to_text(s)
except Exception:
    def latex_to_text(s: str) -> str:
        return s



SYSTEM_PROMPT = """You are a Math Olympiad Study Assistant.
Solve the problem, verify internally, then output ONLY valid JSON with keys:
final_answer, solution_steps, chapter_tag, concepts, thinking_style, difficulty, confidence, quality_checks, suggested_practice.
- Use LaTeX for any math expressions inside solution_steps and final_answer when helpful.
- No markdown fences. No extra text.
"""
DEFAULT_MODEL = "gpt-5"
GEMINI_COMPAT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"

def infer_base_url(model: str) -> str | None:
    """
    Auto-select base_url from model name unless LLM_BASE_URL is set.
    - gemini* -> Google OpenAI-compatible endpoint
    - otherwise -> default (OpenAI)
    """
    forced = os.getenv("LLM_BASE_URL", "").strip() or None
    if forced:
        return forced
    m = (model or "").lower().strip()
    if m.startswith("gemini"):
        return GEMINI_COMPAT_BASE
    return None  # OpenAI default

def make_client_and_model(cli_model: str | None):
    load_dotenv()
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("Missing LLM_API_KEY in environment (.env).")

    model = (cli_model or os.getenv("LLM_MODEL") or DEFAULT_MODEL).strip()
    base_url = infer_base_url(model)

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    return client, model

def ensure_list(field):
    if isinstance(field, list):
        return [str(x).strip() for x in field if str(x).strip()]
    if isinstance(field, str):
        return [field.strip()]
    return []

def repair_json(s: str) -> str:
    """Light fix if JSON comes back with code fences."""
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("\n") + 1:] if "\n" in s else s
    start = s.find("{")
    end = s.rfind("}")
    return s[start:end+1] if start != -1 and end != -1 else s

def solve(problem_text: str, client, model: str) -> Dict[str, Any]:
    """Send problem to GPT and return structured JSON."""
    msg = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": problem_text},
    ]
    print(f"Calling GPT {model}...")
    resp = client.chat.completions.create(
        model=model,
        messages=msg,
        # GPT-5 appears to default to temperature=1, don’t override
        response_format={"type": "json_object"},
    )

    # --- extract token usage
    usage = resp.usage
    prompt_tokens = usage.prompt_tokens
    completion_tokens = usage.completion_tokens
    total_tokens = usage.total_tokens

    print(f"\n--- Token Usage ---")
    print(f"Prompt tokens:     {prompt_tokens}")
    print(f"Completion tokens: {completion_tokens}")
    print(f"Total tokens:      {total_tokens}")
    
    raw = resp.choices[0].message.content
    #print(json.dumps(json.loads(raw), indent=2))  # Debug: show raw response
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(repair_json(raw))

def pretty_print(result: Dict[str, Any], show_latex_raw: bool = False):
    # Extract fields
    final_answer = result.get("final_answer", "")
    steps = result.get("solution_steps", "")
    chapter = result.get("chapter_tag", "")
    concepts = ensure_list(result.get("concepts", []))
    thinking = ensure_list(result.get("thinking_style", []))
    difficulty = result.get("difficulty", "")
    confidence = result.get("confidence", "")
    qchecks = result.get("quality_checks", [])
    practice = result.get("suggested_practice", [])

    # LaTeX → text if desired
    if not show_latex_raw:
        final_answer = latex_to_text(str(final_answer))

        if isinstance(steps, str):
            steps = [latex_to_text(line) for line in steps.split("\n") if line.strip()]
        elif isinstance(steps, list):
            steps = [latex_to_text(str(s)) for s in steps if str(s).strip()]
        else:
            steps = []

    # Print output
    print("\n=== FINAL ANSWER ===")
    print(final_answer if final_answer else "(none)")

    print("\n=== SOLUTION STEPS ===")
    if steps:
        for i, step in enumerate(steps, 1):
            print(f"{i}. {step}")
    else:
        print("(none)")

    print("\n=== CLASSIFICATION ===")
    print("Chapter:", chapter or "(none)")
    print("Concepts:", ", ".join(concepts) if concepts else "(none)")
    print("Thinking:", ", ".join(thinking) if thinking else "(none)")
    print("Difficulty:", difficulty if difficulty else "(none)")
    print("Confidence:", confidence if confidence else "(none)")

    print("\n=== QUALITY CHECKS ===")
    if qchecks:
        if isinstance(qchecks, str):
            print("-", qchecks)
        else:
            for bullet in qchecks:
                print("-", bullet)
    else:
        print("(none)")

    print("\n=== SUGGESTED PRACTICE ===")
    if practice:
        if isinstance(practice, str):
            print("-", practice)
        else:
            for s in practice:
                print("-", s)
    else:
        print("(none)")

def main():
    parser = argparse.ArgumentParser(description="Math Olympiad CLI Agent")
    parser.add_argument("--latex-raw", action="store_true",
                        help="Print raw LaTeX instead of converting to plaintext.")
    parser.add_argument("--file", type=str, default=None,
                        help="Read problem from a file instead of stdin.")
    parser.add_argument("--model", type=str, default=None,
                        help=f"Override model (default from .env)")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            problem = f.read().strip()
    else:
        if sys.stdin.isatty():
            print("Paste a single problem, then Ctrl-D (Linux/macOS) or Ctrl-Z Enter (Windows):")
        problem = sys.stdin.read().strip()

    if not problem:
        print("No problem provided. Exiting.")
        sys.exit(1)

    client, model = make_client_and_model(args.model)

    result = solve(problem_text=problem, client=client, model=model)
    pretty_print(result, show_latex_raw=args.latex_raw)

if __name__ == "__main__":
    main()
