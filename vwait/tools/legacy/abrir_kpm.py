import threading
from datetime import datetime
from pathlib import Path

import os
import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# ==========================
# CONFIGURAÇÕES
# ==========================
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELATORIOS_DIR = PROJECT_ROOT / "workspace" / "reports" / "failures"
CSV_LOG_PATH = RELATORIOS_DIR / "tickets_gerados.csv"

KPM_URL = "https://kpmweb.vw.vwg/kpmweb/f5Login.do"

# Campos fixos
PART_NUMBER = "1234567890"
MODULE = "Electrical"
COUNTRY = "Brazil"
REPRODUCIBLE = "Yes"
FREQUENCY = "100%"
HW_VERSION = "HW_1.0"
SW_VERSION = "SW_1.0"

# PIN do seu PKI (substitua por leitura segura se preferir)
PKI_PIN = "278500"

# Timeout total para aguardar o prompt PKI (segundos)
PKI_PROMPT_TIMEOUT = 30.0

# Palavras-chave para tentar identificar a janela de prompt PKI (títulos)
PKI_WINDOW_KEYWORDS = [
    "smartcard", "pki", "authentication", "autentica", "token", "cert", "senha", "pin"
]

# ==========================
# IMPORTS DINÂMICOS (pygetwindow/pyautogui)
# ==========================
try:
    import pygetwindow as gw
    import pyautogui
    PYGUI_AVAILABLE = True
except Exception:
    gw = None
    pyautogui = None
    PYGUI_AVAILABLE = False

# ==========================
# UTIL
# ==========================
def printc(msg, color="white"):
    cores = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "white": "\033[0m",
        "cyan": "\033[96m"
    }
    print(f"{cores.get(color, '')}{msg}{cores['white']}", flush=True)

# ==========================
# THREAD: Autofill PKI PIN
# ==========================
def _window_title_matches(title: str, keywords):
    if not title:
        return False
    t = title.lower()
    for kw in keywords:
        if kw.lower() in t:
            return True
    return False

def pki_autofill_worker(pin: str, stop_event: threading.Event, timeout: float, keywords=PKI_WINDOW_KEYWORDS, poll_interval: float = 0.5):
    """
    Worker que procura pela janela de prompt PKI e, quando encontrada,
    ativa a janela e digita o PIN + Enter.
    - Usa pygetwindow + pyautogui quando disponíveis.
    - Para maior segurança, o PIN está vindo do parâmetro (não hardcode em múltiplos pontos).
    """
    printc("🔐 PKI autofill thread iniciada (procurando prompt de autenticação)...", "cyan")
    start = time.time()
    typed = False

    while not stop_event.is_set():
        elapsed = time.time() - start
        if elapsed > timeout:
            printc("⏱️ Timeout aguardando prompt PKI. Encerrando thread de autofill.", "yellow")
            break

        try:
            # Método robusto: procurar janelas com pygetwindow (Windows)
            if PYGUI_AVAILABLE and gw is not None:
                titles = gw.getAllTitles()
                for t in titles:
                    if _window_title_matches(t, keywords):
                        try:
                            win = gw.getWindowsWithTitle(t)[0]
                            if not win.isActive:
                                win.activate()
                                time.sleep(0.2)  # dar tempo para ativar
                            # Digitar PIN com pyautogui de forma segura (pequena pausa entre teclas)
                            pyautogui.write(pin, interval=0.05)
                            pyautogui.press("enter")
                            printc("✅ PIN enviado para a janela PKI via pyautogui.", "green")
                            typed = True
                            stop_event.set()
                            break
                        except Exception as e:
                            printc(f"⚠️ Falha ao ativar janela/type (pygetwindow/pyautogui): {e}", "yellow")
                            # continuar tentando
                if typed:
                    break

            # Fallback: sem pygetwindow, tentar usar pyautogui para localizar padrão visual (não implementado)
            # Simples fallback: se pyautogui disponível, tenta digitar quando houver foco na tela (menos seguro)
            if PYGUI_AVAILABLE and not typed:
                # tenta escrever apenas se a janela parecer ativa (não ideal, mas útil como fallback)
                try:
                    # Observe: isso pode digitar em qualquer campo com foco, use com cuidado.
                    pyautogui.write(pin, interval=0.05)
                    pyautogui.press("enter")
                    printc("⚠️ Fallback: PIN enviado com pyautogui (sem detecção de janela).", "yellow")
                    typed = True
                    stop_event.set()
                    break
                except Exception:
                    pass

        except Exception as exc:
            # Não queremos que a thread morra por uma exceção transitória
            printc(f"⚠️ Erro na thread autofill PKI: {exc}", "yellow")

        time.sleep(poll_interval)

    if not typed:
        printc("⚠️ Não detectei o prompt PKI antes do timeout.", "yellow")
    else:
        printc("🔒 Autofill PKI concluído.", "green")


def start_pki_autofill_thread(pin: str, timeout: float = PKI_PROMPT_TIMEOUT):
    """
    Inicia a thread de autofill e retorna (thread_obj, stop_event).
    O chamador deve setar stop_event para interromper a thread caso necessário.
    """
    stop_event = threading.Event()
    thread = threading.Thread(target=pki_autofill_worker, args=(pin, stop_event, timeout), daemon=True)
    thread.start()
    return thread, stop_event

# ==========================
# KPM AUTOMATION CORE
# ==========================
def carregar_relatorio():
    arquivos = sorted(
        RELATORIOS_DIR.rglob("failure_report.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not arquivos:
        printc("❌ Nenhum failure_report.csv encontrado em workspace/reports/failures.", "red")
        return None

    ultimo = arquivos[0]
    printc(f"📄 Usando relatório: {ultimo}", "yellow")
    return pd.read_csv(ultimo)


def iniciar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    # usa uma sessão já existente do Chrome (remote debugging)
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        printc(f"❌ Erro ao conectar ao Chrome via remote-debugging: {e}", "red")
        printc("💡 Abra o Chrome com: chrome.exe --remote-debugging-port=9222 --user-data-dir=\"C:\\ChromeSession\"", "yellow")
        return None


def preencher_ticket(driver, row):
    try:
        # Abre a página KPM (poderá disparar o prompt PKI do middleware)
        driver.get(KPM_URL)
        time.sleep(3)  # aguardar a página e possivelmente o prompt

        # Observação: os IDs/seletores abaixo são PLACEHOLDERS.
        # Você precisa substituí-los pelos seletores reais do formulário KPM.
        # Exemplo:
        # driver.find_element(By.ID, "shortText").send_keys(row["Short Text"])
        # ...
        # Vou usar try/except e procurar por elementos comuns. Ajuste conforme seu ambiente KPM.

        # --- SHORT TEXT ---
        try:
            el = driver.find_element(By.ID, "shortText")
            el.clear()
            el.send_keys(str(row.get("Short Text", "")))
        except Exception:
            printc("⚠️ Campo Short Text não encontrado pelo ID 'shortText' (verifique o seletor).", "yellow")

        # --- MODULE ---
        try:
            el = driver.find_element(By.ID, "module")
            el.clear()
            el.send_keys(MODULE)
        except Exception:
            printc("⚠️ Campo Module não encontrado pelo ID 'module' (verifique o seletor).", "yellow")

        # --- COUNTRY ---
        try:
            el = driver.find_element(By.ID, "country")
            el.clear()
            el.send_keys(COUNTRY)
        except Exception:
            printc("⚠️ Campo Country não encontrado pelo ID 'country' (verifique o seletor).", "yellow")

        # --- RECLAMATION / DESCRIPTION ---
        reclamation_text = (
            f"[Precondition]\n{row.get('Precondition','')}\n\n"
            f"[Action]\n{row.get('Action','')}\n\n"
            f"[Actual Result]\n{row.get('Actual Result','')}\n\n"
            f"[Expected Result]\n{row.get('Expected Result','')}"
        )
        try:
            el = driver.find_element(By.ID, "reclamation")
            el.clear()
            el.send_keys(reclamation_text)
        except Exception:
            printc("⚠️ Campo Reclamation/Description não encontrado pelo ID 'reclamation'.", "yellow")

        # --- REPRODUCIBLE ---
        try:
            el = driver.find_element(By.ID, "reproducible")
            el.clear()
            el.send_keys(REPRODUCIBLE)
        except Exception:
            printc("⚠️ Campo Reproducible não encontrado pelo ID 'reproducible'.", "yellow")

        # --- FREQUENCY ---
        try:
            el = driver.find_element(By.ID, "frequency")
            el.clear()
            el.send_keys(FREQUENCY)
        except Exception:
            printc("⚠️ Campo Frequency não encontrado pelo ID 'frequency'.", "yellow")

        # --- PART NUMBER ---
        try:
            el = driver.find_element(By.ID, "partNumber")
            el.clear()
            el.send_keys(PART_NUMBER)
        except Exception:
            printc("⚠️ Campo Part Number não encontrado pelo ID 'partNumber'.", "yellow")

        # --- HW / SW ---
        try:
            el = driver.find_element(By.ID, "hwVersion")
            el.clear()
            el.send_keys(HW_VERSION)
        except Exception:
            printc("⚠️ Campo HW não encontrado pelo ID 'hwVersion'.", "yellow")

        try:
            el = driver.find_element(By.ID, "swVersion")
            el.clear()
            el.send_keys(SW_VERSION)
        except Exception:
            printc("⚠️ Campo SW não encontrado pelo ID 'swVersion'.", "yellow")

        # --- SUBMIT ---
        try:
            submit = driver.find_element(By.ID, "submitButton")
            submit.click()
            time.sleep(3)
        except Exception:
            printc("⚠️ Botão de submit não encontrado com ID 'submitButton'. (Ajuste o seletor)", "yellow")

        # --- Captura ID do ticket (placeholder selector) ---
        try:
            ticket_id = driver.find_element(By.CSS_SELECTOR, ".ticketNumber").text
            printc(f"✅ Ticket criado: {ticket_id}", "green")
            return ticket_id
        except Exception:
            printc("⚠️ Não foi possível capturar o ID do ticket (seletor '.ticketNumber' pode estar incorreto).", "yellow")
            return None

    except Exception as e:
        printc(f"❌ Erro ao preencher ticket: {e}", "red")
        return None


def registrar_ticket(ticket_id, row):
    RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)
    existe = CSV_LOG_PATH.exists()
    with CSV_LOG_PATH.open("a", encoding="utf-8") as f:
        if not existe:
            f.write("timestamp,ticket_id,short_text,arquivo\n")
        f.write(f"{datetime.now().isoformat()},{ticket_id},{row.get('Short Text','')},{row.name}\n")


def main():
    printc("🚀 Iniciando automação KPM...", "cyan")
    df = carregar_relatorio()
    if df is None:
        return

    # Inicia a thread de autofill PKI ANTES de abrir a URL (ela ficará escutando por prompt)
    thread, stop_event = start_pki_autofill_thread(PKI_PIN, timeout=PKI_PROMPT_TIMEOUT)

    driver = iniciar_driver()
    if not driver:
        # se não conseguiu iniciar o driver, sinaliza para a thread parar
        stop_event.set()
        return

    for _, row in df.iterrows():
        # Para cada item, navegaremos — o autofill thread pode disparar quando o prompt aparecer.
        ticket_id = preencher_ticket(driver, row)
        if ticket_id:
            registrar_ticket(ticket_id, row)
        time.sleep(2)

    # sinaliza a thread para encerrar caso ainda esteja ativa
    stop_event.set()
    # aguarda pequeno tempo para terminar
    time.sleep(0.5)

    printc("🏁 Finalizado. Tickets registrados em tickets_gerados.csv", "green")
    try:
        driver.quit()
    except Exception:
        pass


if __name__ == "__main__":
    main()
