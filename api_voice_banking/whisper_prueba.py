
import pyaudio
import wave
import whisper
import tempfile

# Configuración de PyAudio
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 10

# Inicializar PyAudio
audio = pyaudio.PyAudio()

# Iniciar grabación
print("Grabando...")
stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
frames = []

for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK)
    frames.append(data)

print("Grabación terminada.")

# Detener grabación
stream.stop_stream()
stream.close()
audio.terminate()

# Guardar la grabación en un archivo temporal
with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio_file:
    wf = wave.open(temp_audio_file.name, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    temp_audio_file_name = temp_audio_file.name

# Usar Whisper para transcribir el archivo de audio
model = whisper.load_model("small")
result = model.transcribe(temp_audio_file_name)

# Imprimir la transcripción
print("Transcripción:")
print(result["text"])

# Borrar el archivo temporal
import os
os.remove(temp_audio_file_name)
