from fastapi import FastAPI

from common import db as common_db

from routes import router

app = FastAPI(title="InventoryService")


@app.on_event("startup")
def startup() -> None:
    common_db.init_db()
    app.state.delay_ms = 0
    app.state.fail_mode = "none"
    app.state.fail_code = 503


app.include_router(router)
