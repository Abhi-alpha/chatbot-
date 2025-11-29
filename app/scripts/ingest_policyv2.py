
import os
import re
import fitz  # PyMuPDF
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy.orm import Session


from app.db import SessionLocal
from app.models import PolicyDocument, PolicyChunk

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in .env")
client = OpenAI(api_key=OPENAI_API_KEY)

MIN_CHARS = 180         # drop very tiny chunks
TARGET_TOKENS = 120     # ~ chunk size (tweak)
OVERLAP_TOKENS = 40     # ~ overlap (tweak)

SECTION_HINTS = [
    "Eligibility", "Exclusions", "Inclusions", "Coverage", "Waiting Period",
    "Pre-existing", "Claim", "Cashless", "Documents Required", "Deductible",
    "Co-pay", "Sum Insured", "Non-payable", "Consumables", "Network", "Definitions"
]

def to_paragraphs(text: str) -> list[str]:
    """
    Turn a page's text into paragraphs:
    - split on blank lines
    - re-wrap hard line breaks inside a block
    """
    blocks = re.split(r"\n\s*\n+", text)  # blank-line split
    paras = []
    for b in blocks:
        # collapse single newlines inside a block
        one = " ".join(ln.strip() for ln in b.splitlines() if ln.strip())
        if one:
            paras.append(one)
    # if a page had no blank lines, fallback: treat each line as a para
    if not paras:
        paras = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return paras


def rough_token_count(text: str) -> int:
    # crude but sufficient for chunking
    return max(1, len(text.split()))


# === A) Safer page reader with debug ===
def read_pdf(path: str):
    doc = fitz.open(path)
    pages = []
    for i in range(doc.page_count):
        txt = doc.load_page(i).get_text("text")
        # normalize spaces; KEEP newlines for line/paragraph splitting
        txt = re.sub(r"[ \t]+", " ", txt).strip()
        pages.append((i + 1, txt))
    # quick sanity: preview first 3 pages
    for j, (pgno, txt) in enumerate(pages[:3], 1):
        print(f"[debug] page {pgno}: {txt[:80]!r}")
    return pages


def guess_section(text: str):
    for h in SECTION_HINTS:
        if re.search(rf"\b{re.escape(h)}\b", text, re.I):
            return h
    return None


def embed(texts: list[str]) -> list[list[float]]:
    # text-embedding-3-small => 1536 dims
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]

def chunk_paragraphs(paras: list[str],
                     target: int = TARGET_TOKENS,
                     overlap: int = OVERLAP_TOKENS) -> list[str]:
    """
    Build chunks from paragraphs with token budget + overlap.
    Returns list of chunk strings.
    """
    out, cur, size = [], [], 0
    for para in paras:
        t = rough_token_count(para)
        if size + t > target and cur:
            out.append("\n".join(cur))
            # make overlap by keeping tail
            keep, kept = [], 0      # 
            for p in reversed(cur):
                if kept >= overlap:
                    break
                kept += rough_token_count(p)
                keep.append(p)
            cur = list(reversed(keep))
            size = sum(rough_token_count(p) for p in cur)
        cur.append(para)
        size += t
    if cur:
        out.append("\n".join(cur))
    # filter out tiny chunks
    out = [c for c in out if len(c) >= MIN_CHARS]
    return out

# === B) Page-scoped chunker ===
# def chunk_page_lines(lines: list[str], target=CHUNK_TARGET_TOKENS, overlap=CHUNK_OVERLAP_TOKENS) -> list[str]:
#     """
#     Split a single page's lines into token-budgeted chunks with overlap.
#     """
#     chunks, current, size = [], [], 0
#     for line in lines:
#         t = rough_token_count(line)
#         if size + t > target and current:
#             chunks.append("\n".join(current))
#             # create overlap from the tail
#             overlap_cnt = 0
#             while current and overlap_cnt < overlap:
#                 overlap_cnt += rough_token_count(current[-1])
#                 current.pop()
#             size = sum(rough_token_count(x) for x in current)
#         current.append(line)
#         size += t
#     if current:
#         chunks.append("\n".join(current))
#     return chunks


def ingest(pdf_path: str, uin: str, title: str | None = None):
    db: Session = SessionLocal()
    try:
        # 1) Create a PolicyDocument by UIN (resolves UUID internally)
        doc = PolicyDocument.new_for_uin(
            db,
            uin=uin,
            doc_type="policy_wording",
            source_uri=pdf_path,
            title=title or os.path.basename(pdf_path),
        )

        # 2) Read PDF → per-page text
        pages = read_pdf(pdf_path)

        # 3) Per-page: split into lines and chunk page-scoped
        results = []
        for pg, text in pages:
            paras = to_paragraphs(text)
            if not paras:
                continue
            chunks = chunk_paragraphs(paras)   # multiple chunks per page now
            for body in chunks:
                sec = guess_section(body[:400])
                results.append((body, sec, pg, pg))  # chunks are page-scoped
        if not results:
            print("[warn] No text extracted from PDF. Is it a scanned image?")
            return

        # 4) Embed + insert chunks in batches
        BATCH = 32
        total = 0
        for i in range(0, len(results), BATCH):
            batch = results[i:i + BATCH]
            embs = embed([b[0] for b in batch])
            for (body, sec, pfrom, pto), vec in zip(batch, embs):
                row = PolicyChunk.new_for_uin_and_doc(
                    db,
                    uin=uin,
                    document_id=doc.id,
                    section_id=sec,
                    page_from=pfrom,
                    page_to=pto,
                    content=body,
                    policy_chunk_metadata={},  # IMPORTANT: matches models.py attribute name/DB column
                )
                row.embedding = vec
            #db.commit()
            total += len(batch)

        print(f"Ingested {total} chunks from {pdf_path} into UIN {uin}")

    finally:
        pass
        
        #db.close()


if __name__ == "__main__":
    # EDIT this PDF path as needed
    PDF = r"D:\Professonal\projects\chatbot\data\Acko Health Insurance Policy2020-2021.pdf"
    UIN = input("Enter Policy UIN: ").strip()   # ACKHLIP20039V012021
    ingest(PDF, UIN, title="Acko Health Insurance Policy2020-2021") 