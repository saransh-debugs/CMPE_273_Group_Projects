from fastapi import FastAPI

from common import db as common_db

from routes import router

app = FastAPI(title="NotificationService")


@app.on_event("startup")
def startup() -> None:
    common_db.init_db()


app.include_router(router)
