import io
import os
import wave

SAMPLE_RATE = 16000  # Whisper 16 kHz mono par kaam karta hai
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "whisper-large-v3-turbo")

# Whisper ko andaza dene ke liye ke hum Roman Urdu / English me likhwana chahte hain.
STYLE_PROMPT = (
    "Roman Urdu aur English. Iqra Mom ko Heloo bhej do. "
    "Ammar ko message karo ke main late ho jaunga. Karachi ka mausam batao."
)


def record_until_enter():
    """Mic se tab tak record karo jab tak user Enter na dabaye. WAV bytes return karta hai."""
    import numpy as np
    import sounddevice as sd

    chunks = []
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        callback=lambda data, frames, time, status: chunks.append(data.copy()),
    ):
        input("[mic] Bolein... khatam ho to Enter dabayen. ")

    if not chunks:
        return None
    return to_wav(np.concatenate(chunks))


def to_wav(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16
        w.setframerate(SAMPLE_RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def transcribe(wav_bytes, client=None):
    """Groq Whisper se awaz ko text me badlo."""
    if client is None:
        from groq import Groq

        client = Groq()  # GROQ_API_KEY .env se
    result = client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=("voice.wav", wav_bytes),
        prompt=STYLE_PROMPT,
        temperature=0,
    )
    return result.text.strip()


def listen():
    """Record + transcribe. Kuch na suna ho to khali string."""
    wav = record_until_enter()
    # 0.3 second se kam awaz = galti se Enter dab gaya
    if not wav or len(wav) < SAMPLE_RATE * 2 * 0.3:
        return ""
    return transcribe(wav)
