# Text Extract Pipeline

A simple pipeline that reads PDFs, extracts text, uses an LLM (OpenAI or Gemini) to infer a schema and produce records, and writes a local Excel file per input PDF.

## Prerequisites
- Git (Windows: install from `https://git-scm.com`; macOS: `xcode-select --install` or `brew install git`; Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y git`)
- Python 3.9+ with pip (Windows: install from `https://www.python.org/downloads/` and check "Add Python to PATH"; macOS: `brew install python`; Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv`)
- Optional: `python-dotenv` for automatic `.env` loading (the app still reads `.env` without it)

## Clone From GitHub
```bash
git clone https://github.com/shopnil13/Lead_Generation.git
cd TEXT_EXTRACT
```

## Quick Start
1. Clone the repo (see "Clone From GitHub").
2. Create a virtual environment and install dependencies (see "Local Setup (Detailed)").
3. Set environment variables (see `.env.example`).
4. Put PDFs in `input/`.
5. Run `python -m src.main`.

## Local Setup (Detailed)
1. Create a virtual environment.
```powershell
py -m venv .venv
```
```bash
python3 -m venv .venv
```
2. Activate the virtual environment.
```powershell
.venv\Scripts\Activate.ps1
```
For linux:
```bash
source .venv/bin/activate
```
3. Install dependencies.
```bash
pip install -r requirements.txt
```
4. Optional: install `python-dotenv` if you want automatic `.env` loading.
```bash
pip install python-dotenv
```
5. Create your local `.env`.
```powershell
Copy-Item .env.example .env
```
```bash
cp .env.example .env
```
6. Put PDFs into `input/`.
7. Run the pipeline.
```bash
python -m src.main
```

## Environment Variables
Required:
- `LLM_PROVIDER` = `openai` or `gemini`

OpenAI (if `LLM_PROVIDER=openai`):
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (example: `gpt-4.1-mini`)
- `OPENAI_API_BASE` (optional, default `https://api.openai.com/v1`)

Gemini (if `LLM_PROVIDER=gemini`):
- `GEMINI_API_KEY`
- `GEMINI_MODEL` (example: `gemini-2.5-flash`)
- `GEMINI_API_BASE` (optional, default `https://generativelanguage.googleapis.com/v1beta`)

Optional:
- `LLM_TEMPERATURE` (default `0`)
- `LLM_REQUEST_TIMEOUT` (seconds, default `120`)
- `LLM_RETRIES` (default `2`)
- `LLM_RETRY_BACKOFF` (default `1.5`)
- `MAX_PAGES` (limit pages per PDF)
- `MAX_CHARS_PER_CHUNK` (split long PDFs by character count)
- `CHUNK_PAGES` (process N pages per request; overrides `MAX_CHARS_PER_CHUNK` if set)
- `CACHE_RESET` (set to `true` to clear cached chunks before processing)

## Schema Behavior
- The LLM infers a schema per PDF and returns `{ schema: [...], records: [...] }`.
- One field is always enforced: `record_index`.
- The field `document_name` is dropped if the model returns it.

## Output
- JSON saved to `output/{pdf_name}.json`
- Excel saved to `output/{pdf_name}.xlsx`

## Notes
- Prompts live in `src/config.py`.
- If the model returns invalid JSON, the pipeline automatically attempts a JSON-repair pass.
- Chunk results are cached in `cache/{pdf_name}/chunk_{n}.json` to allow resume.

## Run
```bash
python -m src.main
```
"# Lead_Generation" 
