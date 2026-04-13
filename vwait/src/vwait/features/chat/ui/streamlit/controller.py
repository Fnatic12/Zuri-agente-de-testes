from dataclasses import dataclass


@dataclass
class ChatController:
    session_state: object
    conversation_mode: bool
    adb_path: str
    data_root: str
    base_dir: str
    run_script: str
    process_script: str
    status_lock: object
    global_log_sequence_category: str
    global_log_sequence_test: str
    global_log_sequence_csv: str
    pause_flag_path: str
    ollama_url: str
    ollama_model: str
    ollama_keep_alive: str
    ollama_num_predict: int
    ollama_temperature: float
    ollama_top_p: float
    ollama_num_ctx: int
    requests_module: object
    resolve_ollama_cli_fn: object
    rerun_fn: object
    normalize_post_speech_fn: object
    process_voice_command_fn: object
    parse_adb_devices_fn: object
    list_benches_fn: object
    subprocess_windowless_kwargs_fn: object
    format_benches_fn: object
    replace_number_words_fn: object
    normalize_token_fn: object
    norm_fn: object
    has_any_fn: object
    resolve_test_fn: object
    select_bench_fn: object
    popen_host_python_fn: object
    read_serial_status_fn: object
    capture_radio_logs_for_test_fn: object
    capture_radio_log_command_fn: object
    update_bench_status_fn: object
    ollama_generate_fn: object
    llm_command_fn: object
    llm_chat_response_fn: object
    resolve_command_with_llm_or_fallback_fn: object
    append_execution_log_fn: object
    ensure_chat_execution_dataset_fn: object
    start_execution_on_serial_fn: object
    execute_test_fn: object
    extract_bench_fn: object
    extract_test_token_fn: object
    extract_category_fn: object
    list_categories_impl_fn: object
    list_tests_impl_fn: object
    resolve_execution_from_chunk_fn: object
    extract_parallel_executions_fn: object
    execute_parallel_tests_fn: object
    resolve_navigation_command_fn: object
    select_page_fn: object
    open_menu_tester_fn: object
    dashboard_page: str
    logs_page: str
    failures_page: str
    hmi_page: str
    brain_page: str
    chat_page: str
    continue_recording_flow_fn: object
    respond_conversational_fn: object
    record_global_log_sequence_fn: object
    record_test_fn: object
    start_recording_flow_fn: object
    process_test_fn: object
    delete_test_fn: object
    finalize_log_sequence_fn: object
    pause_execution_fn: object
    resume_execution_fn: object
    stop_execution_fn: object
    is_log_sequence_command_fn: object
    execute_keywords: object
    record_keywords: object
    process_keywords: object
    delete_keywords: object
    list_keywords: object
    help_keywords: object
    interpret_command_fn: object

    def process_voice_command(self, command_text: str) -> None:
        self.process_voice_command_fn(
            command_text,
            normalize_post_speech=self.normalize_post_speech_fn,
            pending_recording=self.session_state.pending_gravacao,
            continue_recording_flow=self.continue_recording_flow_fn,
            conversation_mode=self.conversation_mode,
            conversational_responder=self.respond_conversational,
            command_resolver=self.resolve_command_with_llm_or_fallback,
            chat_history=self.session_state.chat_history,
        )

    def parse_adb_devices(self, raw_lines):
        return self.parse_adb_devices_fn(raw_lines)

    def list_benches(self):
        return self.list_benches_fn(
            adb_path=self.adb_path,
            subprocess_kwargs=self.subprocess_windowless_kwargs_fn(),
        )

    def format_benches(self, benches: dict) -> str:
        return self.format_benches_fn(benches)

    def replace_number_words(self, text: str) -> str:
        return self.replace_number_words_fn(text)

    def normalize_token(self, text: str) -> str:
        return self.normalize_token_fn(text)

    def norm(self, text: str) -> str:
        return self.norm_fn(text)

    def has_any(self, normalized_text: str, terms: list[str]) -> bool:
        return self.has_any_fn(normalized_text, terms)

    def resolve_test(self, name_or_token: str):
        return self.resolve_test_fn(
            name_or_token,
            normalize_token_fn=self.normalize_token,
            norm_fn=self.norm,
            list_categories_fn=self.list_categories,
            list_tests_fn=self.list_tests,
        )

    def select_bench(self, bench: str | None, benches: dict):
        return self.select_bench_fn(bench, benches)

    def popen_host_python(self, cmd):
        return self.popen_host_python_fn(cmd, base_dir=self.base_dir)

    def read_serial_status(self, serial: str):
        return self.read_serial_status_fn(serial, data_root=self.data_root)

    def capture_radio_logs_for_test(self, category: str, test_name: str, serial: str, reason: str = "captura_manual_chat"):
        return self.capture_radio_logs_for_test_fn(category, test_name, serial, reason=reason)

    def capture_radio_log_command(self, text: str) -> str:
        return self.capture_radio_log_command_fn(
            text,
            list_benches_fn=self.list_benches,
            extract_bench_fn=self.extract_bench,
            select_bench_fn=self.select_bench,
            extract_test_token_fn=self.extract_test_token,
            resolve_test_fn=self.resolve_test,
            list_categories_fn=self.list_categories,
            list_tests_fn=self.list_tests,
            read_serial_status_fn=self.read_serial_status,
            capture_logs_fn=self.capture_radio_logs_for_test,
        )

    def update_bench_status(self, serial, status, category=None, test_name=None):
        return self.update_bench_status_fn(
            serial,
            status,
            category=category,
            test_name=test_name,
            data_root=self.data_root,
            status_lock=self.status_lock,
            error_logger=print,
        )

    def ollama_generate(self, prompt: str, timeout_s: int = 12, allow_cli: bool = True) -> str | None:
        return self.ollama_generate_fn(
            prompt,
            ollama_url=self.ollama_url,
            ollama_model=self.ollama_model,
            ollama_keep_alive=self.ollama_keep_alive,
            num_predict=self.ollama_num_predict,
            temperature=self.ollama_temperature,
            top_p=self.ollama_top_p,
            num_ctx=self.ollama_num_ctx,
            requests_module=self.requests_module,
            resolve_ollama_cli=self.resolve_ollama_cli_fn,
            timeout_s=timeout_s,
            allow_cli=allow_cli,
        )

    def llm_command(self, text: str, available_tests: list[str], categories: list[str]) -> str | None:
        return self.llm_command_fn(text, available_tests, categories, ollama_generate_fn=self.ollama_generate)

    def llm_chat_response(self, text: str) -> str | None:
        return self.llm_chat_response_fn(text, ollama_generate_fn=self.ollama_generate)

    def resolve_command_with_llm_or_fallback(self, text: str) -> str:
        return self.resolve_command_with_llm_or_fallback_fn(
            text,
            list_categories_fn=self.list_categories,
            list_tests_fn=self.list_tests,
            llm_command_fn=self.llm_command,
            interpret_command_fn=self.interpret_command,
        )

    def append_execution_log(self, log_path, new_entry):
        return self.append_execution_log_fn(log_path, new_entry, error_logger=print)

    def ensure_execution_dataset(self, category: str, test_name: str):
        return self.ensure_chat_execution_dataset_fn(
            category,
            test_name,
            data_root=self.data_root,
            process_script=self.process_script,
            base_dir=self.base_dir,
            logger=print,
        )

    def start_execution_on_serial(self, category: str, test_name: str, serial: str, bench_label: str | None = None) -> str:
        return self.start_execution_on_serial_fn(
            category,
            test_name,
            serial,
            bench_label=bench_label,
            data_root=self.data_root,
            run_script=self.run_script,
            base_dir=self.base_dir,
            read_serial_status_fn=self.read_serial_status,
            update_bench_status_fn=self.update_bench_status,
            append_execution_log_fn=self.append_execution_log,
            logger=print,
            session_state=self.session_state,
            conversation_mode=self.conversation_mode,
            rerun=self.rerun_fn,
        )

    def execute_test(self, category: str, test_name: str, bench: str | None = None) -> str:
        return self.execute_test_fn(
            category,
            test_name,
            bench,
            ensure_dataset_fn=self.ensure_execution_dataset,
            list_benches_fn=self.list_benches,
            select_bench_fn=self.select_bench,
            start_execution_on_serial_fn=self.start_execution_on_serial,
        )

    def extract_bench(self, text: str) -> str | None:
        return self.extract_bench_fn(text)

    def extract_test_token(self, text: str) -> str | None:
        return self.extract_test_token_fn(text)

    def list_categories(self):
        return self.list_categories_impl_fn(data_root=self.data_root)

    def list_tests(self, category):
        return self.list_tests_impl_fn(category, data_root=self.data_root)

    def extract_category(self, text: str) -> str | None:
        return self.extract_category_fn(text, list_categories=self.list_categories)

    def resolve_execution_chunk(self, text: str) -> tuple[str | None, str | None, str | None]:
        return self.resolve_execution_from_chunk_fn(
            text,
            extract_test_token_fn=self.extract_test_token,
            resolve_test_fn=self.resolve_test,
            list_categories_fn=self.list_categories,
            list_tests_fn=self.list_tests,
        )

    def extract_parallel_executions(self, text: str) -> tuple[list[dict[str, str]] | None, str | None]:
        return self.extract_parallel_executions_fn(
            text,
            replace_number_words_fn=self.replace_number_words,
            norm_fn=self.norm,
            extract_bench_fn=self.extract_bench,
            resolve_execution_chunk_fn=self.resolve_execution_chunk,
        )

    def execute_parallel_tests(self, executions: list[dict[str, str]]) -> str:
        return self.execute_parallel_tests_fn(
            executions,
            list_benches_fn=self.list_benches,
            ensure_execution_dataset_fn=self.ensure_execution_dataset,
            start_execution_on_serial_fn=self.start_execution_on_serial,
        )

    def resolve_navigation_command(self, text: str) -> str | None:
        return self.resolve_navigation_command_fn(
            text,
            normalize=self.norm,
            replace_number_words=self.replace_number_words,
            select_page=self.select_page_fn,
            open_menu_tester=self.open_menu_tester_fn,
            dashboard_page=self.dashboard_page,
            logs_page=self.logs_page,
            failures_page=self.failures_page,
            hmi_page=self.hmi_page,
            brain_page=self.brain_page,
            chat_page=self.chat_page,
        )

    def interpret_command(self, command: str) -> str:
        return self.interpret_command_fn(
            command,
            session_state=self.session_state,
            normalize=self.norm,
            has_any=self.has_any,
            resolve_navigation=self.resolve_navigation_command,
            list_categories=self.list_categories,
            list_tests=self.list_tests,
            format_benches=self.format_benches,
            list_benches=self.list_benches,
            extract_parallel_executions=self.extract_parallel_executions,
            run_parallel_tests=self.execute_parallel_tests,
            extract_category=self.extract_category,
            extract_test_token=self.extract_test_token,
            resolve_test=self.resolve_test,
            execute_test=self.execute_test,
            extract_bench=self.extract_bench,
            is_log_sequence_command=self.is_log_sequence_command_fn,
            record_global_log_sequence=self.record_global_log_sequence_fn,
            record_test=self.record_test_fn,
            process_test=self.process_test_fn,
            delete_test=self.delete_test_fn,
            capture_radio_logs=self.capture_radio_log_command,
            finalize_log_sequence=self.finalize_log_sequence_fn,
            pause_execution=self.pause_execution_fn,
            resume_execution=self.resume_execution_fn,
            stop_execution=self.stop_execution_fn,
            execute_keywords=self.execute_keywords,
            record_keywords=self.record_keywords,
            process_keywords=self.process_keywords,
            delete_keywords=self.delete_keywords,
            list_keywords=self.list_keywords,
            help_keywords=self.help_keywords,
            run_script=self.run_script,
            base_dir=self.base_dir,
        )

    def respond_conversational(self, command: str):
        return self.respond_conversational_fn(
            command,
            session_state=self.session_state,
            normalize=self.norm,
            resolve_navigation=self.resolve_navigation_command,
            resolve_command=self.resolve_command_with_llm_or_fallback,
            llm_respond=self.llm_chat_response,
            conversation_mode=self.conversation_mode,
            continue_recording_flow=self.continue_recording_flow_fn,
            extract_test_token=self.extract_test_token,
            is_log_sequence_command=self.is_log_sequence_command_fn,
            start_recording_flow=self.start_recording_flow_fn,
            finalize_log_sequence=self.finalize_log_sequence_fn,
        )


def build_chat_controller(**kwargs) -> ChatController:
    return ChatController(**kwargs)
