from __future__ import annotations

import base64
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..config import Settings
from ..schemas import ShortsDraft
from .pexels import PexelsClient

logger = logging.getLogger(__name__)


class ShortsCreator:
    """Creates draft-only Shorts (1080x1920 MP4); it never uploads them."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pexels = PexelsClient(api_key=settings.pexels_api_key)
        self.shorts_dir = settings.shorts_dir
        self.shorts_dir.mkdir(parents=True, exist_ok=True)
        self.voice_name = settings.voice_name

    def get_duration(self, file_path: Path) -> float:
        """Get media duration in seconds using ffprobe."""
        if not file_path.exists():
            return 0.0
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception as exc:
            logger.warning("ffprobe error on %s: %s", file_path, exc)
        return 0.0

    def generate_voiceover(self, text: str, output_path: Path) -> float:
        """Generate narration locally with Windows SAPI, with an offline silent fallback."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if sys.platform == "win32" and not espeak:
            wav_path = output_path.with_suffix(".wav")
            text_path = output_path.with_suffix(".txt")
            text_path.write_text(text, encoding="utf-8")
            # The script only receives base64-encoded literal paths and never interpolates
            # article text into PowerShell code.
            ps_script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{base64.b64encode(self.voice_name.encode()).decode()}'))
if ($voice -and ($synth.GetInstalledVoices().VoiceInfo.Name -contains $voice)) {{ $synth.SelectVoice($voice) }}
$textPath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{base64.b64encode(str(text_path.resolve()).encode()).decode()}'))
$wavPath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{base64.b64encode(str(wav_path.resolve()).encode()).decode()}'))
$synth.SetOutputToWaveFile($wavPath)
$synth.Speak([IO.File]::ReadAllText($textPath, [Text.Encoding]::UTF8))
$synth.Dispose()
"""
            encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
            try:
                spoken = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if spoken.returncode == 0 and wav_path.exists() and wav_path.stat().st_size > 100:
                    converted = subprocess.run(
                        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "3", str(output_path)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if converted.returncode == 0 and output_path.exists() and output_path.stat().st_size > 100:
                        duration = self.get_duration(output_path)
                        return duration if duration > 0 else 10.0
                logger.warning("Local Windows narration failed: %s", spoken.stderr.strip())
            except Exception as exc:
                logger.warning("Local Windows narration failed: %s", exc)
            finally:
                text_path.unlink(missing_ok=True)
                wav_path.unlink(missing_ok=True)

        # eSpeak NG is fully local and provides reliable narration on Windows
        # installations where the optional SAPI voice pack is unavailable.
        if espeak:
            wav_path = output_path.with_suffix(".wav")
            try:
                spoken = subprocess.run(
                    [espeak, "-v", "en-us", "-s", "165", "-w", str(wav_path), text],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if spoken.returncode == 0 and wav_path.exists() and wav_path.stat().st_size > 100:
                    converted = subprocess.run(
                        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "3", str(output_path)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if converted.returncode == 0 and output_path.exists() and output_path.stat().st_size > 100:
                        duration = self.get_duration(output_path)
                        return duration if duration > 0 else 10.0
                logger.warning("Local eSpeak narration failed: %s", spoken.stderr.strip())
            except Exception as exc:
                logger.warning("Local eSpeak narration failed: %s", exc)
            finally:
                wav_path.unlink(missing_ok=True)

        # Offline fallback keeps video generation autonomous even if no speech
        # voice is installed.
        try:
            cmd = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "10",
                "-q:a", "9", "-acodec", "libmp3lame",
                str(output_path)
            ]
            subprocess.run(cmd, capture_output=True, check=False)
            return 10.0
        except Exception as exc:
            logger.error("Failed to generate fallback audio: %s", exc)
            return 0.0

    def _normalize_clip(self, clip_path: Path, output_clip: Path, duration: float) -> bool:
        """Scale and crop a clip to standard vertical 1080x1920 portrait without subtitles or text."""
        output_clip.parent.mkdir(parents=True, exist_ok=True)
        # Scale to fill 1080x1920 and center crop, no subtitles
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
        for vcodec in ("libx264", "mpeg4"):
            cmd = [
                "ffmpeg", "-y",
                "-i", str(clip_path),
                "-t", str(duration),
                "-vf", vf,
                "-an",
                "-c:v", vcodec,
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                str(output_clip),
            ] if vcodec == "libx264" else [
                "ffmpeg", "-y",
                "-i", str(clip_path),
                "-t", str(duration),
                "-vf", vf,
                "-an",
                "-c:v", vcodec,
                "-pix_fmt", "yuv420p",
                str(output_clip),
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.returncode == 0 and output_clip.exists() and output_clip.stat().st_size > 1000:
                    return True
            except Exception as exc:
                logger.warning("Failed to normalize clip with %s: %s", vcodec, exc)
        return False

    def _create_ambient_background(self, output_path: Path, duration: float) -> bool:
        """Generate a sleek, dynamic gradient 1080x1920 background without any subtitles or text."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        vf = "color=c=0x111827:s=1080x1920:r=30"
        for vcodec in ("libx264", "mpeg4"):
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", vf,
                "-t", str(duration),
                "-c:v", vcodec,
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ] if vcodec == "libx264" else [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", vf,
                "-t", str(duration),
                "-c:v", vcodec,
                "-pix_fmt", "yuv420p",
                str(output_path),
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
                    return True
            except Exception as exc:
                logger.warning("Failed to create ambient background with %s: %s", vcodec, exc)
        return False

    def assemble_video(self, audio_path: Path, clips: list[Path], output_video: Path, total_duration: float) -> bool:
        """Combine video footage and voiceover audio into clean 1080x1920 MP4 (strictly no subtitles)."""
        output_video.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = output_video.parent / f"temp_{output_video.stem}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            normalized_clips: list[Path] = []
            if clips:
                # Distribute duration across available clips
                clip_dur = max(3.0, total_duration / len(clips))
                for i, clip in enumerate(clips):
                    norm_out = temp_dir / f"norm_{i}.mp4"
                    if self._normalize_clip(clip, norm_out, clip_dur):
                        normalized_clips.append(norm_out)

            if not normalized_clips:
                # Create ambient 1080x1920 visual background
                ambient_out = temp_dir / "ambient.mp4"
                if self._create_ambient_background(ambient_out, total_duration + 0.5):
                    normalized_clips.append(ambient_out)

            if not normalized_clips:
                return False

            # Create concat list file
            concat_file = temp_dir / "concat.txt"
            with open(concat_file, "w", encoding="utf-8") as f:
                # Repeat clips if total duration exceeds clip length
                current_time = 0.0
                while current_time < total_duration:
                    for c in normalized_clips:
                        f.write(f"file '{c.resolve().as_posix()}'\n")
                        current_time += self.get_duration(c) or 5.0
                        if current_time >= total_duration:
                            break

            # Final render: stitch video + voiceover audio (no subtitles, pure clean video)
            for vcodec in ("libx264", "mpeg4"):
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-i", str(audio_path),
                    "-c:v", vcodec,
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    str(output_video),
                ] if vcodec == "libx264" else [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-i", str(audio_path),
                    "-c:v", vcodec,
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    str(output_video),
                ]
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                    if res.returncode == 0 and output_video.exists() and output_video.stat().st_size > 1000:
                        return True
                except Exception as exc:
                    logger.warning("Assemble video with %s failed: %s", vcodec, exc)
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def create_short(self, draft: ShortsDraft, run_id: str) -> ShortsDraft:
        """Fully autonomous draft production pipeline; no upload is performed."""
        if not draft.script.strip():
            return draft

        run_dir = self.shorts_dir / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        audio_path = run_dir / "voiceover.mp3"
        final_video_path = self.shorts_dir / f"short_{run_id}.mp4"

        # 1. Generate Voiceover Audio
        duration = self.generate_voiceover(draft.script, audio_path)
        if duration <= 0:
            duration = 15.0

        # 2. Fetch Pexels Portrait Footage (if configured)
        clips: list[Path] = []
        if self.pexels.is_configured and draft.visual_keywords:
            clips = self.pexels.fetch_footage_for_keywords(
                keywords=draft.visual_keywords,
                output_dir=run_dir / "raw_clips",
                max_clips=3
            )

        # 3. Assemble Vertical Video with Voiceover (no subtitles)
        success = self.assemble_video(audio_path, clips, final_video_path, duration)

        draft.video_path = str(final_video_path.resolve()) if success else ""
        draft.duration_seconds = round(duration, 2)
        draft.generated = success
        return draft
