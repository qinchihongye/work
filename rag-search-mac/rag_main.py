import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from components.log import init_log, log
from components.env import init_env
from handlers.rag_search import rag_router
import dotenv

dotenv.load_dotenv()


def startup():
    print("init log")
    init_log() 
    print("init env")
    init_env()

    log.info("app start")


def shutdown():
    log.info("app shutdown")


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup()
    yield
    shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(rag_router)


@app.get("/")
async def root():
    return {"ping": "pong"}


if __name__ == "__main__":
    uvicorn.run("rag_main:app",host='0.0.0.0',port=8069,reload=True)