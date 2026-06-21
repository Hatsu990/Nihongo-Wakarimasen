from __future__ import annotations

import csv
import ctypes
import queue
import struct
import subprocess
import sys
import threading
import time
import tempfile
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundcard as sc

if sys.platform == "win32":
    import ctypes.wintypes


@dataclass(frozen=True)
class CaptureProcessOption:
    pid: int
    name: str
    window_title: str = ""
    active_audio: bool = False

    @property
    def capture_value(self) -> str:
        return str(self.pid)

    @property
    def label(self) -> str:
        title = f" - {self.window_title}" if self.window_title else ""
        state = "audio" if self.active_audio else "running"
        return f"{self.name} ({state}, pid={self.pid}){title}"


def find_speaker(name: str | None = None):
    if not name:
        speaker = sc.default_speaker()
        if speaker is None:
            raise RuntimeError("기본 출력 장치를 찾지 못했습니다.")
        return speaker

    speakers = sc.all_speakers()
    name_lower = name.lower()
    matches = [speaker for speaker in speakers if name_lower in speaker.name.lower()]
    if not matches:
        available = "\n".join(f"- {speaker.name}" for speaker in speakers)
        raise RuntimeError(
            f"'{name}' 이름을 포함하는 출력 장치를 찾지 못했습니다.\n사용 가능한 출력 장치:\n{available}"
        )
    return matches[0]


def find_capture_device(name: str | None = None):
    if not name:
        return find_speaker(None), True

    speakers = sc.all_speakers()
    name_lower = name.lower()
    speaker_matches = [speaker for speaker in speakers if name_lower in speaker.name.lower()]
    if speaker_matches:
        return speaker_matches[0], True

    microphones = sc.all_microphones(include_loopback=True)
    microphone_matches = [
        microphone for microphone in microphones if name_lower in microphone.name.lower()
    ]
    if microphone_matches:
        return microphone_matches[0], False

    available_speakers = "\n".join(f"- {speaker.name}" for speaker in speakers)
    available_microphones = "\n".join(f"- {microphone.name}" for microphone in microphones)
    raise RuntimeError(
        f"'{name}' 이름을 포함하는 캡처 장치를 찾지 못했습니다.\n"
        f"사용 가능한 출력 장치:\n{available_speakers}\n"
        f"사용 가능한 입력 장치:\n{available_microphones}"
    )


class SystemAudioCapture:
    def __init__(self, sample_rate: int, speaker_name: str | None = None) -> None:
        self.sample_rate = sample_rate
        self.speaker_name = speaker_name

    def record(self, seconds: float) -> np.ndarray:
        device, use_loopback = find_capture_device(self.speaker_name)
        microphone = (
            sc.get_microphone(device.name, include_loopback=True)
            if use_loopback
            else device
        )
        frames = int(self.sample_rate * seconds)

        with microphone.recorder(samplerate=self.sample_rate, channels=1) as recorder:
            audio = recorder.record(numframes=frames)

        return np.asarray(audio, dtype=np.float32).reshape(-1)


def find_process_id(process: str) -> int:
    if process.isdigit():
        return int(process)

    active_audio_pid = _find_active_audio_process_id(process)
    if active_audio_pid is not None:
        return active_audio_pid

    command = [
        "tasklist",
        "/FI",
        f"IMAGENAME eq {process}",
        "/FO",
        "CSV",
        "/NH",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Could not list process: {process}")

    rows = list(csv.reader(result.stdout.splitlines()))
    matches = [row for row in rows if len(row) >= 2 and row[0].lower() == process.lower()]
    if not matches:
        raise RuntimeError(f"Process not found: {process}")
    return int(matches[0][1])


def _find_active_audio_process_id(process: str) -> int | None:
    try:
        from process_audio_capture import ProcessAudioCapture
    except ImportError:
        return None

    if not ProcessAudioCapture.is_supported():
        return None

    try:
        processes = ProcessAudioCapture.enumerate_audio_processes()
    except Exception:
        return None

    for audio_process in processes:
        if audio_process.name.lower() == process.lower():
            return int(audio_process.pid)
    return None


def list_audio_processes() -> list[str]:
    try:
        from process_audio_capture import ProcessAudioCapture
    except ImportError:
        return ["process-audio-capture is not installed"]

    if not ProcessAudioCapture.is_supported():
        return ["Windows process loopback is not supported on this system"]

    try:
        processes = ProcessAudioCapture.enumerate_audio_processes()
    except Exception as exc:
        return [f"Could not enumerate audio processes: {exc}"]
    if not processes:
        return ["No active audio processes found"]
    return [
        f"{process.pid}: {process.name} - {process.window_title}"
        for process in processes
    ]


def list_capture_process_options(
    preferred_names: list[str] | None = None,
) -> list[CaptureProcessOption]:
    options: dict[int, CaptureProcessOption] = {}
    for option in _list_active_audio_process_options():
        options[option.pid] = option

    forced_names = ["Discord.exe"]
    for name in preferred_names or []:
        if name and not name.isdigit() and name not in forced_names:
            forced_names.append(name)
    if "chrome.exe" not in [name.lower() for name in forced_names]:
        forced_names.append("chrome.exe")

    window_titles = _visible_window_titles_by_pid()
    for name in forced_names:
        if any(
            option.active_audio and option.name.lower() == name.lower()
            for option in options.values()
        ):
            continue
        running = _find_running_processes(name)
        titled = [(pid, process_name) for pid, process_name in running if window_titles.get(pid)]
        for pid, process_name in titled or running:
            if pid in options:
                continue
            options[pid] = CaptureProcessOption(
                pid=pid,
                name=process_name,
                window_title=window_titles.get(pid, ""),
                active_audio=False,
            )

    return sorted(
        options.values(),
        key=lambda option: (
            option.name.lower() != "discord.exe",
            not option.active_audio,
            option.name.lower(),
            option.pid,
        ),
    )


def _list_active_audio_process_options() -> list[CaptureProcessOption]:
    try:
        from process_audio_capture import ProcessAudioCapture
    except ImportError:
        return []

    if not ProcessAudioCapture.is_supported():
        return []

    try:
        processes = ProcessAudioCapture.enumerate_audio_processes()
    except Exception:
        return []

    return [
        CaptureProcessOption(
            pid=int(process.pid),
            name=str(process.name),
            window_title=str(getattr(process, "window_title", "") or ""),
            active_audio=True,
        )
        for process in processes
    ]


def _find_running_processes(process_name: str) -> list[tuple[int, str]]:
    command = [
        "tasklist",
        "/FI",
        f"IMAGENAME eq {process_name}",
        "/FO",
        "CSV",
        "/NH",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    rows = list(csv.reader(result.stdout.splitlines()))
    matches = []
    for row in rows:
        if len(row) < 2 or row[0].lower() != process_name.lower():
            continue
        try:
            matches.append((int(row[1]), row[0]))
        except ValueError:
            continue
    return matches


def _visible_window_titles_by_pid() -> dict[int, str]:
    if sys.platform != "win32":
        return {}
    titles: dict[int, str] = {}

    def callback(hwnd, _extra):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        process_id = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value and buffer.value:
            titles.setdefault(int(process_id.value), buffer.value)
        return True

    enum_windows_proc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )
    ctypes.windll.user32.EnumWindows(enum_windows_proc(callback), 0)
    return titles


class ProcessLoopbackCapture:
    def __init__(self, sample_rate: int, process: str) -> None:
        self.sample_rate = sample_rate
        self.process = process

    def record(self, seconds: float) -> np.ndarray:
        try:
            from recap.audio import AudioCapture as RecapAudioCapture
        except ImportError as exc:
            raise RuntimeError("recap-capture is required for process capture.") from exc

        process_id = find_process_id(self.process)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            wav_path = Path(temp_file.name)

        capture = RecapAudioCapture(str(wav_path), process_id=process_id)
        try:
            capture.start()
            if not capture.wait_format_ready(timeout=10):
                raise RuntimeError("Process audio capture format was not ready.")
            if not capture.wait_started(timeout=10):
                raise RuntimeError("Process audio capture did not start.")
            time.sleep(seconds)
            capture.stop()
            capture.wait(timeout=10)
            return _read_wav_mono_float32(wav_path, self.sample_rate)
        finally:
            capture.stop()
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass


class StreamingProcessLoopbackCapture:
    def __init__(
        self,
        sample_rate: int,
        process: str,
        frames_per_chunk: int,
        on_chunk,
    ) -> None:
        self.sample_rate = sample_rate
        self.process = process
        self.frames_per_chunk = frames_per_chunk
        self.on_chunk = on_chunk
        self._pending = np.empty(0, dtype=np.float32)
        self._capture = None
        self._wav_path: Path | None = None

    def start(self) -> None:
        try:
            from recap.audio import _PythonAudioCapture as BaseAudioCapture
        except ImportError as exc:
            raise RuntimeError("recap-capture is required for process streaming.") from exc

        process_id = find_process_id(self.process)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            self._wav_path = Path(temp_file.name)

        outer = self

        class QueueAudioCapture(BaseAudioCapture):
            def _drain_packets(self, capture_client, bytes_per_frame: int) -> None:
                outer._drain_packets(self, capture_client, bytes_per_frame)

        self._capture = QueueAudioCapture(str(self._wav_path), process_id=process_id)
        self._capture.start()
        if not self._capture.wait_format_ready(timeout=10):
            raise RuntimeError("Process audio stream format was not ready.")
        if not self._capture.wait_started(timeout=10):
            raise RuntimeError("Process audio stream did not start.")

    def stop(self) -> None:
        if self._capture is not None:
            self._capture.stop()
            self._capture.wait(timeout=10)
            self._capture = None
        if self._wav_path is not None:
            try:
                self._wav_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._wav_path = None

    def wait(self) -> None:
        if self._capture is not None:
            self._capture.wait()

    def _drain_packets(self, capture, capture_client, bytes_per_frame: int) -> None:
        silent_flag = 0x2
        while True:
            packet_size = capture_client.GetNextPacketSize()
            if packet_size == 0:
                break

            data_ptr, num_frames, flags, _, _ = capture_client.GetBuffer()
            try:
                if num_frames > 0:
                    if flags & silent_flag:
                        audio = np.zeros(num_frames, dtype=np.float32)
                    else:
                        size = num_frames * bytes_per_frame
                        raw = bytes((ctypes.c_char * size).from_address(data_ptr))
                        audio = _raw_packet_to_mono_float32(
                            raw,
                            capture._channels,
                            capture._bits_per_sample,
                            capture._is_float,
                        )
                    if capture._sample_rate != self.sample_rate and audio.size:
                        audio = _resample_linear(
                            audio,
                            capture._sample_rate,
                            self.sample_rate,
                        )
                    self._emit_chunks(audio)
            finally:
                capture_client.ReleaseBuffer(num_frames)

    def _emit_chunks(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        self._pending = np.concatenate([self._pending, audio])
        while self._pending.size >= self.frames_per_chunk:
            chunk = self._pending[: self.frames_per_chunk]
            self._pending = self._pending[self.frames_per_chunk :]
            self.on_chunk(chunk.astype(np.float32, copy=False))


def create_audio_capture(
    sample_rate: int,
    speaker_name: str | None = None,
    process: str | None = None,
):
    if process:
        return ProcessLoopbackCapture(sample_rate, process)
    return SystemAudioCapture(sample_rate, speaker_name)


def _raw_packet_to_mono_float32(
    raw: bytes,
    channels: int,
    bits_per_sample: int,
    is_float: bool,
) -> np.ndarray:
    if is_float:
        audio = np.frombuffer(raw, dtype=np.float32)
    elif bits_per_sample == 16:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif bits_per_sample == 32:
        audio = np.asarray(struct.unpack_from(f"<{len(raw) // 4}i", raw), dtype=np.float32)
        audio = audio / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported process stream sample width: {bits_per_sample}")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio.astype(np.float32, copy=False)


def _read_wav_mono_float32(path: Path, target_sample_rate: int) -> np.ndarray:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise RuntimeError(f"Unsupported process capture sample width: {sample_width}")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if sample_rate != target_sample_rate and audio.size:
        audio = _resample_linear(audio, sample_rate, target_sample_rate)
    return audio.astype(np.float32, copy=False)


def _resample_linear(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or audio.size == 0:
        return audio
    duration = audio.size / source_rate
    target_size = max(1, int(duration * target_rate))
    source_x = np.linspace(0.0, duration, num=audio.size, endpoint=False)
    target_x = np.linspace(0.0, duration, num=target_size, endpoint=False)
    return np.interp(target_x, source_x, audio).astype(np.float32)


class ContinuousSystemAudioCapture:
    def __init__(
        self,
        sample_rate: int,
        seconds: float,
        max_chunks: int,
        recent_chunks: int | None = None,
        speaker_name: str | None = None,
        monitor_speaker_name: str | None = None,
        process: str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.seconds = seconds
        self.max_chunks = max_chunks
        self.speaker_name = speaker_name
        self.monitor_speaker_name = monitor_speaker_name
        self.process = process
        self.frames = int(sample_rate * seconds)
        self.chunks: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_chunks)
        self.monitor_chunks: queue.Queue[np.ndarray] = queue.Queue(maxsize=2)
        self.recent_chunks: deque[np.ndarray] = deque(maxlen=recent_chunks or max_chunks)
        self._recent_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        if self.monitor_speaker_name is not None:
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def read(self) -> np.ndarray:
        return self.chunks.get()

    def read_latest(self) -> tuple[np.ndarray, int]:
        latest = self.chunks.get()
        dropped = 0
        while True:
            try:
                latest = self.chunks.get_nowait()
                dropped += 1
            except queue.Empty:
                return latest, dropped

    def read_recent_window(self, max_frames: int) -> tuple[np.ndarray, int]:
        self.chunks.get()
        drained = 0
        while True:
            try:
                self.chunks.get_nowait()
                drained += 1
            except queue.Empty:
                break

        with self._recent_lock:
            if not self.recent_chunks:
                return np.empty(0, dtype=np.float32), drained
            audio = np.concatenate(list(self.recent_chunks))

        if audio.size > max_frames:
            audio = audio[-max_frames:]
        return audio, drained

    def snapshot_recent_window(self, max_frames: int) -> np.ndarray:
        with self._recent_lock:
            if not self.recent_chunks:
                return np.empty(0, dtype=np.float32)
            audio = np.concatenate(list(self.recent_chunks))

        if audio.size > max_frames:
            audio = audio[-max_frames:]
        return audio

    def queued_count(self) -> int:
        return self.chunks.qsize()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.chunks.put_nowait(np.empty(0, dtype=np.float32))
        except queue.Full:
            pass

    def _record_loop(self) -> None:
        if self.process is not None:
            try:
                self._process_stream_loop()
            except Exception:
                capture = ProcessLoopbackCapture(self.sample_rate, self.process)
                while not self._stop.is_set():
                    chunk = capture.record(self.seconds)
                    self._put_chunk(chunk)
            return

        device, use_loopback = find_capture_device(self.speaker_name)
        if self.monitor_speaker_name is not None:
            monitor_speaker = find_speaker(self.monitor_speaker_name)
            if monitor_speaker.name == device.name:
                raise RuntimeError("Monitor device must be different from capture device.")
        microphone = (
            sc.get_microphone(device.name, include_loopback=True)
            if use_loopback
            else device
        )
        with microphone.recorder(samplerate=self.sample_rate, channels=1) as recorder:
            while not self._stop.is_set():
                audio = recorder.record(numframes=self.frames)
                chunk = np.asarray(audio, dtype=np.float32).reshape(-1)
                self._put_chunk(chunk)

    def _process_stream_loop(self) -> None:
        capture = StreamingProcessLoopbackCapture(
            self.sample_rate,
            self.process or "",
            self.frames,
            self._put_chunk,
        )
        try:
            capture.start()
            while not self._stop.is_set():
                time.sleep(0.05)
        finally:
            capture.stop()

    def _monitor_loop(self) -> None:
        speaker = find_speaker(self.monitor_speaker_name)
        with speaker.player(samplerate=self.sample_rate, channels=1) as player:
            while not self._stop.is_set():
                try:
                    chunk = self.monitor_chunks.get(timeout=0.1)
                except queue.Empty:
                    continue
                player.play(chunk.reshape(-1, 1))

    def _put_chunk(self, chunk: np.ndarray) -> None:
        with self._recent_lock:
            self.recent_chunks.append(chunk)

        if self.chunks.full():
            try:
                self.chunks.get_nowait()
            except queue.Empty:
                pass
        self.chunks.put(chunk)

        if self.monitor_speaker_name is None:
            return
        if self.monitor_chunks.full():
            try:
                self.monitor_chunks.get_nowait()
            except queue.Empty:
                pass
        self.monitor_chunks.put(chunk)


def rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))
