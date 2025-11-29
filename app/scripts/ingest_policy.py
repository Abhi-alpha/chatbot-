import os, re, math, fitz
from dotenv import load_dotenv
from sqlalchemy import select
from openai import OpenAI
from app.db import SessionLocal
from app.models import PolicyDocument, PolicyChunk, PolicyVersion
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Session

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

CHUNK_TARGET_TOKENS = 900
CHUNK_OVERLAP_TOKENS = 150

SECTION_HINTS = [
    "Eligibility", "Exclusions", "Inclusions", "Coverage", "Waiting Period",
    "Pre-existing", "Claim", "Cashless", "Documents Required", "Deductible",
    "Co-pay", "Sum Insured", "Non-payable", "Consumables", "Network", "Definitions"
]

def rough_token_count(text: str) -> int:
    # crude approximation (good enough for chunking)
    return max(1, len(text.split()) * 1)

def chunk_text(paragraphs, target=CHUNK_TARGET_TOKENS, overlap=CHUNK_OVERLAP_TOKENS):
    chunks, current, size = [], [], 0
    for p in paragraphs:
        t = rough_token_count(p)
        if size + t > target and current:
            chunks.append("\n".join(current))
            # create overlap by carrying last few paras
            overlap_cnt = 0
            while current and overlap_cnt < overlap:
                overlap_cnt += rough_token_count(current[-1])
                current.pop()
            size = sum(rough_token_count(x) for x in current)
        current.append(p)
        size += t
    if current:
        chunks.append("\n".join(current))
    return chunks

def read_pdf(path):
    doc = fitz.open(path)
    pages = []
    for i in range(doc.page_count):
        text = doc.load_page(i).get_text("text")
        text = re.sub(r'[ \t]+', ' ', text).strip()
        pages.append((i+1, text))
    return pages

def guess_section(text):
    for h in SECTION_HINTS:
        if re.search(rf'\b{re.escape(h)}\b', text, re.I):
            return h
    return None

def embed(texts):
    # text-embedding-3-small => 1536 dims
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]

def ingest(pdf_path: str, policy_version_id: str, title: str = None):
    db: Session = SessionLocal()
    try:
        # create a PolicyDocument row
        doc = PolicyDocument(policy_version_id=policy_version_id,
                             doc_type="policy_wording",
                             source_uri=pdf_path,
                             title=title or os.path.basename(pdf_path))
        # db.add(doc); db.flush()

        pages = read_pdf(pdf_path)

        # split each page into paragraphs for better chunking
        paras = []
        page_marks = []
        for pg, text in pages:
            p = [x.strip() for x in text.split("\n") if x.strip()]
            for para in p:
                paras.append((pg, para))
            page_marks.append((pg, len(paras)))

        # chunk by ~900 tokens with small overlap
        only_text = [p for _, p in paras]
        chunk_bodies = chunk_text(only_text)

        # map chunk bodies back to (page_from, page_to)
        results = []
        idx = 0
        for body in chunk_bodies:
            lines = body.split("\n")
            first = lines[0]
            last = lines[-1]
            # find first/last paragraph indices
            # (simple approach: find matching text windows)
            # fallback if duplicates: this is approximate and OK for citations
            start_i = idx
            end_i = idx + len(lines) - 1
            idx = end_i + 1

            page_from = paras[start_i][0] if start_i < len(paras) else None
            page_to   = paras[end_i][0]   if end_i < len(paras) else page_from
            sec = guess_section(body[:400])
            results.append((body, sec, page_from, page_to))

        # embed in batches to avoid token limits
        BATCH = 32
        for i in range(0, len(results), BATCH):
            batch = results[i:i+BATCH]
            embs = embed([b[0] for b in batch])
            for (body, sec, pfrom, pto), vec in zip(batch, embs):
                row = PolicyChunk(
                    policy_version_id=policy_version_id,
                    document_id=doc.id,
                    section_id=sec,
                    page_from=pfrom,
                    page_to=pto,
                    content=body,
                    metadata={}
                )
                # assign embedding as list (pgvector handles it)
                setattr(row, "embedding", vec)
                # db.add(row)
           # db.commit()
        print(f"Ingested {len(results)} chunks from {pdf_path} into policy_version {policy_version_id}")
    finally:
        
       db.close()

if __name__ == "__main__":
    # EDIT these for your PDF and version id
    PDF = r"D:\Professonal\projects\chatbot\data\Acko Health Insurance Policy2020-2021.pdf"
    POLICY_VERSION_ID = input("Enter policy_version_id (from seeding): ").strip()


    ingest(PDF, POLICY_VERSION_ID, title="Acko Health Insurance Policy2020-2021")