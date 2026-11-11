from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

from trove.adapters.process import run_command
from trove.content_package import guess_mime
from trove.errors import ProcessingError, ValidationError
from trove.ports import AudioResult, StageContext

SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav"}
TRANSCODE_SUFFIX = ".m4a"
TRANSCODE_MIME = "audio/mp4"
INVALID_MEDIA_CODE = "upload.invalid_media"
PROBE_UNAVAILABLE_CODE = "upload.probe_unavailable"


class FfmpegAudioExtractor:
    def __init__(self, binary: str = "ffmpeg", probe_binary: str = "ffprobe") -> None:
        self.binary = binary
        self.probe_binary = probe_binary

    def probe(self, source: Path, *, kind: str) -> None:
        if shutil.which(self.probe_binary) is None:
            raise ValidationError(
                "Media validation requires FFmpeg/ffprobe; run: brew install ffmpeg",
                details={"code": PROBE_UNAVAILABLE_CODE},
            )
        try:
            result = subprocess.run(
                [
                    self.probe_binary,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "json",
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise _invalid_media("Could not validate the media file") from exc
        if result.returncode != 0:
            raise _invalid_media("Media file is corrupt or unsupported")
        try:
            streams = json.loads(result.stdout or "{}").get("streams") or []
        except json.JSONDecodeError as exc:
            raise _invalid_media("Media file is corrupt or unsupported") from exc
        codec_types = {str(stream.get("codec_type")) for stream in streams}
        expected = "video" if kind == "video" else "audio"
        if expected not in codec_types:
            raise _invalid_media(f"File does not contain {expected} data")

    def extract(
        self,
        source: Path,
        output_dir: Path,
        *,
        force_transcode: bool,
        context: StageContext,
    ) -> AudioResult:
        if shutil.which(self.binary) is None or shutil.which(self.probe_binary) is None:
            raise ProcessingError("ffmpeg.missing", "FFmpeg/ffprobe is missing; install them first")
        output_dir.mkdir(parents=True, exist_ok=True)
        ensure_probe = run_command(
            context,
            [
                self.probe_binary,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(source),
            ],
            timeout=60,
            error_code="ffmpeg.failed",
        )
        duration = _parse_duration(ensure_probe.stdout)
        if not force_transcode and source.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES:
            suffix = source.suffix.lower()
            destination = output_dir / f"audio{suffix}"
            shutil.copyfile(source, destination)
            return AudioResult(
                path=destination,
                duration_sec=duration,
                mime=guess_mime(destination.name),
                extension=suffix,
            )
        destination = output_dir / f"audio{TRANSCODE_SUFFIX}"
        temporary = output_dir / f".audio-{uuid.uuid4().hex}.m4a"
        result = run_command(
            context,
            [
                self.binary,
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            timeout=3600,
            error_code="ffmpeg.failed",
        )
        if result.returncode != 0 or not temporary.exists() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            raise ProcessingError(
                "ffmpeg.failed",
                "FFmpeg audio extraction failed",
                details={"stderr": result.stderr[-2000:]},
            )
        temporary.replace(destination)
        return AudioResult(
            path=destination,
            duration_sec=duration,
            mime=TRANSCODE_MIME,
            extension=TRANSCODE_SUFFIX,
        )


def _invalid_media(message: str) -> ValidationError:
    return ValidationError(message, details={"code": INVALID_MEDIA_CODE})


def _parse_duration(value: str) -> float | None:
    try:
        duration = float(value.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return duration if duration >= 0 else None
