# Zuri - Visual QA Pipeline Add-on

This project now includes a modular `Screen Similarity + LLM Report` layer under `visual_qa/`.

## New Pipeline (3 stages)

1. Stage 1: image embedding + vector search classification
2. Stage 2: existing pixel validator (adapter, unchanged core logic)
3. Stage 3: report generation (Ollama or offline template)

## CLI Commands

Use module entrypoints:

```bash
python -m visual_qa.interfaces.cli.build_index_cli --reference-dir reference_images --index-dir artifacts/vector_index --recursive --labels-json labels.json
python -m visual_qa.interfaces.cli.classify_cli --image path/to/screenshot.png --index-dir artifacts/vector_index --top-k 5 --threshold 0.35 --strategy best
python -m visual_qa.interfaces.cli.validate_cli --image path/to/screenshot.png --index-dir artifacts/vector_index --top-k 5 --threshold 0.35 --strategy vote --runs-dir runs --no-llm
```

Or app CLI wrappers:

```bash
python -m app.cli.build_index --reference-dir reference_images --index-dir artifacts/vector_index --recursive
python -m app.cli.classify --image path/to/screenshot.png --index-dir artifacts/vector_index --strategy best
python -m app.cli.validate --image path/to/screenshot.png --index-dir artifacts/vector_index --strategy vote --runs-dir runs --no-llm
```

Top-level convenience entrypoint:

```bash
python -m app.cli.visual_qa build-index --reference-dir reference_images --index-dir artifacts/vector_index --recursive
python -m app.cli.visual_qa classify --image path/to/screenshot.png --index-dir artifacts/vector_index --top-k 5 --threshold 0.35 --strategy best
python -m app.cli.visual_qa validate --image path/to/screenshot.png --index-dir artifacts/vector_index --top-k 5 --threshold 0.35 --strategy vote --runs-dir runs --no-llm
```

## Environment Variables

- `VISUAL_QA_CONFIG_PATH` (optional JSON config)
- `VISUAL_QA_REFERENCE_DIR`
- `VISUAL_QA_INDEX_DIR`
- `VISUAL_QA_RUNS_DIR`
- `VISUAL_QA_TOP_K`
- `VISUAL_QA_CLASSIFICATION_THRESHOLD`
- `VISUAL_QA_EMBEDDING_PROVIDER` (`auto|mobileclip|openclip|local`)
- `VISUAL_QA_MOBILECLIP_MODEL`
- `VISUAL_QA_OPENCLIP_MODEL`
- `VISUAL_QA_OPENCLIP_PRETRAINED`
- `VISUAL_QA_USE_FAISS` (`true|false`)
- `VISUAL_QA_REPORT_MODE` (`null|ollama`)
- `VISUAL_QA_OLLAMA_BASE_URL`
- `VISUAL_QA_OLLAMA_MODEL`
- `VISUAL_QA_OLLAMA_TIMEOUT_S`

## Jira Integration

The project also includes a reusable Jira integration layer for panel-driven issue creation.

- Setup guide: [JIRA_INTEGRATION.md](/home/victor-milani/vwait-ia/vwait/docs/JIRA_INTEGRATION.md)
- Failure reports guide: [FAILURES_REPORTING.md](/home/victor-milani/vwait-ia/vwait/docs/FAILURES_REPORTING.md)
- Example env file: [.env.jira.example](/home/victor-milani/vwait-ia/vwait/.env.jira.example)

## Artifacts

Each run is stored under:

- `runs/<run_id>/result.json`
- `runs/<run_id>/report.md`
- `runs/<run_id>/logs.jsonl`
- `runs/<run_id>/pixel_artifacts/*` (if produced by existing validator)
- `runs/index.jsonl` (historical index)

## Visual QA Pipeline (Embeddings + Pixel Diff + LLM Report)

### Prerequisites

- Python 3.10+ (recommended: use project `.venv`)
- Baseline/reference images (PNG/JPG) for Stage 1 indexing
- Existing pixel validator dependencies available in this repo
- Optional for LLM report: local Ollama server running

### Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/visual_qa.txt
```

### Commands

Build vector index:

```bash
python -m visual_qa.interfaces.cli.build_index_cli \
  --reference-dir reference_images \
  --index-dir artifacts/vector_index \
  --recursive \
  --labels-json labels.json
```

Classify one screenshot:

```bash
python -m visual_qa.interfaces.cli.classify_cli \
  --image path/to/screenshot.png \
  --index-dir artifacts/vector_index \
  --top-k 5 \
  --threshold 0.35 \
  --strategy best
```

Run full pipeline (classify + pixel compare + report):

```bash
python -m visual_qa.interfaces.cli.validate_cli \
  --image path/to/screenshot.png \
  --index-dir artifacts/vector_index \
  --top-k 5 \
  --threshold 0.35 \
  --strategy vote \
  --runs-dir runs
```

Disable LLM report generation (offline deterministic report):

```bash
python -m visual_qa.interfaces.cli.validate_cli \
  --image path/to/screenshot.png \
  --index-dir artifacts/vector_index \
  --no-llm
```

### Environment Variables

- `OLLAMA_BASE_URL` (default: `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` (default: `llama3`)
- `VISUAL_QA_OLLAMA_BASE_URL`
- `VISUAL_QA_OLLAMA_MODEL`
- `VISUAL_QA_OLLAMA_TIMEOUT_S`
- `VISUAL_QA_REPORT_MODE` (`null|ollama`)
- `VISUAL_QA_EMBEDDING_PROVIDER` (`auto|mobileclip|openclip|local`)
- `VISUAL_QA_REFERENCE_DIR`
- `VISUAL_QA_INDEX_DIR`
- `VISUAL_QA_RUNS_DIR`
- `VISUAL_QA_TOP_K`
- `VISUAL_QA_CLASSIFICATION_THRESHOLD`

### Output Structure (`runs/`)

```text
runs/
  index.jsonl
  logs.jsonl
  <run_id>/
    run_result.json
    report.md
    diff_images/              # optional copied/referenced diff images
    pixel_artifacts/          # optional legacy pixel outputs (if generated)
    logs.jsonl                # per-run structured logs
```
