# Visual QA on Windows

This folder contains ready-to-run wrappers for the new Visual QA pipeline.

## Scripts

- `visual_qa_build_index.bat`
- `visual_qa_classify.bat`
- `visual_qa_validate.bat`

## Usage

From repo root or by double-click (with terminal open):

```bat
Scripts\windows\visual_qa_build_index.bat
Scripts\windows\visual_qa_classify.bat C:\path\to\screenshot.png
Scripts\windows\visual_qa_validate.bat C:\path\to\screenshot.png
```

Each script automatically uses `.venv\Scripts\python.exe` if available.
