# app/scripts/similarity_test.py
import os
from dotenv import load_dotenv
from sqlalchemy import text, create_engine, bindparam
from pgvector.sqlalchemy import Vector
from openai import OpenAI

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"), pool_pre_ping=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embed(q):
    return client.embeddings.create(model="text-embedding-3-small", input=[q]).data[0].embedding

q = "What is the waiting period for pre-existing diseases?"
vec = embed(q)

stmt = text("""
    SELECT section_id, page_from, page_to, content
    FROM policy_chunk
    ORDER BY embedding <#> :qvec
    LIMIT 3
""").bindparams(bindparam("qvec", type_=Vector(1536)))  # 👈 tell SQLAlchemy this param is a vector

with engine.connect() as conn:
    rows = conn.execute(stmt, {"qvec": vec}).fetchall()

for r in rows:
    print("\n---")
    print("Section:", r.section_id, "| pages:", r.page_from, "-", r.page_to)
    print((r.content or "")[:400], "...")
