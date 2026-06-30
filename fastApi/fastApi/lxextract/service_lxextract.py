from .src.lang_extract import lx_extract
from .src.reference_verification import verify_reference


def extract_citation(text: str, model: str = "gpt-4.1-mini") -> dict:
    if not text:
        return {"status": -1, "result": []}
    return lx_extract(text, model=model)


def verify_citation(text: str, model: str = "gpt-4.1-mini") -> dict:
    if not text:
        return {"status": -1, "result": []}
    res = lx_extract(text, model=model)
    if res["status"] == 1:
        res = verify_reference(res["result"])
    return res
