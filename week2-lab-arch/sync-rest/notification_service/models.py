from pydantic import BaseModel


class SendRequest(BaseModel):
    order_id: str
    user_id: str
    message: str
