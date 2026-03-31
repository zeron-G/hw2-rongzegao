# hw2-rongzegao

Week 2 assignment repository for BU.330.760: Build and Evaluate a Simple GenAI Workflow.

## Business Workflow

I built a first-pass customer support drafting workflow for a fictional B2B SaaS company called Northstar Analytics.

- Workflow: drafting customer support email replies
- User: support specialist
- Input: customer message, account context, and policy context
- Output: a structured draft reply, internal notes, and a human-review flag
- Value: repetitive writing can be accelerated, but risky cases still need a human gate

## Repository Contents

```text
hw2-rongzegao/
|- README.md
|- app.py
|- prompts.md
|- eval_set.json
|- report.md
|- requirements.txt
|- .env.example
`- results/
```

## Model Support

The CLI supports three provider families:

- OpenAI (`gpt-*`)
- Anthropic / Claude (`claude-*`)
- Gemini (`gemini-*`)

The current local environment only had a working OpenAI key, so live evaluation was completed with `gpt-4.1-mini`. Claude and Gemini support are implemented in the code and validated through configuration plus error handling, but not live-benchmarked in this repository because those keys were unavailable locally on March 31, 2026.

## Setup

1. Create a virtual environment:

   ```powershell
   E:\codesupport\anaconda\python.exe -m venv .venv
   ```

2. Install dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Create a `.env` file from `.env.example` and fill in at least one provider key.

## Usage

List the evaluation cases:

```powershell
.\.venv\Scripts\python.exe app.py --list-cases
```

Run one case with the final prompt:

```powershell
.\.venv\Scripts\python.exe app.py --provider openai --prompt-version revision2 --case-id case_03
```

Run the full evaluation set:

```powershell
.\.venv\Scripts\python.exe app.py --provider openai --prompt-version revision2 --case-id all
```

Dry-run without making an API call:

```powershell
.\.venv\Scripts\python.exe app.py --provider gemini --prompt-version revision2 --case-id case_01 --dry-run
```

## Evaluation Summary

Stable evaluation set size: 6 cases.

- Initial prompt: `26/30`
- Revision 1: `30/30`
- Revision 2: `30/30`

The baseline prompt was readable but too generic. The revised prompts improved policy grounding, review flagging, and the clarity of risky-case handoffs. Full JSON outputs are saved in the [`results/`](results) folder.

## Local Testing

Completed locally on March 31, 2026:

- `python -m py_compile app.py`
- `app.py --list-cases`
- `app.py --provider openai --prompt-version revision2 --case-id case_01 --dry-run`
- `app.py --provider openai --prompt-version initial --case-id all`
- `app.py --provider openai --prompt-version revision1 --case-id all`
- `app.py --provider openai --prompt-version revision2 --case-id all`
- `app.py --provider anthropic --case-id case_01` to confirm the missing-key error path
- `app.py --provider gemini --case-id case_01` to confirm the missing-key error path

## Video Link

TODO: replace this line with the unlisted YouTube or Vimeo walkthrough link after recording the video.
