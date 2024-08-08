from datetime import datetime, timedelta, timezone
from typing import Annotated
import base64
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
from controller import controlador

client_router = APIRouter()

@client_router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db)
) -> controlador.Token:
    user = controlador.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=controlador.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = controlador.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    ) 
    return controlador.Token(access_token=access_token, token_type="bearer")


@client_router.post("/token-audio/")
async def login_audio(
    user: str,audio: UploadFile = File(...), db: Session = Depends(get_db)
    ) -> controlador.Token:
    # Directorio para guardar los archivos de audio
    print("**************")
    UPLOAD_DIRECTORY = "audios"

    herramienta = [{
        "type": "function",
        "function": {
            "name": "login",
            "description": "Funcion POST que permite hacer el login en la aplicación",
            "parameters": {
                "type": "object",
                "properties": {
                    "password": {
                        "type": "string",
                        "description": "Son 3 palabras usadas como contraseña del usuario, debe ir sin espacios ni mayusculas"
                    }
                }
            }
        }
    }]

    # Crear el directorio si no existe
    print("**************")
    if not os.path.exists(UPLOAD_DIRECTORY):
        os.makedirs(UPLOAD_DIRECTORY)
    try:
        # Guardar el archivo en el servidor (opcional)
        webm_path = f"{UPLOAD_DIRECTORY}/{audio.filename}"
        wav_path = webm_path.replace('.webm', '.wav')
        print(wav_path)

        with open(webm_path, "wb") as buffer:
            buffer.write(audio.file.read())
        
        subprocess.run(['ffmpeg', '-i', webm_path, wav_path])
        # with open(f"{UPLOAD_DIRECTORY}/{audio.filename}", "wb") as buffer:
        #     buffer.write(audio.file.read())
        # print(JSONResponse(status_code=200, content={"message": "Audio received", "filename": audio.filename}))
        transcription = transcribe_audio(wav_path)
        print("\n",transcription,"\n")
        response = controlador.call_gpt(transcription, herramienta)
        print("\n",response,"\n")  # Para verificar la respuesta de OpenAI
        if 'choices' in response and response['choices']:
            choice = response['choices'][0]
            if 'message' in choice and 'tool_calls' in choice['message']:
                params = json.loads(choice['message']['tool_calls'][0]['function']['arguments'])
                print(params)
                password = params["password"]
                dbuser = controlador.authenticate_user(db, user, password)
                if not dbuser:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Incorrect username or password",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                access_token_expires = timedelta(minutes=controlador.ACCESS_TOKEN_EXPIRE_MINUTES)
                access_token = controlador.create_access_token(
                    data={"sub": dbuser.username}, expires_delta=access_token_expires
                ) 
                return controlador.Token(access_token=access_token, token_type="bearer")
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})


@client_router.post("/users/", response_model=controlador.User)
async def create_user(user: controlador.UserCreate, db: Session = Depends(get_db)):
    db_user = controlador.get_user(db, user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    new_user = models.User(
        name=user.name,
        email=user.email,
        direccion=user.direccion,
        username=user.username,
        password=user.password,
        
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@client_router.get("/users/me/", response_model=controlador.User)
async def read_users_me(
    current_user: Annotated[controlador.User, Depends(controlador.get_current_active_user)],
):
    return current_user


@client_router.post("/users/{user_id}/transactions/", response_model=controlador.Transaction)
async def create_transaction(current_user: Annotated[controlador.User, Depends(controlador.get_current_active_user)], transaction: controlador.TransactionCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == current_user.id).first()
    print(db_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    new_transaction = models.Transaction(monto=transaction.monto, owner=db_user, fecha=transaction.fecha)
    db.add(new_transaction)
    db.commit()
    db.refresh(new_transaction)
    return new_transaction


@client_router.get("/users/me/transactions/", response_model=list[controlador.Transaction])
async def read_own_transactions(current_user: Annotated[controlador.User, Depends(controlador.get_current_active_user)], db: Session = Depends(get_db), cantidad_transacciones: int = None):
    transactions = db.query(models.Transaction).filter(models.Transaction.id_client == current_user.id).limit(cantidad_transacciones)
    print(transactions)
    return transactions


@client_router.post("/users/me/transactions-audio/")
async def transcribe_audio(current_user: Annotated[controlador.User, Depends(controlador.get_current_active_user)], db: Session = Depends(get_db),file: UploadFile = File(...)):
    try:
        # Subir el archivo a S3
        file_extension = file.filename.split('.')[-1]
        s3_object_name = f"{uuid.uuid4()}.{file_extension}"
        file_url = controlador.upload_to_s3(file, controlador.BUCKET_NAME, s3_object_name)

        # Iniciar el trabajo de transcripción
        job_name = f"transcription-{uuid.uuid4()}"
        transcription_text = controlador.start_transcription_job(file_url, job_name)
        formated_text = controlador.format_text(current_user, db, transcription_text)
        audio_file_path, audio_file_name = controlador.text_to_speech(formated_text)

        # Leer el archivo de audio y codificarlo en base64
        with open(audio_file_path, "rb") as audio_file:
            audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')

        return JSONResponse(content={"formated_text": formated_text, "audio_base64": audio_base64})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))