import os
from dataclasses import dataclass

from vwait.core.paths import global_log_sequence_paths


@dataclass(frozen=True)
class ChatPageConfig:
    project_root: str
    base_dir: str
    data_root: str
    run_script: str
    collector_script: str
    process_script: str
    pause_flag_path: str
    global_log_sequence_category: str
    global_log_sequence_test: str
    global_log_sequence_csv: str
    global_log_sequence_raw_json: str
    global_log_sequence_meta_json: str
    conversation_mode: bool
    adb_path: str
    ollama_url: str
    ollama_model: str
    ollama_cli: str
    ollama_num_predict: int
    ollama_temperature: float
    ollama_top_p: float
    ollama_num_ctx: int
    ollama_keep_alive: str


def load_chat_page_config(*, project_root_fn, root_path_fn, resolve_adb_path_fn) -> ChatPageConfig:
    project_root = project_root_fn()
    data_root = root_path_fn("Data")
    global_csv, global_raw, global_meta = global_log_sequence_paths()
    return ChatPageConfig(
        project_root=project_root,
        base_dir=project_root,
        data_root=data_root,
        run_script=root_path_fn("src", "vwait", "entrypoints", "cli", "run_test.py"),
        collector_script=root_path_fn("src", "vwait", "entrypoints", "cli", "coletor_adb.py"),
        process_script=root_path_fn("src", "vwait", "entrypoints", "cli", "processar_dataset.py"),
        pause_flag_path=os.path.join(project_root, "pause.flag"),
        global_log_sequence_category="__system__",
        global_log_sequence_test="failure_log_sequence_global",
        global_log_sequence_csv=str(global_csv),
        global_log_sequence_raw_json=str(global_raw),
        global_log_sequence_meta_json=str(global_meta),
        conversation_mode=True,
        adb_path=resolve_adb_path_fn(),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:3b"),
        ollama_cli=os.getenv("OLLAMA_CLI", "ollama"),
        ollama_num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", "40")),
        ollama_temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.2")),
        ollama_top_p=float(os.getenv("OLLAMA_TOP_P", "0.9")),
        ollama_num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "256")),
        ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "10m"),
    )
