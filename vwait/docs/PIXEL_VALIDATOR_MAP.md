# PIXEL VALIDATOR MAP

## 1) Current entrypoints/scripts used to run pixel-to-pixel validation

### Legacy/Current project flow
- `Run/run_noia.py`
  - Main execution runner that performs action-by-action screenshot comparison against expected frames.
  - Typically called from:
    - `app/cli/main.py` (menu option "Executar testes")
    - `app/streamlit/menu_tester.py` (buttons "Executar Teste Unico" / "Executar Todos da Categoria")
    - `app/streamlit/menu_chat.py` (command interpreter for `executar ...`)
- `HMI/validacao_hmi.py`
  - Streamlit UI entrypoint for HMI visual validation (loads references and validates execution screenshots).
  - Called from `app/streamlit/menu_chat.py` page "Validação HMI".
- `Dashboard/diff_tool.py`
  - Direct CLI utility for pairwise image diff using `Dashboard/diff_engine.py`.

### New wrapper entrypoints (added layer, still reusing existing pixel engine)
- `app/cli/validate.py` -> `visual_qa/interfaces/cli/validate_cli.py`
  - Runs Stage 1 classification + Stage 2 pixel compare adapter + Stage 3 report.
  - Stage 2 calls existing validator code (no replacement of core comparator).

## 2) Function/class that performs pixel comparison and its inputs/outputs

### A) Execution runner comparator (legacy action-by-action)
- Function: `Run/run_noia.py::comparar_imagens(img1_path, img2_path)`
- Inputs:
  - `img1_path` (actual screenshot path)
  - `img2_path` (expected frame path)
- Output:
  - `float` SSIM score (0.0 to 1.0)
- Usage:
  - Compared per action inside `run_noia.py`, then logged in `execucao_log.json` with status OK/divergent.

### B) HMI visual comparator (rich pixel validation)
- Main API: `HMI/hmi_engine.py::validate_execution_images(screenshot_paths, library_index, cfg)`
- Internal per-image function: `evaluate_single_screenshot(...)`
- Pixel diff kernel used inside HMI engine:
  - `Dashboard/diff_engine.py::compare_images(imgA, imgB, config)`
- Inputs:
  - `screenshot_paths`: list of actual images
  - `library_index`: indexed reference screens metadata (from `HMI/hmi_indexer.py::build_library_index`)
  - `cfg`: `ValidationConfig`
- Outputs:
  - Dict with:
    - `summary` (pass/fail counts, average scores)
    - `items[]` per screenshot containing:
      - selected reference (`reference_path`, `screen_id`, `screen_name`)
      - scores (`global`, `pixel`, `grid`, `edge`, etc.)
      - `diff_summary` (area ratio, changed pixels, etc.)
      - issues (`toggle_changes`, `critical_region_failures`)
      - `debug_images` (`overlay`, `diff_mask`, `heatmap`, `aligned`)

### C) Adapter currently used by pipeline layer
- Class: `visual_qa/infrastructure/pixel_compare/existing_pixel_comparator_adapter.py::ExistingPixelComparatorAdapter`
- It calls existing code unchanged:
  - Builds temporary one-image reference index with `build_library_index(...)`
  - Calls `validate_execution_images(..., ValidationConfig(stage1_enabled=False))`
- Output normalized to DTO `PixelDiffResult`.

## 3) Where baseline images live and how they are selected today

### A) Test execution baseline (legacy)
- Baselines live at:
  - `Data/<categoria>/<teste>/frames/frame_XX.png`
- Selection strategy:
  - Sequential mapping by action index (`resultado_XX.png` vs `frame_XX.png`) in `run_noia.py`.

### B) HMI baseline (library matching)
- Baselines live in a user-selected local reference folder (Figma exports), indexed by:
  - `HMI/hmi_indexer.py::build_library_index(figma_dir, ...)`
- Selection strategy:
  - Candidate ranking inside `evaluate_single_screenshot(...)` and best result selection by status priority + score.

### C) Pipeline wrapper baseline
- Baseline selected from Stage 1 top match (`selected_baseline_image`) from vector index metadata.
- Stage 2 compares actual image vs that baseline via existing HMI validator API.

## 4) Current output artifacts (JSON, diff images, logs)

### Legacy execution flow (`run_noia.py`)
- `Data/<categoria>/<teste>/execucao_log.json`
- `Data/<categoria>/<teste>/resultados/resultado_XX.png`
- `Data/<categoria>/<teste>/resultado_final.png`
- `Data/<categoria>/<teste>/status_<serial>.json`

### HMI validation flow
- `Data/<categoria>/<teste>/hmi_validation/resultado_hmi.json`
- `Data/<categoria>/<teste>/hmi_validation/overlays/*`
- `Data/<categoria>/<teste>/hmi_validation/diff_masks/*`
- `Data/<categoria>/<teste>/hmi_validation/heatmaps/*`
- `Data/<categoria>/<teste>/hmi_validation/aligned/*`

### Direct diff utility
- `Dashboard/diff_tool.py` outputs:
  - `<out>/diff_mask.png`
  - `<out>/overlay.png`

### Pipeline wrapper outputs (`visual_qa`)
- `runs/<run_id>/result.json`
- `runs/<run_id>/report.md`
- `runs/<run_id>/logs.jsonl`
- `runs/<run_id>/pixel_artifacts/*` (when produced)
- `runs/index.jsonl` (historical index)

## 5) Minimal integration point(s) to call existing pixel validator WITHOUT changing its code

### Recommended minimal integration point (already implemented and safe)
- Use `HMI/hmi_engine.py::validate_execution_images(...)` as the stable existing API.
- Build a temporary one-baseline index using `HMI/hmi_indexer.py::build_library_index(...)`.
- Execute validation with `ValidationConfig(stage1_enabled=False)` to keep pure pixel-level behavior in Stage 2.
- Map result dict into your pipeline DTO/contract externally (adapter layer only).

### Why this is minimal and safe
- No change required in existing comparator internals (`compare_images`, `evaluate_single_screenshot`, `validate_execution_images`).
- Reuses existing output semantics (scores, issues, debug images).
- Keeps backward compatibility with current HMI and dashboard flows.

