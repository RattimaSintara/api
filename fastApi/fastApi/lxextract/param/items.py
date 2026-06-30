from pydantic import BaseModel
from typing import Optional

class InputItem(BaseModel):
    text: Optional[str] = ""
