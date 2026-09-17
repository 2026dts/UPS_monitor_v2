"""
PC / Laptop speaker audible alert engine.
Plays pleasant audio sound effects (WAV chimes/alarms or beeps)
through the PC speaker when a UPS unit reports beeper_sounding,
utility_fail, battery_low, or ups_failed.
"""

import logging
import os
import platform
import sys
import threading
import time

import config
import state

logger = logging.getLogger(__name__)

# Windows native sound support
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# Standard built-in Windows sound presets
SOUND_PRESETS = {
    "chime":  r"C:\Windows\Media\chimes.wav",
    "alarm":  r"C:\Windows\Media\Alarm01.wav",
    "notify": r"C:\Windows\Media\notify.wav",
    "ding":   r"C:\Windows\Media\ding.wav",
    "chord":  r"C:\Windows\Media\chord.wav",
    "ring":   r"C:\Windows\Media\Ring01.wav",
}


def _get_sound_path(style: str) -> str | None:
    """Resolve sound style name or custom path to a valid audio file path."""
    if style in SOUND_PRESETS:
        path = SOUND_PRESETS[style]
        if os.path.exists(path):
            return path
    elif os.path.exists(style):
        return style
    return None


def _play_sound(is_critical: bool = False):
    """Play the configured sound effect or tone."""
    style = getattr(config, "SOUND_STYLE", "chime").lower()

    if HAS_WINSOUND and platform.system() == "Windows":
        wav_path = _get_sound_path(style)
        if wav_path:
            try:
                # Play WAV sound synchronously
                winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
                return
            except Exception as exc:
                logger.debug("[AudioAlert] PlaySound failed: %s", exc)

        # Fallback to tone beep if style is 'beep' or file not found
        try:
            freq = getattr(config, "PC_SPEAKER_BEEP_FREQ", 1000)
            dur = getattr(config, "PC_SPEAKER_BEEP_MS", 400)
            if is_critical:
                winsound.Beep(freq + 300, 200)
                time.sleep(0.08)
                winsound.Beep(freq + 300, 200)
            else:
                winsound.Beep(freq, dur)
        except Exception as exc:
            logger.debug("[AudioAlert] winsound.Beep failed: %s", exc)
    else:
        # Non-Windows terminal bell
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass


def audio_alarm_loop():
    """
    Background worker that monitors UPS state and plays audible alerts
    when alarm conditions or beeper states are active.
    """
    if not getattr(config, "ENABLE_PC_SPEAKER_ALARM", True):
        logger.info("[AudioAlert] PC speaker alarm is disabled in config.")
        return

    style = getattr(config, "SOUND_STYLE", "chime")
    logger.info("[AudioAlert] PC speaker alarm engine started (sound_style='%s')", style)

    while True:
        try:
            critical_active = False
            warning_active = False

            with state.state_lock:
                for unit in config.UPS_UNITS:
                    uid = unit["id"]
                    s = state.ups_state.get(uid, {})
                    if not s.get("connected"):
                        continue
                    ups = s.get("ups")
                    if not ups:
                        continue

                    # Critical conditions (Battery low or UPS hardware fault)
                    if ups.get("battery_low") or ups.get("ups_failed"):
                        critical_active = True
                        break

                    # Warning / On-battery conditions (Utility fail or Beeper sounding)
                    if ups.get("utility_fail") or ups.get("beeper_sounding"):
                        warning_active = True

            if critical_active:
                _play_sound(is_critical=True)
                time.sleep(1.2)
            elif warning_active:
                _play_sound(is_critical=False)
                time.sleep(2.5)
            else:
                # Normal condition — check every second
                time.sleep(1.0)

        except Exception as exc:
            logger.debug("[AudioAlert] Error in audio loop: %s", exc)
            time.sleep(2.0)


def start_audio_thread():
    """Start the audio alert worker in a background daemon thread."""
    t = threading.Thread(
        target=audio_alarm_loop,
        name="audio-alarm-worker",
        daemon=True,
    )
    t.start()
    return t
