# Notes: Citation Extraction FastAPI -> FastMCP

วันที่ทำโน้ต: 2026-06-16

## เป้าหมาย

แปลงโปรเจกต์ Citation Extraction จาก FastAPI endpoint เป็น FastMCP server เพื่อให้ AI client เรียกใช้เป็น MCP tools ได้

## สิ่งที่เปลี่ยนแล้ว

- เปลี่ยน `fastApi/main.py` จาก FastAPI app เป็น FastMCP server
- เพิ่ม MCP tools 2 ตัว:
  - `extract`: ดึง metadata จาก academic reference
  - `verify`: ดึง metadata แล้วตรวจสอบกับ external sources
- เปลี่ยน `fastApi/lxextract/service_lxextract.py` จาก FastAPI router เป็น plain Python service functions:
  - `extract_citation(text, model="gpt-4.1-mini")`
  - `verify_citation(text, model="gpt-4.1-mini")`
- เพิ่มไฟล์ `__init__.py` เพื่อให้ import package ได้ถูกต้อง
- อัปเดต `pyproject.toml` ให้เป็นโปรเจกต์ `citation-extraction-mcp`
- เพิ่ม dependencies ที่โค้ดใช้งานจริง เช่น `fastmcp`, `openai`, `langextract`, `requests`, `rapidfuzz`, `pythainlp`, `semanticscholar`
- refresh `uv.lock` แล้ว
- อัปเดต `fastApi/startService.sh` ให้รัน MCP server ด้วย `uv run python -m fastApi.main`
- อัปเดต `README.md` พร้อมวิธีรัน

## เรื่องสำคัญ

เดิมใน `lang_extract.py` มี hard-coded OpenRouter API key อยู่ใน source code ตอนนี้ย้ายออกแล้ว

ตอนรันต้อง set environment variable ก่อน:

```bash
export OPENROUTER_API_KEY="..."
```

หรือใช้:

```bash
export OPENAI_API_KEY="..."
```

ค่า `OPENAI_BASE_URL` default เป็น:

```text
https://openrouter.ai/api/v1
```

ถ้าต้องการเปลี่ยน backend ให้ set:

```bash
export OPENAI_BASE_URL="..."
```

## วิธีรัน

จาก project root:

```bash
uv run python -m fastApi.main
```

หรือใช้ script:

```bash
./fastApi/startService.sh
```

หลังติดตั้ง package แล้วสามารถใช้ command:

```bash
citation-extraction-mcp
```

## ไฟล์หลัก

- `fastApi/main.py`: MCP server entrypoint
- `fastApi/lxextract/service_lxextract.py`: service functions ที่ MCP tools เรียกใช้
- `fastApi/lxextract/src/lang_extract.py`: LLM extraction logic
- `fastApi/lxextract/src/reference_verification.py`: reference verification logic
- `pyproject.toml`: package metadata และ dependencies
- `uv.lock`: locked dependencies
- `README.md`: วิธีใช้งานสั้น ๆ

## ตรวจสอบที่ทำแล้ว

รัน compile check ผ่าน:

```bash
python3 -m compileall main.py fastApi
```

รัน import check ผ่านด้วย `uv run`:

```text
FastMCP
```

ทดสอบ empty input แล้วคืน:

```python
{"status": -1, "result": []}
```

## หมายเหตุสำหรับครั้งหน้า

- ถ้าจะ test extraction จริง ต้องมี API key และ network access
- `verify` จะเรียก external APIs หลายตัว เช่น Crossref, Semantic Scholar, OpenAlex, PubMed, DataCite และ ThaiJO/AIForThai
- ถ้า `uv run` ติด permission/cache ใน sandbox ให้รันแบบอนุญาต access cache หรือรันใน shell ปกติ
- ยังไม่ได้สร้าง automated tests
- ยังมีไฟล์ `:Zone.Identifier` จาก Windows metadata อยู่ใน repo แต่ไม่ได้แตะ เพราะไม่เกี่ยวกับงานนี้
