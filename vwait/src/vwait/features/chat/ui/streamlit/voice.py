import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from functools import lru_cache
from io import BytesIO
from typing import Callable, TypedDict

import speech_recognition as sr

STT_CAPTURE_TIMEOUT_S = float(os.getenv("STT_CAPTURE_TIMEOUT_S", "8"))
STT_WHISPER_TIMEOUT_S = float(os.getenv("STT_WHISPER_TIMEOUT_S", "8"))

_STT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")


class STTRuntimeProfile(TypedDict):
    provider: str
    model_name: str
    compute_cfg: str
    timeout_s: float
    device_index: int | None


def configure_recognizer() -> sr.Recognizer:
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.energy_threshold = 250
    recognizer.pause_threshold = 1.0
    recognizer.non_speaking_duration = 0.2
    recognizer.phrase_threshold = 0.25
    setattr(recognizer, "operation_timeout", float(max(6, int(STT_CAPTURE_TIMEOUT_S))))
    return recognizer


def _stt_command_prompt(
    *,
    list_categories: Callable[[], list[str]],
    list_tests: Callable[[str], list[str]],
) -> str:
    catalog: list[str] = []
    try:
        for category in list_categories()[:8]:
            for test_name in list_tests(category)[:8]:
                catalog.append(test_name)
    except Exception:
        catalog = []
    catalog_txt = ", ".join(catalog[:20])
    return (
        "Comandos de automacao por voz em portugues do Brasil: "
        "executar, rodar, gravar, coletar, processar, apagar, listar, listar bancadas, "
        "resetar, pausar, retomar, parar, menu tester, validacao hmi, dashboard, mapa neural, "
        "bancada um, bancada dois, bancada tres, audio, video, bluetooth, carplay, android auto. "
        f"Testes conhecidos no ambiente: {catalog_txt}."
    )


def _stt_runtime_profile() -> STTRuntimeProfile:
    device = _detect_whisper_device()
    if device == "cuda":
        return {
            "provider": "whisper",
            "model_name": "medium",
            "compute_cfg": "auto",
            "timeout_s": 10.0,
            "device_index": None,
        }
    return {
        "provider": "auto",
        "model_name": "medium",
        "compute_cfg": "auto",
        "timeout_s": max(12.0, float(STT_WHISPER_TIMEOUT_S)),
        "device_index": None,
    }


def _detect_whisper_device() -> str:
    try:
        import torch  # type: ignore

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _resolve_compute_type(device: str, compute_cfg: str) -> str:
    mode = str(compute_cfg or "auto").strip().lower()
    if mode and mode != "auto":
        return mode
    return "float16" if device == "cuda" else "int8"


@lru_cache(maxsize=8)
def _load_faster_whisper_model(model_name: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel  # type: ignore

    cpu_threads = max(2, int(os.cpu_count() or 2))
    return WhisperModel(model_name, device=device, compute_type=compute_type, cpu_threads=cpu_threads)


def preload_whisper_default() -> None:
    try:
        stt_profile = _stt_runtime_profile()
        device = _detect_whisper_device()
        compute_type = _resolve_compute_type(device, str(stt_profile["compute_cfg"]))
        _load_faster_whisper_model(str(stt_profile["model_name"]), device, compute_type)
    except Exception:
        pass


def _transcribe_with_faster_whisper(
    audio: sr.AudioData,
    *,
    model_name: str,
    compute_cfg: str,
    prompt_text: str,
) -> str | None:
    wav_bytes = audio.get_wav_data(convert_rate=16000, convert_width=2)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="voz_cmd_", suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name

        device = _detect_whisper_device()
        compute_type = _resolve_compute_type(device, compute_cfg)
        try:
            model = _load_faster_whisper_model(model_name, device, compute_type)
        except Exception:
            if compute_type != "float32":
                model = _load_faster_whisper_model(model_name, device, "float32")
            else:
                raise

        segments, _ = model.transcribe(
            tmp_path,
            language="pt",
            task="transcribe",
            beam_size=3,
            best_of=3,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250},
            initial_prompt=prompt_text,
        )
        text = " ".join(segment.text.strip() for segment in segments if getattr(segment, "text", "").strip()).strip()
        return text or None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _transcribe_with_faster_whisper_timeout(
    audio: sr.AudioData,
    *,
    model_name: str,
    compute_cfg: str,
    prompt_text: str,
    timeout_s: float,
) -> str | None:
    future = _STT_EXECUTOR.submit(
        _transcribe_with_faster_whisper,
        audio,
        model_name=model_name,
        compute_cfg=compute_cfg,
        prompt_text=prompt_text,
    )
    try:
        return future.result(timeout=max(2.0, float(timeout_s)))
    except FutureTimeout as exc:
        future.cancel()
        raise TimeoutError(f"Whisper timeout ({timeout_s:.1f}s)") from exc


def _transcribe_google_best_effort(recognizer: sr.Recognizer, audio: sr.AudioData) -> str | None:
    try:
        raw = recognizer.recognize_google(audio, language="pt-BR", show_all=True)  # type: ignore[attr-defined]
        if isinstance(raw, dict):
            alternatives = raw.get("alternative") or []
            if alternatives:
                best = sorted(alternatives, key=lambda alt: float(alt.get("confidence", 0.0)), reverse=True)[0]
                text = str(best.get("transcript") or "").strip()
                if text:
                    return text
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    except Exception:
        pass
    try:
        text = recognizer.recognize_google(audio, language="pt-BR")  # type: ignore[attr-defined]
        return str(text).strip() if text else None
    except Exception:
        return None


def transcribe_command_audio(
    recognizer: sr.Recognizer,
    audio: sr.AudioData,
    *,
    list_categories: Callable[[], list[str]],
    list_tests: Callable[[str], list[str]],
) -> tuple[str | None, str, str]:
    stt_profile = _stt_runtime_profile()
    provider = str(stt_profile["provider"]).strip().lower()
    model_name = str(stt_profile["model_name"]).strip().lower()
    compute_cfg = str(stt_profile["compute_cfg"]).strip().lower()
    whisper_timeout_s = float(stt_profile["timeout_s"])
    prompt_text = _stt_command_prompt(list_categories=list_categories, list_tests=list_tests)
    errors: list[str] = []

    if provider in {"auto", "whisper"}:
        model_candidates = [model_name]
        if model_name in {"large-v3", "medium"}:
            model_candidates.append("small")

        for candidate in model_candidates:
            try:
                text = _transcribe_with_faster_whisper_timeout(
                    audio,
                    model_name=candidate,
                    compute_cfg=compute_cfg,
                    prompt_text=prompt_text,
                    timeout_s=whisper_timeout_s,
                )
                if text:
                    engine = "Whisper" if candidate == model_name else f"Whisper ({candidate})"
                    return text, engine, " | ".join(errors)
                errors.append(f"Whisper {candidate} sem texto")
            except Exception as exc:
                errors.append(f"Whisper {candidate} indisponivel: {exc}")

    text_google = _transcribe_google_best_effort(recognizer, audio)
    if text_google:
        return text_google, "Google", " | ".join(errors)

    if provider == "google":
        errors.append("Google sem texto")
    return None, "Nenhum", " | ".join(errors)


def audio_input_to_sr_audio(uploaded_audio: object) -> sr.AudioData:
    getvalue = getattr(uploaded_audio, "getvalue", None)
    if not callable(getvalue):
        raise RuntimeError("Gravacao do navegador indisponivel.")
    audio_bytes = getvalue()
    if not audio_bytes:
        raise RuntimeError("Nenhum audio recebido do navegador.")
    with sr.AudioFile(BytesIO(audio_bytes)) as source:
        recognizer = configure_recognizer()
        return recognizer.record(source)


def process_voice_command(
    command_text: str,
    *,
    normalize_post_speech: Callable[[str], str],
    pending_recording: object,
    continue_recording_flow: Callable[[str], str],
    conversation_mode: bool,
    conversational_responder: Callable[[str], str],
    command_resolver: Callable[[str], str],
    chat_history: list[dict[str, str]],
) -> None:
    normalized = normalize_post_speech(command_text)
    chat_history.append({"role": "user", "content": normalized})
    if pending_recording is not None:
        response = continue_recording_flow(normalized)
    elif conversation_mode:
        response = conversational_responder(normalized)
    else:
        response = command_resolver(normalized)
    if response:
        chat_history.append({"role": "assistant", "content": response})

