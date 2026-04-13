import json
import os
import time

import streamlit.components.v1 as components

from vwait.core.paths import root_path
from vwait.features.chat.ui.streamlit.navigation import (
    DASHBOARD_PORT,
    FAILURE_CONTROL_PORT,
    LOGS_PANEL_PORT,
    MENU_TESTER_PORT,
)
from vwait.features.chat.ui.streamlit.runtime import porta_local_ativa as _porta_local_ativa


def render_mapa_neural_ia() -> None:
    nodes = [
        {
            "id": "controller",
            "label": "IA Controladora",
            "role": "Orquestrador central",
            "detail": "Interpreta comandos, decide rotas e coordena os subagentes do projeto.",
            "x": 50,
            "y": 47,
            "kind": "core",
        },
        {
            "id": "voice",
            "label": "Voz Browser",
            "role": "Entrada por fala",
            "detail": "Captura comandos pelo microfone do navegador e envia para transcricao.",
            "x": 21,
            "y": 18,
            "kind": "input",
        },
        {
            "id": "intent",
            "label": "Intencao",
            "role": "Roteador semantico",
            "detail": "Transforma linguagem natural em acoes: executar, gravar, validar, logs e navegacao.",
            "x": 50,
            "y": 16,
            "kind": "agent",
        },
        {
            "id": "llm",
            "label": "LLM Local",
            "role": "Raciocinio assistido",
            "detail": "Usa Ollama e fallbacks para classificar comandos e responder conversas.",
            "x": 78,
            "y": 19,
            "kind": "agent",
        },
        {
            "id": "tester",
            "label": "Menu Tester",
            "role": "Agente executor",
            "detail": "Dispara testes, coletas, paralelismo e execucoes por categoria.",
            "x": 18,
            "y": 48,
            "kind": "agent",
        },
        {
            "id": "adb",
            "label": "ADB Runner",
            "role": "Ponte Android",
            "detail": "Conecta bancadas, envia toques, coleta screenshots e monitora dispositivos.",
            "x": 30,
            "y": 78,
            "kind": "device",
        },
        {
            "id": "hmi",
            "label": "Validador HMI",
            "role": "Agente visual",
            "detail": "Compara capturas reais contra a biblioteca GEI/Figma e gera status visual.",
            "x": 73,
            "y": 48,
            "kind": "agent",
        },
        {
            "id": "malagueta",
            "label": "Malagueta/scrcpy",
            "role": "Observador de tela",
            "detail": "Acompanha a tela do radio via scrcpy/ADB e grava capturas em Data/HMI_TESTE.",
            "x": 86,
            "y": 73,
            "kind": "device",
        },
        {
            "id": "figma",
            "label": "Biblioteca GEI",
            "role": "Memoria visual",
            "detail": "Guarda as telas base exportadas do Figma para matching e validacao.",
            "x": 64,
            "y": 84,
            "kind": "memory",
        },
        {
            "id": "logs",
            "label": "Painel de Logs",
            "role": "Agente observador",
            "detail": "Organiza logs do radio e apoia investigacao de comportamento.",
            "x": 9,
            "y": 70,
            "kind": "agent",
        },
        {
            "id": "failures",
            "label": "Controle de Falhas",
            "role": "Triagem",
            "detail": "Agrupa falhas, prepara evidencias e estrutura encaminhamentos.",
            "x": 9,
            "y": 29,
            "kind": "agent",
        },
        {
            "id": "dashboard",
            "label": "Dashboard",
            "role": "Supervisao",
            "detail": "Mostra status, execucoes e resultados para acompanhamento em tempo real.",
            "x": 90,
            "y": 34,
            "kind": "output",
        },
        {
            "id": "data",
            "label": "Data Lake",
            "role": "Memoria operacional",
            "detail": "Persistencia local de resultados, manifests, capturas, relatorios e caches.",
            "x": 50,
            "y": 93,
            "kind": "memory",
        },
    ]
    links = [
        ("controller", "voice"),
        ("controller", "intent"),
        ("controller", "llm"),
        ("controller", "tester"),
        ("controller", "hmi"),
        ("controller", "logs"),
        ("controller", "failures"),
        ("controller", "dashboard"),
        ("tester", "adb"),
        ("adb", "malagueta"),
        ("hmi", "malagueta"),
        ("hmi", "figma"),
        ("hmi", "data"),
        ("malagueta", "data"),
        ("tester", "data"),
        ("logs", "data"),
        ("failures", "dashboard"),
        ("data", "dashboard"),
    ]
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    links_json = json.dumps(links, ensure_ascii=False)
    components.html(
        f"""
        <div class="brain-shell">
          <div class="brain-orb brain-orb-a"></div>
          <div class="brain-orb brain-orb-b"></div>
          <section class="brain-hero">
            <div>
              <p class="eyebrow">Arquitetura Cognitiva VWAIT</p>
              <h1>Mapa Neural da IA</h1>
              <p class="hero-copy">
                Uma visao viva da IA controladora e dos subagentes que operam testes,
                logs, HMI, scrcpy, ADB, dashboards e memoria local do projeto.
              </p>
            </div>
            <div class="hero-badge">
              <span class="pulse-dot"></span>
              Sistema em orquestracao
            </div>
          </section>
          <section class="brain-stage" id="brain-stage">
            <svg class="brain-links" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"></svg>
            <div class="brain-grid"></div>
            <div class="brain-halo"></div>
            <div id="brain-nodes"></div>
          </section>
          <section class="brain-footer">
            <div class="detail-card">
              <p class="detail-kicker">Nodo em foco</p>
              <h2 id="detail-title">IA Controladora</h2>
              <p id="detail-role">Orquestrador central</p>
              <p id="detail-copy">Interpreta comandos, decide rotas e coordena os subagentes do projeto.</p>
            </div>
            <div class="signal-card"><strong>{len(nodes)}</strong><span>nodos cognitivos</span></div>
            <div class="signal-card"><strong>{len(links)}</strong><span>conexoes ativas</span></div>
            <div class="signal-card"><strong>0 CDN</strong><span>visual local</span></div>
          </section>
        </div>
        <style>
          * {{ box-sizing: border-box; }}
          body {{
            margin: 0;
            background: transparent;
            color: #eef6ff;
            font-family: "Aptos", "Segoe UI", sans-serif;
          }}
          .brain-shell {{
            position: relative;
            min-height: 860px;
            overflow: hidden;
            border: 1px solid rgba(119, 201, 255, 0.22);
            border-radius: 34px;
            padding: 34px;
            background:
              radial-gradient(circle at 18% 18%, rgba(39, 201, 255, 0.18), transparent 30%),
              radial-gradient(circle at 84% 24%, rgba(45, 255, 146, 0.13), transparent 29%),
              linear-gradient(145deg, rgba(4, 13, 26, 0.98), rgba(1, 6, 14, 0.96));
            box-shadow:
              inset 0 1px 0 rgba(255,255,255,.08),
              0 34px 90px rgba(0, 0, 0, .45);
          }}
          .brain-orb {{
            position: absolute;
            width: 360px;
            height: 360px;
            border-radius: 999px;
            filter: blur(38px);
            opacity: .34;
            pointer-events: none;
          }}
          .brain-orb-a {{ left: -100px; top: 130px; background: #0cc9ff; animation: drift 8s ease-in-out infinite alternate; }}
          .brain-orb-b {{ right: -120px; bottom: 70px; background: #1dff9b; animation: drift 10s ease-in-out infinite alternate-reverse; }}
          @keyframes drift {{
            from {{ transform: translate3d(0, 0, 0) scale(.95); }}
            to {{ transform: translate3d(42px, -24px, 0) scale(1.06); }}
          }}
          .brain-hero {{
            position: relative;
            z-index: 2;
            display: flex;
            justify-content: space-between;
            gap: 24px;
            align-items: flex-start;
            margin-bottom: 24px;
          }}
          .eyebrow {{
            margin: 0 0 8px;
            color: #5ee6ff;
            text-transform: uppercase;
            letter-spacing: .24em;
            font-size: 12px;
            font-weight: 800;
          }}
          h1 {{
            margin: 0;
            font-size: clamp(42px, 7vw, 82px);
            line-height: .88;
            letter-spacing: -.07em;
            background: linear-gradient(90deg, #f8fbff, #9eeaff 44%, #2cff98 88%);
            -webkit-background-clip: text;
            color: transparent;
          }}
          .hero-copy {{
            max-width: 720px;
            margin: 18px 0 0;
            color: rgba(226, 238, 255, .72);
            font-size: 17px;
            line-height: 1.65;
          }}
          .hero-badge {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 13px 16px;
            border: 1px solid rgba(98, 255, 183, .28);
            border-radius: 999px;
            background: rgba(7, 22, 32, .68);
            color: #baffdc;
            font-size: 13px;
            font-weight: 800;
            white-space: nowrap;
          }}
          .pulse-dot {{
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #2cff98;
            box-shadow: 0 0 0 0 rgba(44,255,152,.72);
            animation: pulse 1.6s ease-out infinite;
          }}
          @keyframes pulse {{
            to {{ box-shadow: 0 0 0 14px rgba(44,255,152,0); }}
          }}
          .brain-stage {{
            position: relative;
            height: 560px;
            border: 1px solid rgba(145, 215, 255, .18);
            border-radius: 30px;
            overflow: hidden;
            background:
              radial-gradient(circle at center, rgba(66, 178, 255, .18), transparent 35%),
              linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.01));
          }}
          .brain-grid {{
            position: absolute;
            inset: 0;
            opacity: .18;
            background-image:
              linear-gradient(rgba(118, 202, 255, .18) 1px, transparent 1px),
              linear-gradient(90deg, rgba(118, 202, 255, .18) 1px, transparent 1px);
            background-size: 42px 42px;
            mask-image: radial-gradient(circle at center, black, transparent 72%);
          }}
          .brain-halo {{
            position: absolute;
            width: 340px;
            height: 340px;
            left: calc(50% - 170px);
            top: calc(47% - 170px);
            border-radius: 999px;
            border: 1px dashed rgba(111, 225, 255, .34);
            box-shadow: 0 0 90px rgba(21, 220, 255, .18);
            animation: spin 18s linear infinite;
          }}
          @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
          .brain-links {{
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            z-index: 1;
          }}
          .brain-link {{
            stroke: rgba(94, 230, 255, .38);
            stroke-width: .22;
            filter: drop-shadow(0 0 5px rgba(94,230,255,.34));
          }}
          .brain-link.hot {{
            stroke: rgba(44, 255, 152, .74);
            stroke-width: .32;
          }}
          .node {{
            position: absolute;
            z-index: 3;
            width: 132px;
            min-height: 76px;
            transform: translate(-50%, -50%);
            padding: 13px 13px 12px;
            border-radius: 22px;
            border: 1px solid rgba(153, 221, 255, .25);
            background: linear-gradient(180deg, rgba(18, 31, 54, .92), rgba(6, 13, 27, .88));
            box-shadow:
              inset 0 1px 0 rgba(255,255,255,.08),
              0 18px 36px rgba(0,0,0,.28);
            cursor: pointer;
            transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease;
          }}
          .node::before {{
            content: "";
            position: absolute;
            width: 9px;
            height: 9px;
            right: 14px;
            top: 14px;
            border-radius: 999px;
            background: var(--accent);
            box-shadow: 0 0 18px var(--accent);
          }}
          .node:hover, .node.active {{
            transform: translate(-50%, -50%) scale(1.07);
            border-color: var(--accent);
            box-shadow:
              0 0 0 1px color-mix(in srgb, var(--accent), transparent 35%),
              0 22px 46px rgba(0,0,0,.34),
              0 0 44px color-mix(in srgb, var(--accent), transparent 58%);
          }}
          .node.core {{
            width: 190px;
            min-height: 112px;
            border-radius: 30px;
            background:
              radial-gradient(circle at 28% 12%, rgba(255,255,255,.16), transparent 34%),
              linear-gradient(145deg, rgba(18, 72, 102, .98), rgba(5, 24, 35, .94));
          }}
          .node-title {{
            display: block;
            color: #f8fbff;
            font-weight: 900;
            line-height: 1.02;
            letter-spacing: -.03em;
            font-size: 15px;
            padding-right: 16px;
          }}
          .node-role {{
            display: block;
            margin-top: 8px;
            color: rgba(218, 234, 255, .62);
            font-size: 11px;
            line-height: 1.25;
            text-transform: uppercase;
            letter-spacing: .08em;
          }}
          .core .node-title {{ font-size: 21px; }}
          .core .node-role {{ font-size: 12px; color: #9bf7ff; }}
          .detail-card, .signal-card {{
            border: 1px solid rgba(145, 215, 255, .16);
            border-radius: 24px;
            background: rgba(6, 14, 27, .72);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
          }}
          .brain-footer {{
            position: relative;
            z-index: 2;
            display: grid;
            grid-template-columns: minmax(0, 1.7fr) repeat(3, minmax(150px, .55fr));
            gap: 16px;
            margin-top: 18px;
          }}
          .detail-card {{ padding: 20px 22px; }}
          .detail-kicker {{
            margin: 0 0 8px;
            font-size: 11px;
            letter-spacing: .18em;
            text-transform: uppercase;
            color: #5ee6ff;
            font-weight: 900;
          }}
          .detail-card h2 {{
            margin: 0;
            font-size: 30px;
            letter-spacing: -.04em;
          }}
          #detail-role {{
            margin: 8px 0;
            color: #2cff98;
            font-weight: 900;
          }}
          #detail-copy {{
            margin: 0;
            color: rgba(226, 238, 255, .72);
            line-height: 1.55;
          }}
          .signal-card {{
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 18px;
            min-height: 122px;
          }}
          .signal-card strong {{
            color: #f8fbff;
            font-size: 34px;
            line-height: 1;
          }}
          .signal-card span {{
            margin-top: 10px;
            color: rgba(226, 238, 255, .6);
            text-transform: uppercase;
            letter-spacing: .1em;
            font-size: 11px;
            font-weight: 800;
          }}
          @media (max-width: 880px) {{
            .brain-shell {{ padding: 22px; min-height: 980px; }}
            .brain-hero {{ flex-direction: column; }}
            .brain-stage {{ height: 640px; }}
            .node {{ width: 116px; font-size: 12px; }}
            .brain-footer {{ grid-template-columns: 1fr; }}
          }}
        </style>
        <script>
          const nodes = {nodes_json};
          const links = {links_json};
          const accents = {{
            core: "#5ee6ff",
            agent: "#2cff98",
            input: "#f7c96b",
            device: "#ff7f5f",
            memory: "#a990ff",
            output: "#77d7ff"
          }};
          const nodeRoot = document.getElementById("brain-nodes");
          const svg = document.querySelector(".brain-links");
          const title = document.getElementById("detail-title");
          const role = document.getElementById("detail-role");
          const copy = document.getElementById("detail-copy");
          const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));

          function renderLinks(activeId) {{
            svg.innerHTML = "";
            links.forEach(([from, to]) => {{
              const a = byId[from];
              const b = byId[to];
              if (!a || !b) return;
              const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
              line.setAttribute("x1", a.x);
              line.setAttribute("y1", a.y);
              line.setAttribute("x2", b.x);
              line.setAttribute("y2", b.y);
              line.setAttribute("class", "brain-link" + (activeId && (activeId === from || activeId === to) ? " hot" : ""));
              svg.appendChild(line);
            }});
          }}

          function focusNode(node) {{
            document.querySelectorAll(".node").forEach((el) => el.classList.toggle("active", el.dataset.nodeId === node.id));
            title.textContent = node.label;
            role.textContent = node.role;
            copy.textContent = node.detail;
            renderLinks(node.id);
          }}

          nodes.forEach((node, index) => {{
            const el = document.createElement("button");
            el.type = "button";
            el.className = "node " + node.kind;
            el.dataset.nodeId = node.id;
            el.style.left = node.x + "%";
            el.style.top = node.y + "%";
            el.style.setProperty("--accent", accents[node.kind] || "#5ee6ff");
            el.style.animation = `nodeFloat ${{5 + (index % 5) * .6}}s ease-in-out ${{index * .08}}s infinite alternate`;
            el.innerHTML = `<span class="node-title">${{node.label}}</span><span class="node-role">${{node.role}}</span>`;
            el.addEventListener("mouseenter", () => focusNode(node));
            el.addEventListener("focus", () => focusNode(node));
            nodeRoot.appendChild(el);
          }});
          const style = document.createElement("style");
          style.textContent = `@keyframes nodeFloat {{ from {{ margin-top: -3px; }} to {{ margin-top: 7px; }} }}`;
          document.head.appendChild(style);
          renderLinks("controller");
          focusNode(byId.controller);
        </script>
        """,
        height=900,
        scrolling=False,
    )


def render_mapa_neural_ia_coder() -> None:
    nodes = [
        {"id": "kernel", "label": "zuri.kernel", "role": "IA controladora", "detail": "Nucleo que decide rota, delega agentes e sincroniza estado da interface.", "x": 50, "y": 45, "w": 1.45, "group": "core"},
        {"id": "intent", "label": "intent.parser", "role": "classificacao", "detail": "Normaliza linguagem natural e converte comandos em intencoes operacionais.", "x": 36, "y": 22, "w": 1.0, "group": "logic"},
        {"id": "router", "label": "nav.router", "role": "roteamento", "detail": "Abre paginas, aciona fluxos e controla a navegacao do operador.", "x": 54, "y": 20, "w": 1.0, "group": "logic"},
        {"id": "llm", "label": "ollama.llm", "role": "raciocinio", "detail": "Fallback semantico local para entender comandos ambigos e responder contexto.", "x": 68, "y": 25, "w": 1.05, "group": "logic"},
        {"id": "voice", "label": "browser.stt", "role": "voz", "detail": "Entrada de comando por audio via navegador, sem PyAudio.", "x": 22, "y": 18, "w": 0.9, "group": "input"},
        {"id": "chat", "label": "chat.ui", "role": "console", "detail": "Campo principal de comando e historico do operador.", "x": 18, "y": 39, "w": 0.95, "group": "ui"},
        {"id": "tester", "label": "tester.panel", "role": "execucao", "detail": "Menu Tester para iniciar, retomar e executar lotes de testes.", "x": 27, "y": 61, "w": 1.0, "group": "agent"},
        {"id": "queue", "label": "run.queue", "role": "fila", "detail": "Fila de execucoes ativas e finalizacoes pendentes.", "x": 38, "y": 72, "w": 0.9, "group": "runtime"},
        {"id": "adb", "label": "adb.bridge", "role": "android", "detail": "Camada de comunicacao com bancadas e dispositivos Android.", "x": 52, "y": 76, "w": 1.05, "group": "device"},
        {"id": "bench", "label": "bench.pool", "role": "bancadas", "detail": "Serializa bancadas conectadas e seleciona alvos de execucao.", "x": 66, "y": 75, "w": 0.95, "group": "device"},
        {"id": "scrcpy", "label": "scrcpy.malagueta", "role": "espelho", "detail": "Janela do radio e origem visual para captura durante testes HMI.", "x": 78, "y": 61, "w": 1.1, "group": "device"},
        {"id": "touch", "label": "touch.monitor", "role": "eventos", "detail": "Monitora clique/toque/mudanca visual e grava screenshots.", "x": 80, "y": 42, "w": 1.0, "group": "agent"},
        {"id": "hmi", "label": "hmi.validator", "role": "comparacao", "detail": "Orquestra captura, biblioteca GEI e comparacao automatica.", "x": 68, "y": 47, "w": 1.18, "group": "agent"},
        {"id": "engine", "label": "hmi.engine", "role": "diff engine", "detail": "Calcula similaridade, pixel match, grids e status HMI.", "x": 64, "y": 34, "w": 0.95, "group": "logic"},
        {"id": "figma", "label": "gei.library", "role": "baseline", "detail": "Pasta GEI/Figma com referencias de tela para matching.", "x": 82, "y": 25, "w": 0.9, "group": "memory"},
        {"id": "vision", "label": "visual.qa", "role": "qa visual", "detail": "Pipeline complementar de classificacao e validacao visual.", "x": 88, "y": 35, "w": 0.85, "group": "logic"},
        {"id": "shots", "label": "screenshot.store", "role": "capturas", "detail": "Cache de capturas ao vivo, normalizadas e nativas.", "x": 67, "y": 88, "w": 0.9, "group": "memory"},
        {"id": "hmiteste", "label": "Data/HMI_TESTE", "role": "evidencias", "detail": "Pasta permanente com screenshots capturados da malagueta/ADB.", "x": 84, "y": 84, "w": 0.9, "group": "memory"},
        {"id": "manifest", "label": "manifest.jsonl", "role": "timeline", "detail": "Linha do tempo append-only de capturas e eventos.", "x": 49, "y": 91, "w": 0.78, "group": "memory"},
        {"id": "reports", "label": "report.builder", "role": "relatorio", "detail": "Consolida resultados em payloads e relatorios exportaveis.", "x": 29, "y": 86, "w": 0.85, "group": "output"},
        {"id": "dashboard", "label": "dashboard.live", "role": "observabilidade", "detail": "Mostra status, capturas recentes e execucoes em andamento.", "x": 18, "y": 75, "w": 0.95, "group": "output"},
        {"id": "logs", "label": "logs.panel", "role": "telemetria", "detail": "Leitura e analise de logs do radio.", "x": 12, "y": 55, "w": 0.85, "group": "output"},
        {"id": "failures", "label": "failure.control", "role": "triagem", "detail": "Agrupa falhas, evidencias e fluxo de encaminhamento.", "x": 12, "y": 27, "w": 0.85, "group": "output"},
        {"id": "cache", "label": "hmi.cache", "role": "estado", "detail": "Persistencia local de indices, results.json e estados do monitor.", "x": 50, "y": 62, "w": 0.9, "group": "memory"},
        {"id": "streamlit", "label": "streamlit.host", "role": "runtime UI", "detail": "Shell que hospeda as paginas e iframes internos.", "x": 35, "y": 38, "w": 0.95, "group": "ui"},
        {"id": "autoheal", "label": "process.guard", "role": "anti-duplicacao", "detail": "Evita monitores duplicados e recicla processos presos.", "x": 43, "y": 52, "w": 0.85, "group": "runtime"},
        {"id": "dataset", "label": "dataset.pipe", "role": "pre-process", "detail": "Processa capturas e artefatos para execucoes futuras.", "x": 25, "y": 48, "w": 0.82, "group": "runtime"},
    ]
    links = [
        ["kernel", "intent"], ["kernel", "router"], ["kernel", "llm"], ["kernel", "chat"], ["kernel", "streamlit"],
        ["kernel", "tester"], ["kernel", "hmi"], ["kernel", "dashboard"], ["kernel", "logs"], ["kernel", "failures"],
        ["voice", "intent"], ["chat", "intent"], ["intent", "llm"], ["intent", "router"], ["router", "dashboard"],
        ["router", "logs"], ["router", "failures"], ["router", "tester"], ["router", "hmi"], ["streamlit", "chat"],
        ["streamlit", "dashboard"], ["streamlit", "logs"], ["streamlit", "failures"], ["streamlit", "hmi"],
        ["tester", "queue"], ["tester", "adb"], ["tester", "dataset"], ["tester", "reports"], ["queue", "adb"],
        ["adb", "bench"], ["adb", "scrcpy"], ["bench", "touch"], ["scrcpy", "touch"], ["touch", "hmi"],
        ["touch", "shots"], ["touch", "hmiteste"], ["touch", "manifest"], ["hmi", "engine"], ["hmi", "figma"],
        ["hmi", "cache"], ["hmi", "shots"], ["hmi", "reports"], ["engine", "figma"], ["engine", "vision"],
        ["engine", "cache"], ["figma", "cache"], ["vision", "reports"], ["shots", "hmiteste"], ["shots", "manifest"],
        ["manifest", "reports"], ["reports", "dashboard"], ["cache", "dashboard"], ["cache", "autoheal"],
        ["autoheal", "touch"], ["autoheal", "hmi"], ["autoheal", "queue"], ["logs", "failures"], ["failures", "reports"],
        ["dataset", "cache"], ["dataset", "reports"], ["adb", "logs"], ["scrcpy", "dashboard"],
    ]
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    links_json = json.dumps(links, ensure_ascii=False)
    def _map_panel_online(port: int | None = None, default: bool = True) -> bool:
        if port is None:
            return default
        try:
            return _porta_local_ativa(int(port), timeout_s=0.05)
        except Exception:
            return False

    hmi_manifest_path = root_path("Data", "HMI_TESTE", "manifest.jsonl")
    try:
        hmi_recent = os.path.exists(hmi_manifest_path) and (time.time() - os.path.getmtime(hmi_manifest_path) < 300)
    except Exception:
        hmi_recent = False
    panel_states = [
        {"id": "control", "label": "control.plane", "node": "kernel", "online": True, "mode": "local"},
        {"id": "chat", "label": "chat.ui", "node": "chat", "online": True, "mode": "streamlit"},
        {"id": "tester", "label": "menu.tester", "node": "tester", "online": _map_panel_online(globals().get("MENU_TESTER_PORT", 8503), False), "mode": "port 8503"},
        {"id": "dashboard", "label": "dashboard.live", "node": "dashboard", "online": _map_panel_online(globals().get("DASHBOARD_PORT", 8504), False), "mode": "port 8504"},
        {"id": "logs", "label": "logs.panel", "node": "logs", "online": _map_panel_online(globals().get("LOGS_PANEL_PORT", 8505), False), "mode": "port 8505"},
        {"id": "failures", "label": "failure.control", "node": "failures", "online": _map_panel_online(globals().get("FAILURE_CONTROL_PORT", 8506), False), "mode": "port 8506"},
        {"id": "hmi", "label": "hmi.capture", "node": "hmi", "online": hmi_recent, "mode": "Data/HMI_TESTE"},
    ]
    panel_states_json = json.dumps(panel_states, ensure_ascii=False)
    html = r"""
    <div class="ops-map">
      <div class="scanline"></div>
      <section class="graph-card">
        <canvas id="ops-canvas"></canvas>
        <div class="graph-tools">
          <button type="button" id="graph-fit">fit</button>
          <button type="button" id="graph-zoom-out">-</button>
          <button type="button" id="graph-zoom-in">+</button>
          <button type="button" id="graph-expand">expand</button>
        </div>
        <div class="agent-bus" aria-label="fluxo operacional de agentes">
          <div class="bus-header">
            <span class="bus-pulse"></span>
            <span>agent bus</span>
            <code id="bus-clock">sync</code>
          </div>
          <div id="agent-bus-lines" class="bus-lines"></div>
          <div id="panel-state-strip" class="panel-state-strip"></div>
        </div>
      </section>
    </div>
    <style>
      :root {
        --paper: #050505;
        --ink: #f1efe7;
        --muted: rgba(241,239,231,.58);
        --hair: rgba(241,239,231,.14);
        --hair-strong: rgba(241,239,231,.3);
        --amber: #c8a968;
      }
      body {
        margin: 0;
        background: transparent;
        color: var(--ink);
        font-family: "JetBrains Mono", "Cascadia Code", "Consolas", monospace;
        overflow: hidden;
      }
      .ops-map {
        position: relative;
        min-height: 760px;
        overflow: hidden;
        border: 0;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
        padding: 0;
      }
      .ops-map::before {
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        opacity: .16;
        background-image:
          linear-gradient(rgba(255,255,255,.14) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,.14) 1px, transparent 1px);
        background-size: 48px 48px;
        mask-image: radial-gradient(circle at center, black, transparent 82%);
      }
      .scanline {
        position: absolute;
        inset: -40% 0 auto;
        height: 42%;
        background: linear-gradient(180deg, transparent, rgba(255,255,255,.035), transparent);
        transform: rotate(-8deg);
        animation: scan 7s linear infinite;
        pointer-events: none;
      }
      @keyframes scan {
        from { top: -44%; }
        to { top: 110%; }
      }
      .graph-card {
        position: relative;
        z-index: 2;
        min-height: 760px;
        overflow: hidden;
        cursor: grab;
        user-select: none;
        touch-action: none;
        border: 1px solid rgba(118,156,228,.20);
        border-radius: 22px;
        background:
          radial-gradient(circle at 22% 18%, rgba(77, 109, 150, .16), transparent 34%),
          radial-gradient(circle at 78% 78%, rgba(200, 169, 104, .05), transparent 30%),
          linear-gradient(135deg, rgba(5, 12, 22, .98), rgba(2, 5, 10, .98));
        box-shadow:
          inset 0 1px 0 rgba(255,255,255,.04),
          0 18px 42px rgba(0,0,0,.34);
      }
      .graph-card.dragging {
        cursor: grabbing;
      }
      #ops-canvas {
        width: 100%;
        height: 760px;
        display: block;
      }
      .graph-tools {
        position: absolute;
        top: 14px;
        right: 14px;
        z-index: 3;
        display: flex;
        gap: 8px;
        padding: 8px;
        border: 1px solid var(--hair);
        border-radius: 16px;
        background: rgba(0,0,0,.58);
        backdrop-filter: blur(12px);
      }
      .graph-tools button {
        min-width: 42px;
        height: 32px;
        border: 1px solid rgba(241,239,231,.18);
        border-radius: 11px;
        background: rgba(241,239,231,.045);
        color: rgba(241,239,231,.82);
        font-family: "JetBrains Mono", "Cascadia Code", "Consolas", monospace;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: .06em;
        text-transform: uppercase;
        cursor: pointer;
      }
      .graph-tools button:hover {
        border-color: rgba(200,169,104,.72);
        color: var(--ink);
        background: rgba(200,169,104,.12);
      }
      .ops-map.expanded {
        min-height: 1080px;
      }
      .ops-map.expanded .graph-card {
        min-height: 1080px;
      }
      .ops-map.expanded #ops-canvas {
        height: 1080px;
      }
      .graph-card:fullscreen {
        width: 100vw;
        height: 100vh;
        min-height: 100vh;
        border-radius: 0;
      }
      .graph-card:fullscreen #ops-canvas {
        width: 100vw;
        height: 100vh;
      }
      .graph-card:fullscreen .graph-tools {
        top: 20px;
        right: 20px;
      }
      .agent-bus {
        position: absolute;
        right: 16px;
        bottom: 16px;
        z-index: 4;
        width: min(390px, calc(100% - 32px));
        padding: 12px;
        border: 1px solid rgba(241,239,231,.14);
        border-radius: 18px;
        background:
          linear-gradient(180deg, rgba(2,7,13,.72), rgba(0,0,0,.82)),
          radial-gradient(circle at 18% 0%, rgba(200,169,104,.11), transparent 42%);
        box-shadow:
          inset 0 1px 0 rgba(255,255,255,.05),
          0 18px 38px rgba(0,0,0,.42);
        backdrop-filter: blur(14px);
        pointer-events: none;
      }
      .bus-header {
        display: flex;
        align-items: center;
        gap: 9px;
        color: rgba(241,239,231,.82);
        font-size: 10px;
        font-weight: 900;
        letter-spacing: .18em;
        text-transform: uppercase;
      }
      .bus-header code {
        margin-left: auto;
        color: rgba(200,169,104,.82);
        font-size: 9px;
        letter-spacing: .08em;
      }
      .bus-pulse {
        width: 7px;
        height: 7px;
        border-radius: 999px;
        background: var(--amber);
        box-shadow: 0 0 0 0 rgba(200,169,104,.7);
        animation: pulseOut 1.6s infinite;
      }
      @keyframes pulseOut {
        0% { box-shadow: 0 0 0 0 rgba(200,169,104,.72); }
        100% { box-shadow: 0 0 0 13px rgba(200,169,104,0); }
      }
      .bus-lines {
        display: grid;
        gap: 7px;
        margin-top: 12px;
      }
      .bus-line {
        position: relative;
        overflow: hidden;
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 10px;
        padding: 8px 10px;
        border: 1px solid rgba(241,239,231,.11);
        border-radius: 12px;
        background: rgba(255,255,255,.025);
        color: rgba(241,239,231,.68);
        font-size: 10px;
      }
      .bus-line::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 -55%;
        width: 52%;
        background: linear-gradient(90deg, transparent, rgba(200,169,104,.16), transparent);
        transform: skewX(-18deg);
      }
      .bus-line.live {
        border-color: rgba(200,169,104,.42);
        background: rgba(200,169,104,.055);
        color: rgba(241,239,231,.92);
      }
      .bus-line.live::before {
        animation: busSweep 3.6s cubic-bezier(.22, 1, .36, 1) infinite;
      }
      .bus-line.locked {
        border-color: rgba(200,169,104,.34);
        background: rgba(200,169,104,.045);
      }
      .bus-line.locked::before {
        display: none;
      }
      @keyframes busSweep {
        from { left: -55%; }
        to { left: 118%; }
      }
      .bus-path {
        position: relative;
        z-index: 1;
        min-width: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .bus-status {
        position: relative;
        z-index: 1;
        color: rgba(200,169,104,.84);
        font-size: 9px;
        letter-spacing: .08em;
        text-transform: uppercase;
      }
      .panel-state-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 10px;
      }
      .panel-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 8px;
        border: 1px solid rgba(241,239,231,.10);
        border-radius: 999px;
        color: rgba(241,239,231,.58);
        background: rgba(255,255,255,.02);
        font-size: 9px;
        letter-spacing: .04em;
      }
      .panel-chip::before {
        content: "";
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: rgba(241,239,231,.22);
      }
      .panel-chip.online {
        color: rgba(241,239,231,.82);
        border-color: rgba(200,169,104,.26);
        background: rgba(200,169,104,.055);
      }
      .panel-chip.online::before {
        background: var(--amber);
        box-shadow: 0 0 12px rgba(200,169,104,.72);
      }
      @media (max-width: 980px) {
        .ops-map,
        .graph-card,
        #ops-canvas { min-height: 720px; height: 720px; }
        .agent-bus {
          left: 12px;
          right: 12px;
          bottom: 12px;
          width: auto;
        }
      }
    </style>
    <script>
      const nodes = __NODES__;
      const rawLinks = __LINKS__;
      const panelStates = __PANEL_STATES__;
      const shell = document.querySelector(".ops-map");
      const graphCard = document.querySelector(".graph-card");
      const canvas = document.getElementById("ops-canvas");
      const ctx = canvas.getContext("2d");
      const fitBtn = document.getElementById("graph-fit");
      const zoomInBtn = document.getElementById("graph-zoom-in");
      const zoomOutBtn = document.getElementById("graph-zoom-out");
      const expandBtn = document.getElementById("graph-expand");
      const busLinesEl = document.getElementById("agent-bus-lines");
      const panelStateEl = document.getElementById("panel-state-strip");
      const busClockEl = document.getElementById("bus-clock");
      const colors = {
        core: "#f1efe7",
        logic: "#bbb7ab",
        input: "#aaa69a",
        ui: "#d0c9b7",
        agent: "#d8caa7",
        runtime: "#a9a9a0",
        device: "#c0b7a0",
        memory: "#b6b1a6",
        output: "#d3c4a2"
      };
      const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
      const FLOW_INTERVAL_MS = 3900;
      const FLOW_TAIL = .28;
      const AMBIENT_FLOW_COUNT = 6;
      const links = rawLinks.map(([a, b]) => ({ a: byId[a], b: byId[b], phase: Math.random(), speed: .00042 + Math.random() * .00062 })).filter((l) => l.a && l.b);
      const baseFlows = [
        { from: "chat", to: "intent", label: "command.ingest", status: "parse" },
        { from: "intent", to: "router", label: "intent.route", status: "route" },
        { from: "router", to: "tester", label: "tester.dispatch", status: "exec" },
        { from: "tester", to: "adb", label: "adb.session", status: "device" },
        { from: "adb", to: "scrcpy", label: "malagueta.mirror", status: "stream" },
        { from: "scrcpy", to: "touch", label: "click.capture", status: "event" },
        { from: "touch", to: "hmi", label: "hmi.validate", status: "compare" },
        { from: "hmi", to: "engine", label: "diff.engine", status: "score" },
        { from: "hmi", to: "shots", label: "screenshot.store", status: "persist" },
        { from: "shots", to: "hmiteste", label: "Data/HMI_TESTE", status: "archive" },
        { from: "manifest", to: "reports", label: "timeline.report", status: "emit" },
        { from: "reports", to: "dashboard", label: "dashboard.sync", status: "view" },
        { from: "logs", to: "failures", label: "log.triage", status: "risk" },
        { from: "failures", to: "reports", label: "failure.evidence", status: "trace" },
      ];
      const runtimeFlowMap = {
        tester: [
          { from: "kernel", to: "tester", label: "menu.tester.online", status: "runtime" },
          { from: "tester", to: "queue", label: "run.queue.watch", status: "queue" },
          { from: "tester", to: "adb", label: "adb.bridge.ready", status: "device" },
        ],
        dashboard: [
          { from: "kernel", to: "dashboard", label: "dashboard.live.online", status: "runtime" },
          { from: "reports", to: "dashboard", label: "report.feed", status: "view" },
          { from: "cache", to: "dashboard", label: "cache.hydrate", status: "state" },
        ],
        logs: [
          { from: "kernel", to: "logs", label: "logs.panel.online", status: "runtime" },
          { from: "adb", to: "logs", label: "radio.log.stream", status: "logcat" },
          { from: "logs", to: "failures", label: "failure.signal", status: "triage" },
        ],
        failures: [
          { from: "kernel", to: "failures", label: "failure.control.online", status: "runtime" },
          { from: "logs", to: "failures", label: "log.triage", status: "risk" },
          { from: "failures", to: "reports", label: "evidence.bundle", status: "trace" },
        ],
        hmi: [
          { from: "kernel", to: "hmi", label: "hmi.capture.recent", status: "runtime" },
          { from: "scrcpy", to: "touch", label: "malagueta.clicks", status: "event" },
          { from: "touch", to: "hmi", label: "screenshot.compare", status: "compare" },
          { from: "hmi", to: "engine", label: "diff.engine", status: "score" },
          { from: "hmi", to: "shots", label: "capture.cache", status: "persist" },
          { from: "shots", to: "hmiteste", label: "Data/HMI_TESTE", status: "archive" },
          { from: "shots", to: "manifest", label: "manifest.jsonl", status: "timeline" },
        ],
      };
      function uniqueFlows(flows) {
        const seen = new Set();
        return flows.filter((flow) => {
          const key = `${flow.from}->${flow.to}:${flow.label}`;
          if (seen.has(key)) return false;
          seen.add(key);
          return byId[flow.from] && byId[flow.to];
        });
      }
      const runtimePanels = panelStates.filter((panel) => panel.online && !["control", "chat"].includes(panel.id));
      const runtimeMode = runtimePanels.length > 0;
      const runtimeFlows = uniqueFlows(runtimePanels.flatMap((panel) => runtimeFlowMap[panel.id] || [
        { from: "kernel", to: panel.node, label: `${panel.label}.online`, status: panel.mode || "runtime" }
      ]));
      const agentFlows = (runtimeMode && runtimeFlows.length ? runtimeFlows : uniqueFlows(baseFlows));
      let w = 1, h = 1, active = byId.kernel, mouse = { x: -9999, y: -9999 };
      let camera = { x: 0, y: 0, scale: 1 };
      let dragging = false;
      let dragStart = { x: 0, y: 0, camX: 0, camY: 0 };
      let activeFlowIndex = 0;
      let lastFlowTick = 0;
      let flowProgress = 0;

      function resize() {
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        w = Math.max(640, rect.width);
        h = Math.max(620, rect.height);
        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        nodes.forEach((n) => {
          n.tx = (n.x / 100) * w;
          n.ty = (n.y / 100) * h;
          if (n.px == null) {
            n.px = n.tx + (Math.random() - .5) * 26;
            n.py = n.ty + (Math.random() - .5) * 26;
            n.vx = 0;
            n.vy = 0;
          }
        });
      }

      function screenToWorld(x, y) {
        return {
          x: (x - camera.x) / camera.scale,
          y: (y - camera.y) / camera.scale
        };
      }

      function clampCamera() {
        camera.scale = Math.max(.42, Math.min(3.2, camera.scale));
      }

      function zoomAt(screenX, screenY, factor) {
        const before = screenToWorld(screenX, screenY);
        camera.scale *= factor;
        clampCamera();
        camera.x = screenX - before.x * camera.scale;
        camera.y = screenY - before.y * camera.scale;
      }

      function fitGraph() {
        if (!nodes.length) return;
        const pad = 84;
        const xs = nodes.map((n) => n.px ?? n.tx ?? 0);
        const ys = nodes.map((n) => n.py ?? n.ty ?? 0);
        const minX = Math.min(...xs) - pad;
        const maxX = Math.max(...xs) + pad;
        const minY = Math.min(...ys) - pad;
        const maxY = Math.max(...ys) + pad;
        const graphW = Math.max(1, maxX - minX);
        const graphH = Math.max(1, maxY - minY);
        camera.scale = Math.min(2.4, Math.max(.45, Math.min(w / graphW, h / graphH)));
        camera.x = (w - graphW * camera.scale) / 2 - minX * camera.scale;
        camera.y = (h - graphH * camera.scale) / 2 - minY * camera.scale;
      }

      function setActive(node) {
        active = node || active;
      }

      function formatFlow(flow) {
        return `${flow.from} -> ${flow.to}  // ${flow.label}`;
      }

      function renderAgentBus() {
        const activeIndex = agentFlows.length ? activeFlowIndex % agentFlows.length : 0;
        const visibleFlows = runtimeMode
          ? agentFlows.slice(0, 7)
          : agentFlows.length
            ? Array.from({ length: Math.min(7, agentFlows.length) }, (_, offset) => agentFlows[(activeIndex + offset) % agentFlows.length])
            : [];
        const liveCount = runtimeMode ? visibleFlows.length : Math.min(AMBIENT_FLOW_COUNT, visibleFlows.length);
        busLinesEl.innerHTML = visibleFlows.map((flow, index) => {
          const isLive = index < liveCount;
          return `
            <div class="bus-line ${isLive ? "live" : ""} ${runtimeMode ? "locked" : ""}">
              <span class="bus-path">${formatFlow(flow)}</span>
              <span class="bus-status">${runtimeMode ? "real" : isLive ? flow.status : "standby"}</span>
            </div>
          `;
        }).join("");
        panelStateEl.innerHTML = panelStates.map((panel) => `
          <span class="panel-chip ${panel.online ? "online" : ""}">${panel.label}</span>
        `).join("");
        const now = new Date();
        busClockEl.textContent = `${runtimeMode ? "runtime.lock" : "ambient.flow"} t+${String(now.getSeconds()).padStart(2, "0")}.${String(Math.floor(now.getMilliseconds() / 10)).padStart(2, "0")}`;
      }

      function updateAgentFlow(timestamp) {
        if (!agentFlows.length) return;
        if (runtimeMode) {
          flowProgress = .72;
          if (!lastFlowTick || timestamp - lastFlowTick > 2600) {
            renderAgentBus();
            lastFlowTick = timestamp;
          }
          return;
        }
        if (!lastFlowTick || timestamp - lastFlowTick > FLOW_INTERVAL_MS) {
          activeFlowIndex = (activeFlowIndex + 1) % agentFlows.length;
          const flow = agentFlows[activeFlowIndex];
          setActive(byId[flow.to] || byId[flow.from]);
          renderAgentBus();
          lastFlowTick = timestamp;
        }
        const elapsed = Math.max(0, timestamp - lastFlowTick);
        const linear = Math.min(1, elapsed / FLOW_INTERVAL_MS);
        flowProgress = 1 - Math.pow(1 - linear, 3);
      }

      function activeFlowEntries() {
        if (!agentFlows.length) return [];
        if (runtimeMode) {
          return agentFlows.map((flow, slot) => ({ flow, slot, locked: true, progress: .56 + (slot % 3) * .12 }));
        }
        const count = Math.min(AMBIENT_FLOW_COUNT, agentFlows.length);
        return Array.from({ length: count }, (_, slot) => ({
          flow: agentFlows[(activeFlowIndex + slot) % agentFlows.length],
          slot,
          locked: false,
          progress: (flowProgress + slot * .16) % 1
        }));
      }

      function flowTouchesNode(nodeId) {
        return activeFlowEntries().some(({ flow }) => flow && (flow.from === nodeId || flow.to === nodeId));
      }

      function flowEntryForLink(link) {
        return activeFlowEntries().find(({ flow }) =>
          flow &&
          ((link.a.id === flow.from && link.b.id === flow.to) ||
           (link.a.id === flow.to && link.b.id === flow.from))
        );
      }

      function flowTouchesLink(link) {
        return Boolean(flowEntryForLink(link));
      }

      function quadraticPoint(x0, y0, cx, cy, x1, y1, t) {
        const mt = 1 - t;
        return {
          x: mt * mt * x0 + 2 * mt * t * cx + t * t * x1,
          y: mt * mt * y0 + 2 * mt * t * cy + t * t * y1
        };
      }

      function drawQuadraticSegment(x0, y0, cx, cy, x1, y1, t0, t1) {
        const start = Math.max(0, Math.min(1, t0));
        const end = Math.max(start, Math.min(1, t1));
        const steps = 18;
        const first = quadraticPoint(x0, y0, cx, cy, x1, y1, start);
        ctx.beginPath();
        ctx.moveTo(first.x, first.y);
        for (let i = 1; i <= steps; i++) {
          const t = start + (end - start) * (i / steps);
          const point = quadraticPoint(x0, y0, cx, cy, x1, y1, t);
          ctx.lineTo(point.x, point.y);
        }
      }

      function step() {
        nodes.forEach((n) => {
          n.vx += (n.tx - n.px) * .003;
          n.vy += (n.ty - n.py) * .003;
        });
        links.forEach((l) => {
          const dx = l.b.px - l.a.px;
          const dy = l.b.py - l.a.py;
          const dist = Math.hypot(dx, dy) || 1;
          const desired = 118 + (1.4 - Math.min(l.a.w, l.b.w)) * 52;
          const force = (dist - desired) * .0009;
          const fx = dx / dist * force;
          const fy = dy / dist * force;
          l.a.vx += fx; l.a.vy += fy;
          l.b.vx -= fx; l.b.vy -= fy;
        });
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j];
            const dx = b.px - a.px;
            const dy = b.py - a.py;
            const dist = Math.max(22, Math.hypot(dx, dy));
            const repel = 58 / (dist * dist);
            a.vx -= dx * repel; a.vy -= dy * repel;
            b.vx += dx * repel; b.vy += dy * repel;
          }
        }
        nodes.forEach((n) => {
          n.vx *= .86;
          n.vy *= .86;
          n.px += n.vx;
          n.py += n.vy;
        });
      }

      function drawGrid() {
        ctx.save();
        ctx.translate(camera.x, camera.y);
        ctx.scale(camera.scale, camera.scale);
        ctx.strokeStyle = "rgba(241,239,231,.045)";
        ctx.lineWidth = 1 / camera.scale;
        const left = -camera.x / camera.scale;
        const top = -camera.y / camera.scale;
        const right = left + w / camera.scale;
        const bottom = top + h / camera.scale;
        for (let x = Math.floor(left / 42) * 42; x < right; x += 42) {
          ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
        }
        for (let y = Math.floor(top / 42) * 42; y < bottom; y += 42) {
          ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
        }
        ctx.restore();
      }

      function draw() {
        ctx.clearRect(0, 0, w, h);
        drawGrid();
        ctx.save();
        ctx.translate(camera.x, camera.y);
        ctx.scale(camera.scale, camera.scale);
        links.forEach((l) => {
          const flowEntry = flowEntryForLink(l);
          const flowHot = Boolean(flowEntry);
          const nodeHot = l.a === active || l.b === active;
          const hot = flowHot || nodeHot;
          const cx = (l.a.px + l.b.px) / 2 + (l.b.py - l.a.py) * .045;
          const cy = (l.a.py + l.b.py) / 2 - (l.b.px - l.a.px) * .045;
          ctx.strokeStyle = flowHot ? "rgba(200,169,104,.34)" : (nodeHot ? "rgba(200,169,104,.20)" : "rgba(241,239,231,.13)");
          ctx.lineWidth = (flowHot ? 1.15 : nodeHot ? .9 : .62) / camera.scale;
          ctx.beginPath();
          ctx.moveTo(l.a.px, l.a.py);
          ctx.quadraticCurveTo(cx, cy, l.b.px, l.b.py);
          ctx.stroke();

          if (flowHot) {
            ctx.save();
            ctx.shadowColor = flowEntry.locked ? "rgba(200,169,104,.34)" : "rgba(200,169,104,.72)";
            ctx.shadowBlur = (flowEntry.locked ? 9 : 16) / camera.scale;
            ctx.strokeStyle = flowEntry.locked ? "rgba(220,197,147,.34)" : "rgba(220,197,147,.86)";
            ctx.lineWidth = (flowEntry.locked ? 1.75 : 2.55) / camera.scale;
            if (flowEntry.locked) {
              ctx.beginPath();
              ctx.moveTo(l.a.px, l.a.py);
              ctx.quadraticCurveTo(cx, cy, l.b.px, l.b.py);
            } else {
              const start = Math.max(0, flowEntry.progress - FLOW_TAIL);
              const end = Math.min(1, flowEntry.progress);
              drawQuadraticSegment(l.a.px, l.a.py, cx, cy, l.b.px, l.b.py, start, end);
            }
            ctx.stroke();
            ctx.restore();
          }

          l.phase = (l.phase + l.speed) % 1;
          const t = flowHot ? flowEntry.progress : l.phase;
          const point = quadraticPoint(l.a.px, l.a.py, cx, cy, l.b.px, l.b.py, t);
          ctx.fillStyle = flowHot ? (flowEntry.locked ? "rgba(241,224,176,.58)" : "rgba(241,224,176,.95)") : (hot ? "rgba(200,169,104,.46)" : "rgba(241,239,231,.20)");
          ctx.beginPath();
          ctx.arc(point.x, point.y, flowHot ? (flowEntry.locked ? 1.65 : 2.35) : hot ? 1.55 : .95, 0, Math.PI * 2);
          ctx.fill();
        });
        nodes.forEach((n) => {
          const dx = mouse.x - n.px;
          const dy = mouse.y - n.py;
          const hover = !dragging && Math.hypot(dx, dy) < 42;
          if (hover && active !== n) setActive(n);
          const hot = n === active || flowTouchesNode(n.id);
          const r = (n.group === "core" ? 22 : 12) * (n.w || 1);
          ctx.fillStyle = hot ? "rgba(200,169,104,.14)" : "rgba(7,7,7,.78)";
          ctx.strokeStyle = hot ? "rgba(200,169,104,.9)" : "rgba(241,239,231,.38)";
          ctx.lineWidth = (hot ? 1.7 : .85) / camera.scale;
          ctx.beginPath();
          ctx.arc(n.px, n.py, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
          ctx.strokeStyle = hot ? "rgba(200,169,104,.52)" : "rgba(241,239,231,.18)";
          ctx.beginPath();
          ctx.moveTo(n.px - r - 7, n.py); ctx.lineTo(n.px + r + 7, n.py);
          ctx.moveTo(n.px, n.py - r - 7); ctx.lineTo(n.px, n.py + r + 7);
          ctx.stroke();
          ctx.fillStyle = hot ? "#f1efe7" : (colors[n.group] || "#bbb7ab");
          ctx.font = hot ? "700 12px Consolas, monospace" : "11px Consolas, monospace";
          ctx.textAlign = "center";
          ctx.fillText(n.label, n.px, n.py + r + 18);
          ctx.fillStyle = "rgba(241,239,231,.42)";
          ctx.font = "9px Consolas, monospace";
          ctx.fillText(n.role, n.px, n.py + r + 32);
        });
        ctx.restore();
      }

      function animate(timestamp) {
        step();
        updateAgentFlow(timestamp || performance.now());
        draw();
        requestAnimationFrame(animate);
      }

      canvas.addEventListener("pointerdown", (event) => {
        dragging = true;
        graphCard.classList.add("dragging");
        dragStart = { x: event.clientX, y: event.clientY, camX: camera.x, camY: camera.y };
        canvas.setPointerCapture(event.pointerId);
      });

      canvas.addEventListener("pointermove", (event) => {
        const rect = canvas.getBoundingClientRect();
        const sx = event.clientX - rect.left;
        const sy = event.clientY - rect.top;
        if (dragging) {
          camera.x = dragStart.camX + event.clientX - dragStart.x;
          camera.y = dragStart.camY + event.clientY - dragStart.y;
        }
        const world = screenToWorld(sx, sy);
        mouse.x = world.x;
        mouse.y = world.y;
      });

      canvas.addEventListener("pointerup", (event) => {
        dragging = false;
        graphCard.classList.remove("dragging");
        try { canvas.releasePointerCapture(event.pointerId); } catch (error) {}
      });

      canvas.addEventListener("pointercancel", () => {
        dragging = false;
        graphCard.classList.remove("dragging");
      });

      canvas.addEventListener("mouseleave", () => {
        if (!dragging) {
          mouse.x = -9999;
          mouse.y = -9999;
        }
      });

      canvas.addEventListener("dblclick", fitGraph);

      canvas.addEventListener("wheel", (event) => {
        event.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const sx = event.clientX - rect.left;
        const sy = event.clientY - rect.top;
        zoomAt(sx, sy, event.deltaY < 0 ? 1.12 : .89);
      }, { passive: false });

      fitBtn.addEventListener("click", fitGraph);
      zoomInBtn.addEventListener("click", () => zoomAt(w / 2, h / 2, 1.18));
      zoomOutBtn.addEventListener("click", () => zoomAt(w / 2, h / 2, .84));

      function afterViewportChange() {
        setTimeout(() => { resize(); fitGraph(); }, 90);
      }

      expandBtn.addEventListener("click", async () => {
        if (graphCard.requestFullscreen) {
          try {
            if (document.fullscreenElement === graphCard) {
              await document.exitFullscreen();
            } else {
              await graphCard.requestFullscreen();
            }
            return;
          } catch (error) {}
        }
        shell.classList.toggle("expanded");
        expandBtn.textContent = shell.classList.contains("expanded") ? "collapse" : "expand";
        afterViewportChange();
      });

      document.addEventListener("fullscreenchange", () => {
        expandBtn.textContent = document.fullscreenElement === graphCard ? "collapse" : "expand";
        afterViewportChange();
      });

      window.addEventListener("mouseup", () => {
        dragging = false;
        graphCard.classList.remove("dragging");
        mouse.x = -9999;
        mouse.y = -9999;
      });

      window.addEventListener("resize", resize);
      resize();
      setActive(byId.kernel);
      fitGraph();
      renderAgentBus();
      animate();
    </script>
    """
    html = (
        html.replace("__NODES__", nodes_json)
        .replace("__LINKS__", links_json)
        .replace("__PANEL_STATES__", panel_states_json)
        .replace("__NODE_COUNT__", str(len(nodes)))
        .replace("__LINK_COUNT__", str(len(links)))
    )
    components.html(html, height=790, scrolling=False)
