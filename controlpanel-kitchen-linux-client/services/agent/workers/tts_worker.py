"""TTS worker — serial TTS playback with PulseAudio/PipeWire mute/unmute."""

from __future__ import annotations

import asyncio
import json
import logging

from models.tasks import Task
from services.agent.base_worker import BaseWorker

logger = logging.getLogger(__name__)

_MUTE_CMD = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"]
_UNMUTE_CMD = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"]


async def _pactl(cmd: list[str]) -> None:
    """Run a pactl command, logging a warning on failure (non-fatal)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(
            "pactl command failed (rc=%d): %s",
            proc.returncode,
            stderr.decode().strip(),
        )


class TTSWorker(BaseWorker):
    """Polls for ``type="tts"`` tasks and plays them via ``espeak-ng``.

    Audio pipeline per task:

    1. Mute the default PulseAudio/PipeWire sink.
    2. Synthesise and play the text with ``espeak-ng``.
    3. Restore (unmute) the sink regardless of success or failure.

    Tasks are processed serially — the next task only starts after the
    current one finishes playing, so audio never overlaps.

    Expected payload fields:
        text (str): Text to speak.  Also checked under ``message``.
        voice (str, optional): espeak-ng voice name (e.g. ``"es"``).  Defaults to the system default.
        speed (int, optional): Words per minute passed to ``-s``.  Defaults to 175.
    """

    task_type = "tts"

    async def handle(self, task: Task) -> None:
        payload = json.loads(task.payload)
        text: str = payload.get("text") or payload.get("message") or ""
        if not text:
            logger.warning("TTS task id=%d has no text; skipping", task.id)
            return

        voice: str | None = payload.get("voice")
        speed: int = int(payload.get("speed", 175))

        espeak_cmd = ["espeak-ng", "-s", str(speed)]
        if voice:
            espeak_cmd += ["-v", voice]
        espeak_cmd.append(text)

        await _pactl(_MUTE_CMD)
        try:
            proc = await asyncio.create_subprocess_exec(
                *espeak_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"espeak-ng failed (rc={proc.returncode}): {stderr.decode().strip()}"
                )
            logger.info("TTS played for task id=%d", task.id)
        finally:
            await _pactl(_UNMUTE_CMD)


def main() -> None:
    from services.agent.logging_config import configure
    configure()
    asyncio.run(TTSWorker().run())


if __name__ == "__main__":
    main()
