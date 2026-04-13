from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from vwait.core.paths import (
    iter_tester_tests,
    tester_actions_path,
    tester_catalog_dir,
    tester_dataset_path,
    tester_system_collection_log_path,
    tester_system_exec_log_path,
)


def render_collection_section(
    *,
    base_dir: str,
    stop_flag_path: str,
    scripts: dict[str, str],
    bancadas: list[str],
    clean_display_text,
    salvar_resultado_parcial,
    resolver_teste_por_serial,
    capturar_logs_radio,
    resolver_pasta_logs_teste,
    abrir_pasta_local,
):
    st.subheader("Coletar Gestos")
    categoria = st.text_input("Categoria do Teste (ex: audio, video, bluetooth)", key="cat_coleta")
    nome_teste = st.text_input("Nome do Teste (ex: audio_1, bt_pareamento)", key="nome_coleta")

    serial_sel = None
    if bancadas:
        serial_sel = st.selectbox("Bancada/Dispositivo ADB", options=bancadas, index=0)
    else:
        st.info("Nenhum dispositivo ADB encontrado. Conecte o radio e clique em iniciar.")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        if st.button("Iniciar Coleta", use_container_width=True):
            if categoria and nome_teste:
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
                    cmd = [sys.executable, "-u", scripts["Coletar Teste"], categoria, nome_teste]
                    if serial_sel:
                        cmd += ["--serial", serial_sel]

                    st.session_state.proc_coleta = subprocess.Popen(
                        cmd,
                        cwd=base_dir,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                        env=env,
                    )
                    st.success(f"Coleta iniciada para {categoria}/{nome_teste}")
                else:
                    st.warning("Já existe uma coleta em andamento.")
            else:
                st.error("Preencha categoria e nome do teste antes de iniciar.")

    with col2:
        if st.button("Finalizar Coleta", use_container_width=True):
            proc = st.session_state.proc_coleta
            if proc:
                try:
                    with open(stop_flag_path, "w") as handle:
                        handle.write("stop")
                    st.warning("Toque na tela do rádio para capturar o print final...")
                    acoes_path = str(tester_actions_path(categoria, nome_teste))
                    timeout_s = 60
                    t0 = time.time()
                    while time.time() - t0 < timeout_s:
                        if os.path.exists(acoes_path):
                            break
                        if proc.poll() is not None:
                            break
                        time.sleep(1)

                    if os.path.exists(acoes_path):
                        st.success("Coleta finalizada com sucesso. Print final e ações salvos.")
                    else:
                        proc.wait(timeout=10)
                        if os.path.exists(acoes_path):
                            st.success("Coleta finalizada com sucesso. Print final e ações salvos.")
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
            else:
                st.info("Nenhuma coleta em andamento.")

    with col3:
        if st.button("Salvar Resultado Esperado", use_container_width=True):
            if categoria and nome_teste:
                ok, msg = salvar_resultado_parcial(categoria, nome_teste, serial_sel)
                if ok:
                    st.success(f"Resultado esperado salvo: {msg}")
                else:
                    st.error(msg)
            else:
                st.error("Informe categoria e nome do teste antes de salvar o esperado.")

    with col4:
        if st.button("Capturar Log do Radio", use_container_width=True):
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
        if st.button("Abrir Pasta de Logs", use_container_width=True):
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
            st_autorefresh(interval=1000, limit=None, key="coleta_refresh")

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
            logs_txt = clean_display_text("".join(lines[-200:]))
        except Exception:
            logs_txt = ""

        st.text_area("Toques e eventos", value=logs_txt, height=220)

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

    if st.button("Deletar Teste", use_container_width=True):
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

    if st.button("Processar Dataset", use_container_width=True):
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
    categoria_exec = st.text_input("Categoria do Teste", key="cat_exec")
    nome_teste_exec = st.text_input("Nome do Teste (deixe vazio para rodar todos)", key="nome_exec")
    st.markdown("**Execucao paralela por bancada**")

    execucoes_paralelas_config = []
    if bancadas:
        colunas_paralelas = st.columns(2)
        for idx, serial_bancada in enumerate(bancadas, start=1):
            with colunas_paralelas[(idx - 1) % 2]:
                st.caption(f"Bancada {idx}")
                st.caption(f"Serial: {serial_bancada}")
                categoria_exec_b = st.text_input(f"Categoria Bancada {idx}", key=f"cat_exec_b{idx}")
                nome_teste_exec_b = st.text_input(f"Teste Bancada {idx}", key=f"nome_exec_b{idx}")
                if categoria_exec_b.strip() and nome_teste_exec_b.strip():
                    execucoes_paralelas_config.append(
                        {
                            "categoria": categoria_exec_b.strip(),
                            "teste": nome_teste_exec_b.strip(),
                            "serial": serial_bancada,
                            "label": f"Bancada {idx}",
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
            executar_teste_unico = st.button("Executar Teste Unico", use_container_width=True)
        with btn_duplo_col:
            executar_duplo = st.button("Rodar Testes em Paralelo", key="executar_teste_duplo", use_container_width=True)

        if executar_teste_unico:
            serial_exec = serial_sel or (bancadas[0] if bancadas else None)
            ok_exec, msg_exec, processos = iniciar_execucoes_teste_unico(
                categoria_exec,
                nome_teste_exec,
                [serial_exec] if serial_exec else [],
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
            st_autorefresh(interval=1500, limit=None, key="execucao_unica_refresh")

        st.session_state["teste_em_execucao"] = existe_execucao_ativa
        if not existe_execucao_ativa:
            st.session_state["proc_execucao_unica"] = None
            st.session_state["execucao_unica_status"] = ""

        status_msg = "<br>".join(status_msgs) if status_msgs else "Nenhum teste em execucao."
        st.markdown(f"<div class='status-box'>{status_msg}</div>", unsafe_allow_html=True)

        if "teste_em_execucao" in st.session_state and st.session_state["teste_em_execucao"]:
            if not st.session_state.get("teste_pausado", False):
                st.markdown("<div class='pause-btn'>", unsafe_allow_html=True)
                if st.button("Pausar Teste", key="pause_teste", use_container_width=True):
                    with open(os.path.join(base_dir, "pause.flag"), "w") as handle:
                        handle.write("pause")
                    st.session_state["teste_pausado"] = True
                    st.warning("Execucao pausada.")
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='resume-btn'>", unsafe_allow_html=True)
                if st.button("Retomar Teste", key="resume_teste", use_container_width=True):
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
            executar_todos_categoria = st.button("Executar Todos da Categoria", use_container_width=True)

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
                                ["python", scripts["Executar Teste"], categoria_exec, teste],
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

    if st.button("Gerar Relatórios de Falhas (execução_log.json)", use_container_width=True):
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
        if st.button("Abrir Dashboard", use_container_width=True):
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
        if st.button("Abrir Painel de Logs", use_container_width=True):
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
        if st.button("Abrir Controle de Falhas", use_container_width=True):
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
