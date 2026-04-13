def update_bench_status(
    serial,
    status,
    *,
    update_bench_status_fn,
    data_root: str,
    status_lock,
    error_logger,
    category=None,
    test_name=None,
):
    return update_bench_status_fn(
        serial,
        status,
        category=category,
        test_name=test_name,
        data_root=data_root,
        status_lock=status_lock,
        error_logger=error_logger,
    )


def ensure_chat_execution_dataset(
    category: str,
    test_name: str,
    *,
    ensure_execution_dataset_fn,
    data_root: str,
    process_script: str,
    base_dir: str,
    logger,
):
    return ensure_execution_dataset_fn(
        category,
        test_name,
        data_root=data_root,
        process_script=process_script,
        base_dir=base_dir,
        logger=logger,
    )


def start_execution_on_serial(
    category: str,
    test_name: str,
    serial: str,
    *,
    start_execution_on_serial_fn,
    bench_label: str | None,
    data_root: str,
    run_script: str,
    base_dir: str,
    read_serial_status_fn,
    update_bench_status_fn,
    append_execution_log_fn,
    logger,
    session_state,
    conversation_mode: bool,
    rerun,
):
    return start_execution_on_serial_fn(
        category,
        test_name,
        serial,
        bench_label=bench_label,
        data_root=data_root,
        run_script=run_script,
        base_dir=base_dir,
        read_serial_status_fn=read_serial_status_fn,
        update_bench_status_fn=update_bench_status_fn,
        append_execution_log_fn=append_execution_log_fn,
        logger=logger,
        session_state=session_state,
        conversation_mode=conversation_mode,
        rerun=rerun,
    )


def execute_test(
    category: str,
    test_name: str,
    bench: str | None = None,
    *,
    ensure_dataset_fn,
    list_benches_fn,
    select_bench_fn,
    start_execution_on_serial_fn,
):
    ok_dataset, dataset_error = ensure_dataset_fn(category, test_name)
    if not ok_dataset:
        return dataset_error or f"ERRO: falha ao preparar dataset de {category}/{test_name}."

    benches = list_benches_fn()
    serials, error = select_bench_fn(bench, benches)
    if error:
        return str(error)

    responses = []
    for serial in serials:
        responses.append(start_execution_on_serial_fn(category, test_name, serial))
    return "\n".join(responses)


def execute_parallel_tests(
    executions: list[dict[str, str]],
    *,
    run_parallel_tests_fn,
    list_benches_fn,
    ensure_execution_dataset_fn,
    start_execution_on_serial_fn,
) -> str:
    return run_parallel_tests_fn(
        executions,
        list_benches_fn=list_benches_fn,
        ensure_execution_dataset_fn=ensure_execution_dataset_fn,
        start_execution_on_serial_fn=start_execution_on_serial_fn,
    )
