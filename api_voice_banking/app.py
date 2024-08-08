from fastapi import FastAPI
from routes.routes import client_router
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.include_router(client_router)

# Define your allowed origins
origins = [
    "http://localhost:4200",
    # Add other origins if needed
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

