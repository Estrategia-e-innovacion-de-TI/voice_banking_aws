from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel
from sqlalchemy.orm import Session
from config.database import engine, get_db
from models import models
import os
from fastapi import APIRouter, HTTPException
import whisper
import openai
import json
import unicodedata
import requests
import subprocess
# Modelo de transcripción con AWS
import boto3
import time
import uuid
# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = "bacec3dab48fd1c796ce9b7bfa8c722a16ca58b39598496f308f6065df3f44b5"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

openai.api_type = os.environ["OPENAI_API_TYPE"]
openai.api_version = os.environ["AZURE_OPENAI_VERSION_GPT4"]
openai.api_base = os.environ["AZURE_OPENAI_ENDPOINT_GPT4"]
openai.api_key = os.environ["AZURE_OPENAI_API_KEY_GPT4"]

session = boto3.Session(profile_name='BCO-PocRole-538430999815')
# Configura el cliente S3 y Transcribe
s3_client = session.client('s3')
transcribe_client = session.client('transcribe')
polly_client = session.client('polly')

# Tu bucket de S3
BUCKET_NAME = "audios-poc-voice-banking-aws"


models.Base.metadata.create_all(bind=engine)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    id: int
    name: str
    email: str | None = None
    direccion: str
    username: str
    password: str
    class Config:
        orm_mode = True


class UserInDB(User):
    password: str


class UserCreate(BaseModel):
    name: str
    email: str | None = None
    direccion: str
    username: str
    password: str


class Transaction(BaseModel):
    id_client: int
    monto: float
    fecha: datetime
    class Config:
        orm_mode = True


class TransactionCreate(BaseModel):
    monto: float
    fecha: datetime



oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()



def get_user(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not eliminar_tildes(password.lower().replace(" ", "")) == eliminar_tildes(user.password.lower().replace(" ", "")):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def eliminar_tildes(input_str):
    # Normalizar caracteres en forma NFD (Descomposición canónica)
    normalized_str = unicodedata.normalize('NFD', input_str)
    # Filtrar caracteres para mantener solo aquellos sin marcas diacríticas
    no_tildes_str = ''.join([c for c in normalized_str if not unicodedata.combining(c)])
    return no_tildes_str


# FUNCIONES DE AUDIO
def transcribe_audio(filename):
    model = whisper.load_model("base")
    result = model.transcribe(filename)
    return result["text"]


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
    formatted_transactions = []
    for transaction in transacciones:
        # Example format: "Date: {date}, Amount: {amount}, Description: {description}"
        formatted_str = f"fecha: {transaction.fecha}, monto: {transaction.monto}"
        formatted_transactions.append(formatted_str)
    # Join all formatted transaction strings with a newline character
    prompt = (
    "Quiero que formatees la siguiente lista de transacciones en un texto amigable para un cliente. "
    "Cada monto debe ser leído como pesos colombianos, y al final debes calcular y mencionar el total de las transacciones.\n\n"
    "RECUERDA: listar todas las transacciones y formatearlas de la sigueinte manera: Respuesta formateada: 100 = cien pesos colombianos, 1000= mil pesos colombianos"
    f"Transacciones: {formatted_transactions}\n\n"
    )
    
    

    openai_response = openai.ChatCompletion.create(
        engine="gpt-4-32k", #"text-davinci-003",
        messages=[{"role": "user", "content": prompt}],
        #prompt=prompt,
        max_tokens=100
    )

    #return openai_response.choices[0].text.strip()
    return openai_response.choices[0]["message"]["content"]


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    # if current_user.disabled:
        # raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_user_transactions(
        token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return

def upload_to_s3(file: UploadFile, bucket_name: str, object_name: str):
    try:
        s3_client.upload_fileobj(file.file, bucket_name, object_name)
        file_url = f"https://{bucket_name}.s3.amazonaws.com/{object_name}"
        return file_url
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def start_transcription_job(file_uri, job_name, language_code='es-US'):
    try:
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': file_uri},
            MediaFormat='wav',  # Cambia esto según el formato de tu archivo: 'mp3', 'mp4', 'wav', 'flac'
            LanguageCode=language_code
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    while True:
        status = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
            break
        time.sleep(10)

    if status['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
        transcription_url = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
        transcription_text = extract_transcription_text(transcription_url)
        return transcription_text
    else:
        raise HTTPException(status_code=500, detail="Transcription job failed")


def extract_transcription_text(transcription_url):
    try:
        response = requests.get(transcription_url)
        response.raise_for_status()
        transcription_data = response.json()
        transcription_text = transcription_data['results']['transcripts'][0]['transcript']
        return transcription_text
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def text_to_speech(text, output_format='mp3', voice_id='Lucia'):
    try:
        response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat=output_format,
            VoiceId=voice_id
        )
        audio_stream = response['AudioStream'].read()
        audio_file_name = f"{uuid.uuid4()}.mp3"
        audio_file_path = f"/tmp/{audio_file_name}"

        with open(audio_file_path, 'wb') as audio_file:
            audio_file.write(audio_stream)

        return audio_file_path, audio_file_name
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
def format_text(current_user: Annotated[User, Depends(get_current_active_user)], db: Session = Depends(get_db),transcription_text: str = ''):
    herramienta = [{
        "type": "function",
        "function": {
            "name": "get_transaction",
            "description": "Funcion GET que utilizo para obtener datos de las transferencias del servidor",
            "parameters": {
                "type": "object",
                "properties": {
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
    }]
    try:
        response = call_gpt(transcription_text, herramienta)
        print("\n",response,"\n")  # Para verificar la respuesta de OpenAI
        if 'choices' in response and response['choices']:
            choice = response['choices'][0]
            if 'message' in choice and 'tool_calls' in choice['message']:
                params = json.loads(choice['message']['tool_calls'][0]['function']['arguments'])
                cantidad_transacciones = params["cantidad_transacciones"]
                print(type(cantidad_transacciones), cantidad_transacciones)
                transactions = db.query(models.Transaction).filter(models.Transaction.id_client == current_user.id).limit(cantidad_transacciones).all()
            
                print("*************************")
                print(transactions)
                # Formatear la respuesta usando GPT
                mensaje_formateado = str(formatear_respuesta_gpt(transactions))
                print(mensaje_formateado)  # Para verificar el formato
        return mensaje_formateado
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})