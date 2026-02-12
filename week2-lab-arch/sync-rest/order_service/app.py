from fastapi import FastAPI

from common import db as common_db

from routes import router

app = FastAPI(title="OrderService")


@app.on_event("startup")
def startup() -> None:
    common_db.init_db()
    # Defaults are tuned for lab scenarios.
    app.state.inventory_timeout_s = 3.0
    app.state.notification_timeout_s = 2.0


app.include_router(router)
