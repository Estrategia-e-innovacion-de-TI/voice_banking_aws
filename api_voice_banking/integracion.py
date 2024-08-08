import openai
import json
import requests
import whisper
import sounddevice as sd
import wavio
import numpy as np
from fastapi import FastAPI, HTTPException
from gtts import gTTS
import os
from dotenv import load_dotenv
import os
load_dotenv()


openai.api_type = os.environ["OPENAI_API_TYPE"]
openai.api_version = os.environ["AZURE_OPENAI_VERSION_GPT4"]
openai.api_base = os.environ["AZURE_OPENAI_ENDPOINT_GPT4"]
openai.api_key = os.environ["AZURE_OPENAI_API_KEY_GPT4"]


# Función para grabar el audio de la petición del cliente
def record_audio(filename, duration, fs=44100):
    print(sd.query_devices())
    # Get the default input device info
    input_device_info = sd.query_devices(kind='input')
    print(input_device_info)

    # Check the maximum number of input channels for the default input device
    max_input_channels = input_device_info['max_input_channels']
    print(f"Maximum input channels: {max_input_channels}")

    # Set the channels to the maximum supported number of input channels
    channels = min(2, max_input_channels)

    print("Recording...")
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=channels, dtype=np.int16)
    sd.wait()
    wavio.write(filename, recording, fs, sampwidth=2)
    print("Recording complete.")

# Función para transcribir audio a texto usando Whisper
def transcribe_audio(filename):
    model = whisper.load_model("base")
    result = model.transcribe(filename)
    return result["text"]

# Función para sacar los parámetros de la transcripción para la API
def call_gpt(prompt_template, tool):
    response = openai.ChatCompletion.create(
        engine="gpt-4-32k",
        temperature=0.0,
        request_timeout=300,
        messages=[{"role": "user", "content": prompt_template}],
        tools=tool
    )
    return response

# Función para formatear los datos usando GPT
def formatear_respuesta_gpt(transacciones):
    prompt = (
    "Quiero que formatees la siguiente lista de transacciones en un texto amigable para un cliente. "
    "Cada monto debe ser leído como pesos colombianos, y al final debes calcular y mencionar el total de las transacciones.\n\n"
    "un monto = 100 lo debes leer como cien pesos colombianos\n"
    "un monto = 1000 lo debes leer como mil pesos colombianos\n RECUERDA: listar todas las trasacciones"
    f"Transacciones: {transacciones}\n\n"
    "Respuesta formateada: "
    )
    
    

    openai_response = openai.ChatCompletion.create(
        engine="gpt-4-32k", #"text-davinci-003",
        messages=[{"role": "user", "content": prompt}],
        #prompt=prompt,
        max_tokens=100
    )

    #return openai_response.choices[0].text.strip()
    return openai_response.choices[0]["message"]["content"]

# Graba audio
record_audio("audio.wav", duration=6)

# Transcribe audio
transcription = transcribe_audio("audio.wav")


# Usar la transcripción como prompt para GPT
herramienta = [{
    "type": "function",
    "function": {
        "name": "get_transaction",
        "description": "Funcion GET que utilizo para obtener datos de las transferencias del servidor",
        "parameters": {
            "type": "object",
            "properties": {
                "user": {
                    "type": "string",
                    "description": "id del usuario, alias, etc"
                },
                "cantidad_transacciones": {
                    "type": "integer",
                    "description": "Cantidad de txs"
                },
                "tiempo": {
                    "type": "string",
                    "enum": ["2022", "2023", "2024"]
                }
            }
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "login",
        "description": "Funcion POST que permite hacer el login en la aplicación",
        "parameters": {
            "type": "object",
            "properties": {
                "username":{
                    "type": "string",
                    "description": "username del usuario, usualmente dado de forma deletreada"
                },
                "password": {
                    "type": "string",
                    "description": "Son 3 palabras usadas como clave del usuario"
                }
            }
        }
    }
}]

response = call_gpt(transcription, herramienta)
print(response)  # Para verificar la respuesta de OpenAI

if 'choices' in response and response['choices']:
    choice = response['choices'][0]
    if 'message' in choice and 'tool_calls' in choice['message']:
        params = json.loads(choice['message']['tool_calls'][0]['function']['arguments'])
        print(params)

        client_id = params["user"]
        cantidad_transacciones = params["cantidad_transacciones"]
        año = params.get("año")

        ## Realizar una solicitud HTTP a la API de FastAPI
        #api_response = requests.get(f"http://localhost:8000/clients/{client_id}/transactions", params={
        #    "cantidad_transacciones": cantidad_transacciones,
        #    "año": año,
        #    "client_id": client_id
        #})

        # Realizar la solicitud GET a la API con parámetros de consulta
        api_response = requests.get(
        f"http://localhost:8000/clients/{client_id}/transactions",
        params={
        "cantidad_transacciones": cantidad_transacciones,
        "año": año
        }
        )

        # Verifica que la solicitud fue exitosa
        if api_response.status_code == 200:
            try:
                response_data = api_response.json()  # Deserializa la respuesta JSON
            except ValueError:
                print("Error al decodificar la respuesta JSON")
                response_data = []

            # Formatear la respuesta usando GPT
            mensaje_formateado = str(formatear_respuesta_gpt(response_data))
            print(mensaje_formateado)  # Para verificar el formato

            # Convertir el texto a voz en español
            tts = gTTS(text=mensaje_formateado, lang='es')
#
            ## Guardar el audio en un archivo
            tts.save("output.mp3")
#
            ## Reproducir el archivo de audio (opcional)
            os.system("start output.mp3")  # En Windows

            
        else:
            print("Error al obtener datos de la API: ", api_response.status_code)
    else:
        print("No se encontraron tool_calls en la respuesta de OpenAI.")
else:
    print("No se encontraron choices en la respuesta de OpenAI.")