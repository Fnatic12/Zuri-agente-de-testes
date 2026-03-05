# Visual QA Architecture (Scaffolding)

This document describes the modular scaffolding for a new `visual_qa` layer using Clean Architecture.

## Goals

- Keep current pixel validator untouched.
- Introduce explicit contracts for Stage 1 (similarity), Stage 2 (pixel compare adapter), and Stage 3 (report generation).
- Enable incremental implementation with dependency inversion and testable boundaries.

## Package Layout

```text
visual_qa/
  domain/
    scaffold_entities.py
  application/
    dtos.py
    ports/
      protocols.py
  infrastructure/
    ... concrete adapters live here
  interfaces/
    cli/
      ... CLI entrypoints live here
```

## Layer Responsibilities

### 1) Domain (`visual_qa.domain`)

Contains core, framework-agnostic entities:

- `ScreenMatch`: Stage 1 classification output.
- `PixelDiffResult`: normalized Stage 2 output.
- `ValidationRun`: aggregate of a full execution.
- `Report`: persisted report artifact paths.

These are dataclasses with no infrastructure dependencies.

### 2) Application (`visual_qa.application`)

Defines orchestration contracts and DTOs:

- `application/ports/protocols.py`:
  - `EmbeddingProvider`
  - `VectorIndexRepository`
  - `PixelComparator`
  - `ReportGenerator`
  - `ArtifactStore`
- `application/dtos.py`:
  - request/response contracts for build/classify/validate flows.

Application code should depend only on domain entities and port Protocols.

### 3) Infrastructure (`visual_qa.infrastructure`)

Hosts concrete implementations (FAISS, CLIP, existing pixel validator adapter, LLM adapters, local storage).

Rules:
- Infrastructure imports from `application.ports.protocols` and `domain`.
- Domain/Application must not import concrete infrastructure.

### 4) Interfaces (`visual_qa.interfaces`)

Entry points such as CLI should call application use cases and assemble concrete dependencies.

## Dependency Direction

```text
interfaces -> application -> domain
infrastructure -> application -> domain
```

No upward dependency is allowed from `domain` to any other layer.

## Incremental Integration Plan

1. Implement use cases that consume the new Protocol ports.
2. Add concrete adapters in `infrastructure` for embeddings/index/reporting.
3. Wrap the existing pixel validator with `PixelComparator` only (no code changes in validator).
4. Wire CLI commands to use cases.
