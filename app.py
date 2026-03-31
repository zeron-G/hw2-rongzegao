from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any

import requests
from dotenv import load_dotenv

DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "gemini": "gemini-2.0-flash",
}

PROMPT_VERSIONS = {
    "initial": dedent(
        """
        You are a helpful B2B SaaS customer support writer.
        Draft a professional email response to the customer using the provided context.
        Return valid JSON with these keys only:
        - subject
        - customer_reply
        - internal_notes
        - review_required
        - review_reason
        - confidence

        Keep the reply concise and ready for a support specialist to review.
        """
    ).strip(),
    "revision1": dedent(
        """
        You are writing a first-pass customer support reply for Northstar Analytics.
        Use only the facts provided in the ticket, account context, and policy context.
        If a detail is missing, say that follow-up or review is needed instead of inventing facts.
        Do not claim an action is already complete unless the context says it is complete.

        Return valid JSON with these keys only:
        - subject
        - customer_reply
        - internal_notes
        - review_required
        - review_reason
        - confidence

        Requirements:
        - customer_reply: 1 to 3 short paragraphs, calm and professional
        - internal_notes: a JSON array of 2 to 4 short bullet-style strings
        - review_required: true when policy, approval, privacy, security, refund exception, or legal review is needed
        - review_reason: one sentence
        - confidence: one of low, medium, high
        """
    ).strip(),
    "revision2": dedent(
        """
        You are the drafting assistant for Northstar Analytics support.
        Your job is to produce a safe first draft for a human support specialist.

        Grounding rules:
        - Use only the supplied ticket, account context, and policy context.
        - Never invent approvals, attachments, credits, refunds, completed actions, or product capabilities.
        - When the case involves refund exceptions, service credits, privacy requests, legal claims, security ownership transfer, or any approval that is still pending, set review_required to true.
        - When a feature is unavailable on the customer's plan, say so directly and offer the next valid step.
        - When verification is missing, ask for the specific verification needed.

        Writing rules:
        - Sound calm, direct, and helpful.
        - Answer the customer's main question in the first paragraph.
        - Mention the next step or expected handoff clearly.
        - Keep the reply concise enough for real support use.

        Return valid JSON only with these keys:
        - subject
        - customer_reply
        - internal_notes
        - review_required
        - review_reason
        - confidence

        Field rules:
        - subject: short support-style subject line
        - customer_reply: 1 to 3 short paragraphs
        - internal_notes: JSON array of 2 to 4 strings
        - review_required: true or false
        - review_reason: empty string if false, otherwise one concrete sentence
        - confidence: one of low, medium, high
        """
    ).strip(),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a simple multi-provider GenAI customer support drafting workflow."
    )
    parser.add_argument(
        "--provider",
        choices=sorted(DEFAULT_MODELS.keys()),
        default="openai",
        help="LLM provider to use.",
    )
    parser.add_argument(
        "--model",
        help="Override the default model for the selected provider.",
    )
    parser.add_argument(
        "--prompt-version",
        choices=sorted(PROMPT_VERSIONS.keys()),
        default="revision2",
        help="Prompt version to run.",
    )
    parser.add_argument(
        "--case-id",
        default="all",
        help="Case ID from eval_set.json, or 'all'.",
    )
    parser.add_argument(
        "--eval-set",
        default="eval_set.json",
        help="Path to the evaluation set JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory where JSON run outputs are saved.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=700,
        help="Maximum response tokens.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="List available case IDs and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build prompts and validate inputs without calling an API.",
    )
    return parser.parse_args()


def load_eval_set(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Evaluation set not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def select_cases(eval_data: dict[str, Any], case_id: str) -> list[dict[str, Any]]:
    cases = eval_data.get("cases", [])
    if case_id == "all":
        return cases
    for case in cases:
        if case["id"] == case_id:
            return [case]
    available = ", ".join(case["id"] for case in cases)
    raise ValueError(f"Unknown case_id '{case_id}'. Available cases: {available}")


def build_user_prompt(case: dict[str, Any]) -> str:
    return dedent(
        f"""
        Customer message:
        {case["customer_message"]}

        Account context:
        {case["account_context"]}

        Policy context:
        {case["policy_context"]}
        """
    ).strip()


def ensure_env_key(provider: str) -> str:
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment.")
        return key
    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN") or ""
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is missing from the environment."
            )
        return key
    if provider == "gemini":
        key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
            or ""
        )
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY, GOOGLE_API_KEY, or GOOGLE_GENERATIVE_AI_API_KEY is missing from the environment."
            )
        return key
    raise ValueError(f"Unsupported provider: {provider}")


def post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int = 120,
) -> dict[str, Any]:
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"API request failed with status {response.status_code}: {response.text}"
        ) from exc
    return response.json()


def call_openai(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    api_key = ensure_env_key("openai")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = post_json(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    return data["choices"][0]["message"]["content"]


def call_anthropic(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    api_key = ensure_env_key("anthropic")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    data = post_json(
        f"{base_url}/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        payload=payload,
    )
    return "".join(block["text"] for block in data["content"] if block["type"] == "text")


def call_gemini(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    api_key = ensure_env_key("gemini")
    base_url = os.getenv(
        "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    data = post_json(
        f"{base_url}/models/{model}:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        payload=payload,
    )
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(part.get("text", "") for part in parts)


def call_model(
    provider: str,
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    if provider == "openai":
        return call_openai(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "anthropic":
        return call_anthropic(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "gemini":
        return call_gemini(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unsupported provider: {provider}")


def extract_json(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def build_search_text(parsed_output: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("subject", "customer_reply", "review_reason", "confidence"):
        value = parsed_output.get(key)
        if isinstance(value, str):
            chunks.append(value)
    notes = parsed_output.get("internal_notes", [])
    if isinstance(notes, list):
        chunks.extend(str(note) for note in notes)
    return " ".join(chunks).lower()


def evaluate_case(case: dict[str, Any], parsed_output: dict[str, Any]) -> dict[str, Any]:
    rules = case.get("heuristic_rules", {})
    required_keywords = rules.get("required_keywords", [])
    forbidden_keywords = rules.get("forbidden_keywords", [])
    search_text = build_search_text(parsed_output)

    required_results = {
        keyword: keyword.lower() in search_text for keyword in required_keywords
    }
    forbidden_results = {
        keyword: keyword.lower() not in search_text for keyword in forbidden_keywords
    }
    review_matches = (
        normalize_bool(parsed_output.get("review_required"))
        == case["expected_review_required"]
    )

    checks_passed = sum(required_results.values()) + sum(forbidden_results.values())
    if review_matches:
        checks_passed += 1
    total_checks = len(required_results) + len(forbidden_results) + 1

    return {
        "expected_review_required": case["expected_review_required"],
        "actual_review_required": normalize_bool(parsed_output.get("review_required")),
        "review_matches_expectation": review_matches,
        "required_keyword_results": required_results,
        "forbidden_keyword_results": forbidden_results,
        "heuristic_score": f"{checks_passed}/{total_checks}",
    }


def run_case(
    *,
    provider: str,
    model: str,
    prompt_version: str,
    case: dict[str, Any],
    temperature: float,
    max_tokens: int,
    dry_run: bool,
) -> dict[str, Any]:
    system_prompt = PROMPT_VERSIONS[prompt_version]
    user_prompt = build_user_prompt(case)

    if dry_run:
        raw_text = json.dumps(
            {
                "subject": "DRY RUN",
                "customer_reply": "No API call was made.",
                "internal_notes": ["Prompt and case loaded successfully."],
                "review_required": False,
                "review_reason": "",
                "confidence": "high",
            },
            indent=2,
        )
    else:
        raw_text = call_model(
            provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    parsed_output = extract_json(raw_text)
    evaluation = evaluate_case(case, parsed_output)
    return {
        "case_id": case["id"],
        "label": case["label"],
        "case_type": case["case_type"],
        "good_output_should": case["good_output_should"],
        "raw_response": raw_text,
        "parsed_output": parsed_output,
        "evaluation": evaluation,
    }


def save_run(output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_name = (
        f"{timestamp}_{payload['provider']}_{payload['model'].replace('/', '-')}"
        f"_{payload['prompt_version']}.json"
    )
    output_path = output_dir / file_name
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    load_dotenv()
    args = parse_args()
    eval_path = Path(args.eval_set)
    eval_data = load_eval_set(eval_path)

    if args.list_cases:
        for case in eval_data.get("cases", []):
            print(f"{case['id']}: {case['label']} ({case['case_type']})")
        return

    cases = select_cases(eval_data, args.case_id)
    provider = args.provider
    model = args.model or DEFAULT_MODELS[provider]
    results = []

    for case in cases:
        result = run_case(
            provider=provider,
            model=model,
            prompt_version=args.prompt_version,
            case=case,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            dry_run=args.dry_run,
        )
        results.append(result)
        score = result["evaluation"]["heuristic_score"]
        review = result["evaluation"]["actual_review_required"]
        print(f"{case['id']}: score={score}, review_required={review}")

    payload = {
        "run_timestamp": datetime.now().isoformat(timespec="seconds"),
        "provider": provider,
        "model": model,
        "prompt_version": args.prompt_version,
        "dry_run": args.dry_run,
        "workflow": eval_data.get("workflow"),
        "cases_run": [case["id"] for case in cases],
        "results": results,
    }
    output_path = save_run(Path(args.output_dir), payload)
    print(f"Saved run output to: {output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
