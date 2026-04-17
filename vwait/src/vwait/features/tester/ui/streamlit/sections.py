from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from vwait.core.paths import (
    iter_tester_categories,
    iter_tester_tests,
    tester_actions_path,
    tester_catalog_dir,
    tester_dataset_path,
    tester_system_collection_log_path,
    tester_system_exec_log_path,
)


def _safe_index(options: list[str], value: str | None) -> int:
    if value in options:
        return options.index(value)
    return 0


def _selectbox_accept_new(label: str, *, options: list[str], key: str, help: str | None = None) -> str:
    try:
        return str(
            st.selectbox(
                label,
                options=options,
                index=_safe_index(options, st.session_state.get(key)),
                key=key,
                accept_new_options=True,
                help=help,
            )
            or ""
        )
    except TypeError:
        return st.text_input(
            label,
            key=key,
            placeholder="Digite ou selecione uma opção disponível",
            help=help,
        )


def _action_button(label: str, *, style: str, key: str | None = None, use_container_width: bool = True) -> bool:
    raw_scope = str(key or label or style).lower()
    scope_slug = re.sub(r"[^a-z0-9_]+", "-", raw_scope).strip("-") or "button"
    scope_key = f"tester-btn-{style}-{scope_slug}"
    try:
        container = st.container(key=scope_key)
    except TypeError:
        container = st.container()
    with container:
        st.markdown(f"<span class='tester-button-marker tester-btn-{style}'></span>", unsafe_allow_html=True)
        return st.button(label, key=key, use_container_width=use_container_width)


def _render_training_help_content() -> None:
    st.markdown("### Como preencher a exportação para TrainingData")
    st.write("Use esta opção quando a coleta representar um fluxo válido para treinamento supervisionado.")
    st.write("Se houver dúvida sobre nome de categoria ou fluxo, alinhe antes de salvar.")
    st.markdown("#### Exemplo claro para o tester")
    st.markdown(
        """
        - Marque `Salvar também para TrainingData` antes de iniciar/finalizar a coleta.
        - Em `Categoria/DOMÍNIO`, escreva o domínio funcional. Exemplo: `tuner`.
        - Em `Fluxo/Caso de teste`, escreva o fluxo específico. Exemplo: `validar_funcoes_padrao_do_tuner`.
        - Em `Objetivo do episódio`, descreva o que o agente deve aprender. Exemplo: `Validar se o Tuner abre, troca de estação e mantém a tela correta`.
        - Em `Critério de sucesso final`, descreva o estado final esperado. Exemplo: `A tela do Tuner aparece sem erro visual, com frequência visível e botões respondendo`.
        - Em `Intenção por passo`, use uma linha por ação gravada. Exemplo: `Abrir menu principal`, `Entrar no Tuner`, `Trocar estação`.
        - Em `Resultado esperado por passo`, use uma linha por ação dizendo o que deve aparecer depois dela.
        """
    )
    st.info(
        "Dica: a coleta em Data/ continua igual. O TrainingData/ é uma segunda saída para preparar exemplos de treino supervisionado."
    )


def _open_training_help_modal() -> None:
    dialog = getattr(st, "dialog", None)
    if callable(dialog):
        @dialog("Ajuda da exportação supervisionada")
        def _training_help_dialog() -> None:
            _render_training_help_content()

        _training_help_dialog()
        return

    st.session_state["show_training_help_fallback"] = True


def render_collection_section(
    *,
    base_dir: str,
    stop_flag_path: str,
    scripts: dict[str, str],
    bancadas: list[str],
    clean_display_text,
    salvar_resultado_parcial,
    abrir_scrcpy_persistente,
    criar_training_episode_draft,
    completar_training_episodes_pendentes,
    exportar_training_episode,
    resolver_teste_por_serial,
    capturar_logs_radio,
    resolver_pasta_logs_teste,
    abrir_pasta_local,
):
    st.subheader("Coletar Gestos")
    pending_results = completar_training_episodes_pendentes()
    completed_pending = [message for ok, message in pending_results if ok]
    failed_pending = [message for ok, message in pending_results if not ok and "Aguardando actions.json" not in message]
    if completed_pending:
        st.success(f"TrainingData atualizado com steps em {len(completed_pending)} episódio(s).")
    if failed_pending:
        st.warning("Alguns episódios TrainingData ainda não foram completados: " + "; ".join(failed_pending[:2]))

    categoria = st.text_input("Categoria do Teste (ex: audio, video, bluetooth)", key="cat_coleta")
    nome_teste = st.text_input("Nome do Teste (ex: audio_1, bt_pareamento)", key="nome_coleta")

    serial_sel = None
    if bancadas:
        serial_sel = st.selectbox("Bancada/Dispositivo ADB", options=bancadas, index=0)
    else:
        st.info("Nenhum dispositivo ADB encontrado. Conecte o radio e clique em iniciar.")

    fonte_coleta_label = st.selectbox(
        "Fonte de coleta",
        options=["Bancada (ADB)", "Scrcpy (ADB)"],
        index=0,
    )
    fonte_coleta = "scrcpy" if fonte_coleta_label.lower().startswith("scrcpy") else "adb"
    if fonte_coleta == "scrcpy":
        st.caption("A coleta Scrcpy abre uma janela gerenciada pelo VWAIT. Interaja nessa janela para registrar cada toque.")

    with st.expander("Exportação supervisionada (TrainingData)", expanded=False):
        help_col, hint_col = st.columns([1, 3])
        with help_col:
            if _action_button("Como preencher", style="help", key="training_help_btn"):
                _open_training_help_modal()
        with hint_col:
            st.caption("Abra a ajuda para ver um exemplo pronto antes de gravar uma coleta para treinamento supervisionado.")

        if st.session_state.get("show_training_help_fallback"):
            with st.container(border=True):
                _render_training_help_content()
                if _action_button("Fechar ajuda", style="open", key="training_help_close"):
                    st.session_state["show_training_help_fallback"] = False
                    st.rerun()

        export_training_enabled = st.checkbox(
            "Salvar também para TrainingData",
            key="training_export_enabled",
            help=(
                "Marque esta opção quando esta coleta também deve virar um episódio "
                "para futuro treino supervisionado. A coleta normal em Data/ continua igual."
            ),
        )
        training_category = st.text_input(
            "Categoria/DOMÍNIO",
            key="training_category",
            placeholder="Exemplo: tuner",
            help=(
                "Domínio funcional do rádio que este teste cobre. "
                "Exemplos: tuner, bluetooth, audio, navigation, camera."
            ),
        )
        training_flow = st.text_input(
            "Fluxo/Caso de teste",
            key="training_flow",
            placeholder="Exemplo: validar_funcoes_padrao_do_tuner",
            help=(
                "Nome do fluxo que o agente deverá aprender a executar dentro do domínio. "
                "Exemplos: validar_funcoes_padrao_do_tuner, parear_dispositivo_bluetooth, ajustar_volume."
            ),
        )
        training_objective = st.text_area(
            "Objetivo do episódio",
            key="training_objective",
            placeholder=(
                "Exemplo: Validar se o Tuner abre corretamente, troca de estação "
                "e mantém a tela principal funcional."
            ),
            help=(
                "Explique em linguagem natural o que este episódio ensina. "
                "Pense como se fosse o prompt futuro para o agente."
            ),
            height=80,
        )
        training_success_criteria = st.text_area(
            "Critério de sucesso final",
            key="training_success_criteria",
            placeholder=(
                "Exemplo: O rádio deve estar na tela do Tuner, sem erro visual, "
                "com estação/frequência visível e botões respondendo."
            ),
            help=(
                "Descreva como saber que o teste terminou corretamente. "
                "Esse texto ajuda o agente/modelo a entender o estado final esperado."
            ),
            height=80,
        )
        training_step_intents = st.text_area(
            "Intenção por passo (opcional, 1 por linha)",
            key="training_step_intents",
            placeholder=(
                "Exemplo:\n"
                "Abrir o menu principal\n"
                "Entrar na tela do Tuner\n"
                "Selecionar próxima estação\n"
                "Voltar para a tela anterior"
            ),
            help=(
                "Opcional. Escreva uma intenção para cada toque/gesto gravado, na mesma ordem da coleta. "
                "Se deixar vazio ou faltar alguma linha, o VWAIT preenche automaticamente com fallback."
            ),
            height=100,
        )
        training_step_expected = st.text_area(
            "Resultado esperado por passo (opcional, 1 por linha)",
            key="training_step_expected",
            placeholder=(
                "Exemplo:\n"
                "Menu principal aparece na tela\n"
                "Tela do Tuner é exibida\n"
                "Frequência muda para a próxima estação\n"
                "Tela anterior é exibida sem falhas"
            ),
            help=(
                "Opcional. Escreva o resultado visual/comportamental esperado após cada passo. "
                "Use uma linha por passo, alinhada com as intenções acima."
            ),
            height=100,
        )
        training_notes = st.text_area(
            "Observações (opcional)",
            key="training_notes",
            placeholder=(
                "Exemplo: Teste gravado com rádio em português, tema escuro, "
                "sem rede conectada e volume em 10."
            ),
            help=(
                "Opcional. Use para contexto extra que pode ajudar no treino ou análise futura, "
                "como idioma, tema, versão do software, pré-condições ou comportamento observado."
            ),
            height=80,
        )
        if categoria and nome_teste:
            current_actions_path = str(tester_actions_path(categoria, nome_teste))
            if os.path.exists(current_actions_path):
                try:
                    with open(current_actions_path, "r", encoding="utf-8") as handle:
                        current_payload = json.load(handle)
                    current_actions = current_payload.get("acoes", []) if isinstance(current_payload, dict) else []
                    if current_actions:
                        st.caption(f"Passos gravados atualmente: {len(current_actions)}")
                except Exception:
                    pass
        if export_training_enabled:
            st.caption(
                "A coleta continua igual. O episódio em TrainingData/ será exportado depois que você finalizar "
                "a coleta e capturar/salvar o resultado esperado final."
            )

    def _training_required_missing() -> list[str]:
        if not export_training_enabled:
            return []
        fields = [
            ("Categoria/DOMÍNIO", training_category),
            ("Fluxo/Caso de teste", training_flow),
            ("Objetivo do episódio", training_objective),
            ("Critério de sucesso final", training_success_criteria),
        ]
        return [label for label, value in fields if not str(value or "").strip()]

    def _export_training_from_payload(payload: dict) -> tuple[bool, str]:
        with st.spinner("Exportando episódio para TrainingData..."):
            return exportar_training_episode(
                categoria=payload.get("categoria", ""),
                nome_teste=payload.get("nome_teste", ""),
                training_category=payload.get("training_category", ""),
                flow=payload.get("training_flow", ""),
                objective=payload.get("training_objective", ""),
                success_criteria_final=payload.get("training_success_criteria", ""),
                notes=payload.get("training_notes", ""),
                serial=payload.get("serial"),
                input_source=payload.get("fonte_coleta"),
                step_intents_text=payload.get("training_step_intents", ""),
                step_expected_text=payload.get("training_step_expected", ""),
                episode_id=payload.get("training_episode_id"),
            )

    def _current_training_payload() -> dict:
        return {
            "categoria": categoria,
            "nome_teste": nome_teste,
            "serial": serial_sel,
            "fonte_coleta": fonte_coleta,
            "export_training_enabled": bool(export_training_enabled),
            "training_category": training_category,
            "training_flow": training_flow,
            "training_objective": training_objective,
            "training_success_criteria": training_success_criteria,
            "training_notes": training_notes,
            "training_step_intents": training_step_intents,
            "training_step_expected": training_step_expected,
        }

    def _export_training_if_enabled(payload: dict) -> None:
        if not payload.get("export_training_enabled"):
            return
        required_payload_fields = [
            ("Categoria/DOMÍNIO", payload.get("training_category")),
            ("Fluxo/Caso de teste", payload.get("training_flow")),
            ("Objetivo do episódio", payload.get("training_objective")),
            ("Critério de sucesso final", payload.get("training_success_criteria")),
        ]
        missing_training = [label for label, value in required_payload_fields if not str(value or "").strip()]
        if missing_training:
            st.error("TrainingData não exportada. Campos obrigatórios ausentes: " + ", ".join(missing_training))
            return
        ok_export, msg_export = _export_training_from_payload(payload)
        if ok_export:
            st.success(f"Episódio supervisionado exportado em: {msg_export}")
            st.session_state["coleta_expected_pending"] = None
        else:
            st.error(f"Falha ao exportar TrainingData: {msg_export}")

    pending_expected = st.session_state.get("coleta_expected_pending")
    if isinstance(pending_expected, dict):
        with st.container(border=True):
            st.warning("Toque na tela para gravar o resultado esperado do teste.")
            st.caption(
                "Depois de tocar no rádio/scrcpy e deixar a tela no estado final correto, "
                "clique no botão abaixo para capturar o esperado e finalizar a exportação."
            )
            pending_label = f"{pending_expected.get('categoria', '-')}/{pending_expected.get('nome_teste', '-')}"
            st.caption(f"Coleta aguardando resultado esperado: {pending_label}")
            confirm_col, cancel_col = st.columns([2, 1])
            with confirm_col:
                if _action_button("Capturar esperado e finalizar", style="open", key="confirmar_resultado_esperado"):
                    pending_category = str(pending_expected.get("categoria") or "").strip()
                    pending_test = str(pending_expected.get("nome_teste") or "").strip()
                    pending_serial = pending_expected.get("serial")
                    ok_expected, msg_expected = salvar_resultado_parcial(pending_category, pending_test, pending_serial)
                    if ok_expected:
                        st.success(f"Resultado esperado salvo: {msg_expected}")
                        _export_training_if_enabled(pending_expected)
                        if not pending_expected.get("export_training_enabled"):
                            st.session_state["coleta_expected_pending"] = None
                    else:
                        st.error(msg_expected)
            with cancel_col:
                if _action_button("Cancelar etapa", style="open", key="cancelar_resultado_esperado"):
                    st.session_state["coleta_expected_pending"] = None
                    st.rerun()

    if _action_button("Abrir Scrcpy", style="open", key="abrir_scrcpy_full_width"):
        if not serial_sel:
            st.error("Selecione uma bancada/dispositivo ADB antes de abrir o scrcpy.")
        else:
            ok_scrcpy, msg_scrcpy = abrir_scrcpy_persistente(serial_sel)
            if ok_scrcpy:
                st.success(msg_scrcpy)
            else:
                st.error(f"Falha ao abrir o scrcpy: {msg_scrcpy}")
    st.caption("Use este botao para manter uma sessao persistente do scrcpy aberta e reutiliza-la nas gravacoes e execucoes.")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        if _action_button("Iniciar Coleta", style="open"):
            if categoria and nome_teste:
                missing_training = _training_required_missing()
                if missing_training:
                    st.error("Preencha os campos obrigatórios da TrainingData: " + ", ".join(missing_training))
                    return
                if st.session_state.proc_coleta is None:
                    pause_path = os.path.join(base_dir, "pause.flag")
                    if os.path.exists(pause_path):
                        try:
                            os.remove(pause_path)
                        except Exception:
                            pass
                    if os.path.exists(stop_flag_path):
                        try:
                            os.remove(stop_flag_path)
                        except Exception:
                            pass

                    log_path = str(tester_system_collection_log_path())
                    st.session_state.coleta_log_path = log_path
                    log_file = open(log_path, "w", encoding="utf-8", errors="ignore", buffering=1)
                    st.session_state.coleta_log_file = log_file
                    env = os.environ.copy()
                    env["PYTHONUNBUFFERED"] = "1"
                    training_payload = _current_training_payload()
                    if export_training_enabled:
                        ok_draft, msg_draft, episode_id = criar_training_episode_draft(
                            categoria=categoria,
                            nome_teste=nome_teste,
                            training_category=training_category,
                            flow=training_flow,
                            objective=training_objective,
                            success_criteria_final=training_success_criteria,
                            notes=training_notes,
                            serial=serial_sel,
                            input_source=fonte_coleta,
                            step_intents_text=training_step_intents,
                            step_expected_text=training_step_expected,
                        )
                        if not ok_draft:
                            st.error(f"Não consegui iniciar o TrainingData: {msg_draft}")
                            return
                        training_payload["training_episode_id"] = episode_id
                        training_payload["training_episode_path"] = msg_draft
                        st.success(f"TrainingData iniciado em: {msg_draft}")
                    st.session_state["coleta_training_payload"] = training_payload
                    cmd = [sys.executable, "-u", scripts["Coletar Teste"], categoria, nome_teste]
                    if serial_sel:
                        cmd += ["--serial", serial_sel]
                    if fonte_coleta != "adb":
                        cmd += ["--source", fonte_coleta]

                    st.session_state.proc_coleta = subprocess.Popen(
                        cmd,
                        cwd=base_dir,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                        env=env,
                    )
                    st.success(f"Coleta iniciada para {categoria}/{nome_teste}")
                    if export_training_enabled:
                        st.info("TrainingData preparado. Finalize a coleta e salve o resultado esperado para exportar o episódio.")
                else:
                    st.warning("Já existe uma coleta em andamento.")
            else:
                st.error("Preencha categoria e nome do teste antes de iniciar.")

    with col2:
        if _action_button("Finalizar Coleta", style="open"):
            proc = st.session_state.proc_coleta
            if proc:
                try:
                    missing_training = _training_required_missing()
                    if missing_training:
                        st.error("TrainingData não exportada. Campos obrigatórios ausentes: " + ", ".join(missing_training))
                        return
                    with open(stop_flag_path, "w") as handle:
                        handle.write("stop")
                    st.info("Finalizando coleta. Em seguida, toque na tela para gravar o resultado esperado do teste.")
                    timeout_s = 60
                    proc.wait(timeout=timeout_s)

                    acoes_path = str(tester_actions_path(categoria, nome_teste))
                    if os.path.exists(acoes_path):
                        st.session_state["coleta_expected_pending"] = (
                            st.session_state.get("coleta_training_payload") or _current_training_payload()
                        )
                        st.success("Coleta finalizada com sucesso. Ações salvas.")
                        st.warning("Toque na tela para gravar o resultado esperado do teste.")
                    else:
                        st.warning("Coleta finalizada, mas o acoes.json não apareceu. Verifique o log.")
                except subprocess.TimeoutExpired:
                    proc.kill()
                    st.warning("Coletor não respondeu, finalizado à força.")
                finally:
                    if os.path.exists(stop_flag_path):
                        os.remove(stop_flag_path)
                    if st.session_state.coleta_log_file:
                        try:
                            st.session_state.coleta_log_file.close()
                        except Exception:
                            pass
                        st.session_state.coleta_log_file = None
                    st.session_state.proc_coleta = None
                st.rerun()
            else:
                if st.session_state.get("coleta_expected_pending"):
                    st.warning("Toque na tela para gravar o resultado esperado do teste.")
                else:
                    st.info("Nenhuma coleta em andamento.")

    with col3:
        if _action_button("Salvar Resultado Esperado", style="open"):
            if categoria and nome_teste:
                ok, msg = salvar_resultado_parcial(categoria, nome_teste, serial_sel)
                if ok:
                    st.success(f"Resultado esperado salvo: {msg}")
                    payload = st.session_state.get("coleta_expected_pending")
                    if not isinstance(payload, dict):
                        payload = st.session_state.get("coleta_training_payload")
                    if not isinstance(payload, dict):
                        payload = _current_training_payload()
                    _export_training_if_enabled(payload)
                else:
                    st.error(msg)
            else:
                st.error("Informe categoria e nome do teste antes de salvar o esperado.")

    with col4:
        if _action_button("Capturar Log do Radio", style="open"):
            if not serial_sel:
                st.error("Selecione uma bancada conectada para capturar logs.")
            else:
                categoria_logs = (categoria or "").strip()
                nome_teste_logs = (nome_teste or "").strip()
                if not categoria_logs or not nome_teste_logs:
                    categoria_logs, nome_teste_logs = resolver_teste_por_serial(serial_sel)

                if not categoria_logs or not nome_teste_logs:
                    st.error("Nao consegui resolver o teste desta bancada. Informe categoria/nome do teste ou rode um teste antes.")
                else:
                    with st.spinner("Capturando logs do radio..."):
                        resultado = capturar_logs_radio(categoria_logs, nome_teste_logs, serial_sel)
                    status_captura = str(resultado.get("status", "") or "")
                    pasta_logs = resultado.get("artifact_dir")
                    erro_logs = resultado.get("error")
                    if status_captura == "capturado":
                        st.success(f"Logs capturados em {pasta_logs}")
                    elif status_captura == "sem_artefatos":
                        st.warning(f"Nenhum log novo encontrado. Pasta gerada em {pasta_logs}")
                    else:
                        st.error(f"Falha ao capturar logs: {erro_logs or 'erro desconhecido'}")

    with col5:
        if _action_button("Abrir Pasta de Logs", style="open"):
            if not serial_sel:
                st.error("Selecione uma bancada conectada para abrir os logs.")
            else:
                categoria_logs = (categoria or "").strip()
                nome_teste_logs = (nome_teste or "").strip()
                if not categoria_logs or not nome_teste_logs:
                    categoria_logs, nome_teste_logs = resolver_teste_por_serial(serial_sel)

                if not categoria_logs or not nome_teste_logs:
                    st.error("Nao consegui resolver o teste desta bancada. Informe categoria/nome do teste ou rode um teste antes.")
                else:
                    pasta_logs = resolver_pasta_logs_teste(categoria_logs, nome_teste_logs, serial_sel)
                    if not pasta_logs:
                        st.error("Nenhuma pasta de logs encontrada para este teste.")
                    else:
                        ok_open, detalhe_open = abrir_pasta_local(pasta_logs)
                        if ok_open:
                            st.success(f"Pasta de logs aberta: {pasta_logs}")
                        else:
                            st.error(f"Falha ao abrir a pasta de logs: {detalhe_open}")

    log_path = st.session_state.coleta_log_path
    proc = st.session_state.proc_coleta
    if log_path and os.path.exists(log_path):
        st.markdown("**Logs da coleta (ao vivo)**" if proc is not None else "**Logs da ultima coleta**")
        if proc is not None and proc.poll() is None:
            st_autorefresh(interval=150, limit=None, key="coleta_refresh")

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
            logs_txt = clean_display_text("".join(lines[-300:]))
        except Exception:
            logs_txt = ""

        st.text_area("Toques e eventos", value=logs_txt, height=220)

        acoes_path = None
        if categoria and nome_teste:
            acoes_path = str(tester_actions_path(categoria, nome_teste))

        if acoes_path and os.path.exists(acoes_path):
            try:
                with open(acoes_path, "r", encoding="utf-8") as handle:
                    acoes_payload = json.load(handle)
                acoes_items = acoes_payload.get("acoes", []) if isinstance(acoes_payload, dict) else []
            except Exception:
                acoes_items = []

            if acoes_items:
                rows = []
                for item in acoes_items[-12:]:
                    acao = item.get("acao", {}) if isinstance(item, dict) else {}
                    rows.append(
                        {
                            "id": item.get("id"),
                            "tipo": acao.get("tipo", ""),
                            "gesture": acao.get("gesture", ""),
                            "action_timestamp": item.get("action_timestamp", item.get("timestamp", "")),
                            "screenshot_timestamp": item.get("screenshot_timestamp", ""),
                            "imagem": item.get("imagem", ""),
                        }
                    )

                st.markdown("**Tempos das ações coletadas**")
                st.dataframe(rows, use_container_width=True, hide_index=True)

        if proc is not None and proc.poll() is not None:
            st.warning(f"Coleta finalizada com codigo {proc.returncode}. Veja o log acima.")
            st.session_state.proc_coleta = None

    return {"categoria": categoria, "nome_teste": nome_teste, "serial_sel": serial_sel}


def render_management_and_execution_sections(
    *,
    base_dir: str,
    scripts: dict[str, str],
    bancadas: list[str],
    serial_sel: str | None,
    carregar_status_execucao,
    formatar_resumo_execucao,
    iniciar_execucoes_teste_unico,
    iniciar_execucoes_configuradas,
    clean_display_text,
    garantir_painel_streamlit,
):
    st.divider()
    st.subheader("Deletar Teste")
    cat_del = st.text_input("Categoria do Teste a deletar", key="cat_del")
    nome_del = st.text_input("Nome do Teste a deletar", key="nome_del")

    if _action_button("Deletar Teste", style="danger"):
        if cat_del and nome_del:
            teste_path = str(tester_catalog_dir(cat_del, nome_del))
            runs_path = os.path.join(base_dir, "Data", "runs", "tester", cat_del, nome_del)
            if os.path.exists(teste_path) or os.path.exists(runs_path):
                try:
                    if os.path.exists(teste_path):
                        shutil.rmtree(teste_path)
                    if os.path.exists(runs_path):
                        shutil.rmtree(runs_path)
                    st.success(f"Teste {cat_del}/{nome_del} deletado com sucesso.")
                except Exception as exc:
                    st.error(f"rro ao deletar: {exc}")
            else:
                st.warning(f"Teste {cat_del}/{nome_del} não encontrado.")
        else:
            st.error("Informe categoria e nome do teste para deletar.")

    st.divider()
    st.subheader("Processar Dataset (opcional)")
    categoria_ds = st.text_input("Categoria do Dataset", key="cat_dataset")
    nome_teste_ds = st.text_input("Nome do Teste", key="nome_dataset")

    if _action_button("Processar Dataset", style="save"):
        if categoria_ds and nome_teste_ds:
            with st.spinner(f"Processando dataset de {categoria_ds}/{nome_teste_ds}..."):
                proc_dataset = subprocess.run(
                    [sys.executable, scripts["Processar Dataset"], categoria_ds, nome_teste_ds],
                    cwd=base_dir,
                    capture_output=True,
                    text=True,
                )

            saida_dataset = clean_display_text(
                "\n".join(parte for parte in [proc_dataset.stdout, proc_dataset.stderr] if parte and parte.strip())
            )
            if proc_dataset.returncode == 0:
                st.success(f"Dataset de {categoria_ds}/{nome_teste_ds} processado com sucesso.")
                if saida_dataset:
                    st.caption(saida_dataset)
            else:
                st.error(f"Falha ao processar dataset de {categoria_ds}/{nome_teste_ds}.")
                if saida_dataset:
                    st.text_area("Detalhes do processamento", value=saida_dataset, height=180, disabled=True)
        else:
            st.error("Informe categoria e nome do teste.")

    st.divider()
    st.subheader("Executar Testes")
    categorias_exec_options = [""] + iter_tester_categories()
    categoria_exec = _selectbox_accept_new(
        "Categoria do Teste",
        options=categorias_exec_options,
        key="cat_exec",
        help="Categorias disponíveis em Data/catalog/tester.",
    )
    testes_exec_options = [""] + (iter_tester_tests(categoria_exec) if categoria_exec else [])
    nome_teste_exec = _selectbox_accept_new(
        "Nome do Teste (deixe vazio para rodar todos)",
        options=testes_exec_options,
        key="nome_exec",
        help="Testes disponíveis dentro da categoria selecionada.",
    )
    fonte_exec_label = st.selectbox(
        "Fonte de execucao",
        options=["Bancada (ADB)", "Scrcpy (ADB)"],
        index=0,
        key="fonte_exec",
    )
    fonte_exec = "scrcpy" if fonte_exec_label.lower().startswith("scrcpy") else "adb"
    st.markdown("**Execucao paralela por bancada**")

    execucoes_paralelas_config = []
    if bancadas:
        colunas_paralelas = st.columns(2)
        for idx, serial_bancada in enumerate(bancadas, start=1):
            with colunas_paralelas[(idx - 1) % 2]:
                st.caption(f"Bancada {idx}")
                st.caption(f"Serial: {serial_bancada}")
                cat_key = f"cat_exec_b{idx}"
                test_key = f"nome_exec_b{idx}"
                categoria_exec_b = _selectbox_accept_new(
                    f"Categoria Bancada {idx}",
                    options=categorias_exec_options,
                    key=cat_key,
                )
                testes_b_options = [""] + (iter_tester_tests(categoria_exec_b) if categoria_exec_b else [])
                nome_teste_exec_b = _selectbox_accept_new(
                    f"Teste Bancada {idx}",
                    options=testes_b_options,
                    key=test_key,
                )
                if categoria_exec_b.strip() and nome_teste_exec_b.strip():
                    execucoes_paralelas_config.append(
                        {
                            "categoria": categoria_exec_b.strip(),
                            "teste": nome_teste_exec_b.strip(),
                            "serial": serial_bancada,
                            "label": f"Bancada {idx}",
                            "input_source": fonte_exec,
                        }
                    )
    else:
        st.info("Nenhuma bancada conectada para execucao paralela.")

    st.markdown("<div class='exec-row'>", unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns([2, 2, 2])

    with col_a:
        st.markdown("<div class='exec-card'>", unsafe_allow_html=True)
        st.markdown("<h4>Executar teste unico</h4>", unsafe_allow_html=True)
        btn_unico_col, btn_duplo_col = st.columns(2)
        with btn_unico_col:
            executar_teste_unico = _action_button("Executar Teste Unico", style="run")
        with btn_duplo_col:
            executar_duplo = _action_button("Rodar Testes em Paralelo", style="run", key="executar_teste_duplo")

        if executar_teste_unico:
            serial_exec = serial_sel or (bancadas[0] if bancadas else None)
            ok_exec, msg_exec, processos = iniciar_execucoes_teste_unico(
                categoria_exec,
                nome_teste_exec,
                [serial_exec] if serial_exec else [],
                input_source=fonte_exec,
            )
            if ok_exec and processos:
                serial = processos[0]["serial"]
                st.success(f"Execucao iniciada para {categoria_exec}/{nome_teste_exec} (Bancada {serial})")
            else:
                st.error(msg_exec)

        if executar_duplo:
            if len(bancadas) < 2:
                st.error("Conecte pelo menos duas bancadas ADB para rodar em paralelo.")
            elif len(execucoes_paralelas_config) < 2:
                st.error("Preencha pelo menos duas bancadas com categoria e teste para executar em paralelo.")
            else:
                ok_exec, msg_exec, processos = iniciar_execucoes_configuradas(execucoes_paralelas_config)
                if ok_exec:
                    st.success("Execucoes iniciadas ao mesmo tempo nas bancadas configuradas.")
                    for processo in processos:
                        st.caption(f"{processo['label']}: {processo['categoria']}/{processo['teste']} em {processo['serial']}")
                else:
                    st.error(msg_exec)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown("<div class='exec-card secondary'>", unsafe_allow_html=True)
        st.markdown("<h4>Status</h4>", unsafe_allow_html=True)

        execucao_processos = st.session_state.get("execucao_unica_processos", [])
        status_msgs = []
        existe_execucao_ativa = False
        for item in execucao_processos:
            proc_exec = item.get("proc")
            if proc_exec is None:
                continue
            if proc_exec.poll() is None:
                payload = carregar_status_execucao(item.get("categoria"), item.get("teste"), item.get("serial"))
                resumo = formatar_resumo_execucao(payload)
                existe_execucao_ativa = True
                status_msgs.append(f"{item.get('label', 'Bancada')} ({item.get('serial', '-')}): {resumo.lower()}.")
                continue

            if not item.get("log_closed") and item.get("log_file") is not None:
                try:
                    item["log_file"].close()
                except Exception:
                    pass
                item["log_closed"] = True

            payload = carregar_status_execucao(item.get("categoria"), item.get("teste"), item.get("serial"))
            resumo = formatar_resumo_execucao(payload, fallback_returncode=proc_exec.returncode)
            status_msgs.append(f"{item.get('label', 'Bancada')} ({item.get('serial', '-')}): {resumo.lower()}.")

        if existe_execucao_ativa:
            st_autorefresh(interval=500, limit=None, key="execucao_unica_refresh")

        st.session_state["teste_em_execucao"] = existe_execucao_ativa
        if not existe_execucao_ativa:
            st.session_state["proc_execucao_unica"] = None
            st.session_state["execucao_unica_status"] = ""

        status_msg = "<br>".join(status_msgs) if status_msgs else "Nenhum teste em execucao."
        st.markdown(f"<div class='status-box'>{status_msg}</div>", unsafe_allow_html=True)

        if "teste_em_execucao" in st.session_state and st.session_state["teste_em_execucao"]:
            if not st.session_state.get("teste_pausado", False):
                st.markdown("<div class='pause-btn'>", unsafe_allow_html=True)
                if _action_button("Pausar Teste", style="pause", key="pause_teste"):
                    with open(os.path.join(base_dir, "pause.flag"), "w") as handle:
                        handle.write("pause")
                    st.session_state["teste_pausado"] = True
                    st.warning("Execucao pausada.")
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='resume-btn'>", unsafe_allow_html=True)
                if _action_button("Retomar Teste", style="resume", key="resume_teste"):
                    pause_path = os.path.join(base_dir, "pause.flag")
                    if os.path.exists(pause_path):
                        os.remove(pause_path)
                    st.session_state["teste_pausado"] = False
                    st.success("Execucao retomada com sucesso.")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.caption("Sem teste em execucao.")

        st.markdown("</div>", unsafe_allow_html=True)

    with col_c:
        st.markdown("<div class='exec-card secondary'>", unsafe_allow_html=True)
        st.markdown("<h4>Executar todos</h4>", unsafe_allow_html=True)
        btn_all_col, _btn_all_spacer = st.columns(2)
        with btn_all_col:
            executar_todos_categoria = _action_button("Executar Todos da Categoria", style="run")

        if executar_todos_categoria:
            if categoria_exec:
                categoria_path = str(tester_catalog_dir(categoria_exec, "__placeholder__").parent)
                if not os.path.isdir(categoria_path):
                    st.error(f"Categoria {categoria_exec} nao encontrada em Data/catalog/tester/")
                else:
                    testes = iter_tester_tests(categoria_exec)
                    if not testes:
                        st.warning(f"Nenhum teste encontrado em Data/catalog/tester/{categoria_exec}/")
                    else:
                        st.success(f"Executando {len(testes)} testes da categoria {categoria_exec}...")
                        for teste in testes:
                            dataset_path = str(tester_dataset_path(categoria_exec, teste))
                            if not os.path.exists(dataset_path):
                                subprocess.run(["python", scripts["Processar Dataset"], categoria_exec, teste], cwd=base_dir)

                            log_path = str(tester_system_exec_log_path())
                            st.session_state["execucao_log_path"] = log_path
                            log_file = open(log_path, "a", encoding="utf-8", errors="ignore", buffering=1)
                            subprocess.Popen(
                                [
                                    "python",
                                    scripts["Executar Teste"],
                                    categoria_exec,
                                    teste,
                                    "--input-source",
                                    fonte_exec,
                                ],
                                cwd=base_dir,
                                stdout=log_file,
                                stderr=subprocess.STDOUT,
                                text=True,
                            )
            else:
                st.error("Informe a categoria para rodar todos os testes.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def render_reports_and_links_section(*, base_dir: str, scripts: dict[str, str], garantir_painel_streamlit):
    st.divider()
    st.subheader("Gerar Relatórios de Falhas")

    if _action_button("Gerar Relatórios de Falhas (execução_log.json)", style="report"):
        gerar_falha_path = scripts["Gerar Relatórios de Falhas"]
        if not os.path.exists(gerar_falha_path):
            st.error("Arquivo generate_failure_reports.py não encontrado.")
        else:
            with st.spinner("Analisando execucao_log.json e gerando relatórios..."):
                try:
                    result = subprocess.run(
                        [sys.executable, gerar_falha_path],
                        cwd=base_dir,
                        capture_output=True,
                        text=True,
                    )
                    st.text_area("Saída do Script", result.stdout, height=250)

                    rel_dir = os.path.join(base_dir, "workspace", "reports", "failures")
                    if os.path.isdir(rel_dir):
                        relatorios = sorted(
                            [
                                os.path.relpath(os.path.join(root, name), rel_dir)
                                for root, _, files in os.walk(rel_dir)
                                for name in files
                                if name.endswith((".json", ".md", ".csv"))
                            ],
                            reverse=True,
                        )
                        if relatorios:
                            st.success(f"? {len(relatorios)} relatórios gerados!")
                            for relatorio in relatorios[:10]:
                                st.markdown(f"- ?? **{relatorio}**  `{os.path.join(rel_dir, relatorio)}`")
                        else:
                            st.info("Nenhum relatório encontrado.")
                    else:
                        st.warning("A pasta workspace/reports/failures ainda não existe.")
                except Exception as exc:
                    st.error(f"Erro ao executar generate_failure_reports.py: {exc}")

    st.divider()
    st.markdown("<div class='tester-link-row'>", unsafe_allow_html=True)
    link_col_1, link_col_2, link_col_3 = st.columns(3)

    with link_col_1:
        if _action_button("Abrir Dashboard", style="open"):
            try:
                port = int(os.environ.get("VWAIT_DASHBOARD_PORT", "8504"))
                pronto = garantir_painel_streamlit(scripts["Abrir Dashboard"], port)
                webbrowser.open_new_tab(f"http://localhost:{port}")
                if pronto:
                    st.success(f"Dashboard pronto em http://localhost:{port}")
                else:
                    st.warning(f"Dashboard ainda inicializando em http://localhost:{port}")
            except Exception as exc:
                st.error(f"Falha ao abrir dashboard: {exc}")

    with link_col_2:
        if _action_button("Abrir Painel de Logs", style="open"):
            try:
                port = int(os.environ.get("VWAIT_LOGS_PANEL_PORT", "8505"))
                pronto = garantir_painel_streamlit(scripts["Abrir Painel de Logs"], port)
                webbrowser.open_new_tab(f"http://localhost:{port}")
                if pronto:
                    st.success(f"Painel de logs pronto em http://localhost:{port}")
                else:
                    st.warning(f"Painel de logs ainda inicializando em http://localhost:{port}")
            except Exception as exc:
                st.error(f"Falha ao abrir painel de logs: {exc}")

    with link_col_3:
        if _action_button("Abrir Controle de Falhas", style="open"):
            try:
                port = int(os.environ.get("VWAIT_FAILURE_CONTROL_PORT", "8506"))
                pronto = garantir_painel_streamlit(scripts["Abrir Controle de Falhas"], port)
                webbrowser.open_new_tab(f"http://localhost:{port}")
                if pronto:
                    st.success(f"Controle de falhas pronto em http://localhost:{port}")
                else:
                    st.warning(f"Controle de falhas ainda inicializando em http://localhost:{port}")
            except Exception as exc:
                st.error(f"Falha ao abrir controle de falhas: {exc}")

    st.markdown("</div>", unsafe_allow_html=True)


__all__ = [
    "render_collection_section",
    "render_management_and_execution_sections",
    "render_reports_and_links_section",
]
