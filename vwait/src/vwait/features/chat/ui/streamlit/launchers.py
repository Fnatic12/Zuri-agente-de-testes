import webbrowser


def open_panel(
    *,
    url: str,
    script_path: str,
    port: int,
    ensure_app_streamlit_fn,
    silence_output: bool = False,
    label: str,
) -> str:
    try:
        ready = ensure_app_streamlit_fn(
            script_path,
            port,
            silence_output=silence_output,
        )
        webbrowser.open_new_tab(url)
        if ready:
            return f"Abrindo o {label} em {url}."
        return f"{label} em inicializacao: {url}."
    except Exception as exc:
        return f"Falha ao abrir {label}: {exc}"
