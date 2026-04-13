from __future__ import annotations

from functools import partial
from types import SimpleNamespace


def build_chat_page_utilities(
    *,
    normalize_post_speech_impl_fn,
    replace_number_words_fn,
    norm_fn,
    extract_test_token_fn,
    extract_bench_fn,
    resolve_test_fn,
    ensure_streamlit_app_impl_fn,
    base_dir: str,
    open_menu_tester_impl_fn,
    menu_tester_port: int,
    root_path_fn,
):
    def normalize_post_speech(text: str) -> str:
        return normalize_post_speech_impl_fn(
            text,
            replace_number_words_fn=replace_number_words_fn,
            norm_fn=norm_fn,
            extract_test_token_fn=extract_test_token_fn,
            extract_bench_fn=extract_bench_fn,
            resolve_test_fn=resolve_test_fn,
        )

    def ensure_streamlit_app(script_path: str, port: int, silence_output: bool = False, timeout_s: float = 12.0) -> bool:
        return ensure_streamlit_app_impl_fn(
            script_path,
            port,
            base_dir=base_dir,
            silence_output=silence_output,
            timeout_s=timeout_s,
        )

    def open_menu_tester() -> str:
        return open_menu_tester_impl_fn(
            menu_tester_port=menu_tester_port,
            root_path_fn=root_path_fn,
            ensure_streamlit_app_fn=ensure_streamlit_app,
        )

    return SimpleNamespace(
        normalize_post_speech=normalize_post_speech,
        ensure_streamlit_app=ensure_streamlit_app,
        open_menu_tester=open_menu_tester,
    )


def build_chat_page_bindings(
    *,
    controller,
    session_state,
    project_root: str,
    data_root: str,
    adb_path: str,
    process_script: str,
    collector_script: str,
    pause_flag_path: str,
    global_log_sequence_category: str,
    global_log_sequence_test: str,
    global_log_sequence_csv: str,
    start_recording_flow_impl_fn,
    is_log_sequence_command_impl_fn,
    record_global_log_sequence_impl_fn,
    finalize_global_log_sequence_impl_fn,
    continue_recording_flow_impl_fn,
    check_finalizations_impl_fn,
    check_finished_executions_impl_fn,
    save_partial_result_impl_fn,
    record_test_impl_fn,
    finalize_recording_impl_fn,
    cancel_recording_impl_fn,
    process_test_impl_fn,
    delete_test_impl_fn,
    list_categories_impl_fn,
    list_tests_impl_fn,
    pause_execution_impl_fn,
    resume_execution_impl_fn,
    stop_execution_impl_fn,
    export_global_log_sequence_fn,
):
    list_categories = partial(list_categories_impl_fn, data_root=data_root)
    list_tests = lambda category: list_tests_impl_fn(category, data_root=data_root)
    pause_execution = partial(pause_execution_impl_fn, pause_flag_path=pause_flag_path)
    resume_execution = partial(resume_execution_impl_fn, pause_flag_path=pause_flag_path)
    stop_execution = partial(stop_execution_impl_fn, project_root=project_root)

    def start_recording_flow():
        return start_recording_flow_impl_fn(session_state)

    def is_log_sequence_command(text: str) -> bool:
        return is_log_sequence_command_impl_fn(text, norm_fn=controller.norm)

    def record_test(category, test_name, bench: str | None = None):
        return record_test_impl_fn(
            category,
            test_name,
            bench,
            project_root=project_root,
            collector_script=collector_script,
            list_benches_fn=controller.list_benches,
            select_bench_fn=controller.select_bench,
            popen_host_python_fn=controller.popen_host_python,
        )

    def record_global_log_sequence(bench: str | None = None):
        return record_global_log_sequence_impl_fn(
            bench,
            session_state=session_state,
            record_test_fn=record_test,
            list_benches_fn=controller.list_benches,
            select_bench_fn=controller.select_bench,
            global_log_sequence_category=global_log_sequence_category,
            global_log_sequence_test=global_log_sequence_test,
            global_log_sequence_csv=global_log_sequence_csv,
        )

    def finalize_recording(category=None, test_name=None, serial=None):
        return finalize_recording_impl_fn(
            project_root=project_root,
            session_state=session_state,
            category=category,
            test_name=test_name,
            serial=serial,
            global_log_sequence_category=global_log_sequence_category,
            global_log_sequence_test=global_log_sequence_test,
        )

    def finalize_log_sequence():
        return finalize_global_log_sequence_impl_fn(
            session_state=session_state,
            finalize_recording_fn=finalize_recording,
        )

    def continue_recording_flow(response: str):
        return continue_recording_flow_impl_fn(
            response,
            session_state=session_state,
            list_benches_fn=controller.list_benches,
            extract_bench_fn=controller.extract_bench,
            record_test_fn=record_test,
        )

    def check_finalizations():
        check_finalizations_impl_fn(
            session_state=session_state,
            data_root=data_root,
            export_global_log_sequence_fn=export_global_log_sequence_fn,
        )

    def check_finished_executions():
        check_finished_executions_impl_fn(session_state=session_state)

    def save_partial_result(category, test_name, serial=None):
        return save_partial_result_impl_fn(
            category,
            test_name,
            serial,
            data_root=data_root,
            adb_path=adb_path,
        )

    def cancel_recording(category=None, test_name=None):
        return cancel_recording_impl_fn(
            project_root=project_root,
            data_root=data_root,
            session_state=session_state,
            global_log_sequence_category=global_log_sequence_category,
            global_log_sequence_test=global_log_sequence_test,
            category=category,
            test_name=test_name,
        )

    def process_test(category, test_name):
        return process_test_impl_fn(
            category,
            test_name,
            process_script=process_script,
            popen_host_python_fn=controller.popen_host_python,
        )

    def delete_test(category, test_name):
        return delete_test_impl_fn(category, test_name, data_root=data_root)

    return SimpleNamespace(
        process_voice_command=controller.process_voice_command,
        list_benches=controller.list_benches,
        format_benches=controller.format_benches,
        resolve_command_with_llm_or_fallback=controller.resolve_command_with_llm_or_fallback,
        respond_conversational=controller.respond_conversational,
        start_recording_flow=start_recording_flow,
        is_log_sequence_command=is_log_sequence_command,
        record_global_log_sequence=record_global_log_sequence,
        finalize_log_sequence=finalize_log_sequence,
        continue_recording_flow=continue_recording_flow,
        check_finalizations=check_finalizations,
        check_finished_executions=check_finished_executions,
        save_partial_result=save_partial_result,
        record_test=record_test,
        finalize_recording=finalize_recording,
        cancel_recording=cancel_recording,
        process_test=process_test,
        delete_test=delete_test,
        list_categories=list_categories,
        list_tests=list_tests,
        pause_execution=pause_execution,
        resume_execution=resume_execution,
        stop_execution=stop_execution,
    )
