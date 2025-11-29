import os
import math
from typing import List, Dict, Any, Optional
import ast
import pandas as pd

from fastapi import APIRouter, HTTPException, Depends, Body
from sqlalchemy import text, select, bindparam
from sqlalchemy.orm import Session

from openai import OpenAI
from pgvector.sqlalchemy import Vector

from app.db import SessionLocal
from app.models import PolicyVersion

router = APIRouter(prefix="/chat", tags=["chat"])

# ---- dependencies ----
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)

# ---- helpers ----
def l2_norm(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v)) or 1.0

# storuing query result to csv file 
def store_query_result(rows):
    print("no of rows :" ,len(rows))
    df = pd.DataFrame([row._asdict() for row in rows])
    df = df.drop(columns=["embedding"])

    # Step 3: Rename columns (optional, if you want custom headers)
    df.columns = [
        "Chunk ID",
        "Section ID",
        "Page From",
        "Page To",
        "Content",
        "Document PDF",
        "similarity_pct"
    ]

    # Step 4: Save to CSV
    df.to_csv(r"D:\Professonal\projects\chatbot\Results\embeddings_query_result.csv", index=False)


def emp_to_float(r):
    if isinstance(r.embedding, str):
        try:
            emb = ast.literal_eval(r.embedding)  # Safely parse string to list
        except Exception:
            emb = [r.embedding]  # Fallback: treat as single string
    elif isinstance(r.embedding, (list, tuple)):
        emb = list(r.embedding)
    else:
        emb = [r.embedding]

# Step 2: Convert each element to float
    try:
        emb = [float(e) for e in emb]
    except ValueError as ve:
        print("Error converting to float:", ve)
        emb = []

    return emb

def cosine_sim(a: List[float], b: List[float]) -> float:
    # assumes same length
    #print("a type ;",type(a[0]), "b type :",type(b[0]))
    dot = sum(x*y for x, y in zip(a, b))
    return dot / (l2_norm(a) * l2_norm(b))

def embed(client: OpenAI, text_in: str) -> List[float]:
    # text-embedding-3-small => 1536 dims (matches your table)
    resp = client.embeddings.create(model="text-embedding-3-small", input=[text_in]).data[0].embedding

    return resp

def build_prompt(question: str, snippets: List[Dict[str, Any]]) -> str:

    #print(snippets)
    """Construct a grounding prompt with citations."""
    lines = [
        "You are a helpful insurance policy assistant chatbot. You search the given sippets and provide best answer"
        "Read all the snippets provided by user and make a understanding what user is asking and answer the user's question using all the provided snippets.",
        "After reading all the snippets if the answer is not in any snippets, then give the user a general answer of that question based on your understanding and mention that this is only general term/answer and it is not present in the snippet",
        "Cite snippet numbers like [S1], [S2] from which you develop the knowledge and when you use them.",
        "",
        "=== SNIPPETS ==="
    ]
    for i, s in enumerate(snippets, 1):
        loc = f"(pages {s.get('page_from')}–{s.get('page_to')})" if s.get("page_from") else ""
        lines.append(f"[S{i}] {loc}\n{s['content']}\n")
    lines += ["=== END SNIPPETS ===", "", f"Question: {question}", "Answer:"]
    return "\n".join(lines)

# ---- request/response schemas ----
from pydantic import BaseModel

class AskRequest(BaseModel):
    uin: str
    question: str
    top_k: Optional[int] = 15          # final snippets to use
    candidate_k: Optional[int] = 100   # how many to pull from DB before re-ranking
    mmr_lambda: Optional[float] = 0.5 # 1.0 = only relevance, 0.0 = only diversity

class AskResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]

# ---- route ----
@router.post("/ask", response_model=AskResponse, summary="Ask a question for a specific UIN")
def ask(
    payload: AskRequest = Body(...),
    db: Session = Depends(get_db),
    client: OpenAI = Depends(get_client),
):
    # 1) Resolve policy_version_id from UIN
    row = db.execute(
        select(PolicyVersion.id).where(PolicyVersion.uin == payload.uin.strip())
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No policy version found for UIN: {payload.uin}")
    policy_version_id = row[0]

    # 2) Embed the question
    qvec = embed(client, payload.question)
    

    print("length of question vector: ",len(qvec))
    print(f"type of qvec: ",type(qvec))
    # 3) Retrieve candidate chunks for this policy version (cosine distance)
    candidate_k = int(payload.candidate_k or 80)
    text_k = min(1, candidate_k) 

    stmt = text("""
        SELECT
          c.id,
          c.section_id,
          c.page_from,
          c.page_to,
          c.content,
          d.source_uri AS document_pdf,
          c.embedding,
          (1 - (c.embedding <=> :qvec)) * 100 AS similarity_pct
        FROM policy_chunk c
        JOIN policy_document d ON d.id = c.document_id
        WHERE c.policy_version_id = :pvid
        --ORDER BY c.embedding <=> :qvec ::vector  -- cosine distance
        LIMIT 150 ;
    """).bindparams(
        bindparam("qvec", type_=Vector(1536)),
    )
    
    rows = db.execute(stmt, {"pvid": policy_version_id,"k": candidate_k, "qvec": qvec}).fetchall()
    store_query_result(rows)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No chunks found for this UIN. Did you ingest a PDF?: {qvec}")

# normalize qtext a bit: lower, strip excess spaces
    qtext = " ".join(payload.question.lower().split())

    txt_stmt = text("""
        SELECT
        c.id,
        c.section_id,
        c.page_from,
        c.page_to,
        c.content,
        d.source_uri AS document_pdf,
        c.embedding
        FROM policy_chunk c
        JOIN policy_document d ON d.id = c.document_id
        WHERE c.policy_version_id = :pvid
        ORDER BY similarity(c.content, :qtext) DESC
        LIMIT :tlimit
    """)

    txt_rows = db.execute(txt_stmt, {"pvid": policy_version_id, "qtext": qtext, "tlimit": text_k}).fetchall()
    #print(txt_rows)
 # --- C) Merge (dedupe by chunk id) ---
    by_id = {}
    for r in rows + txt_rows:
        by_id.setdefault(r.id, r)
    rows = list(by_id.values())
    if not rows:
        raise HTTPException(status_code=404, detail="No chunks found for this UIN. Did you ingest a PDF?")

# --- D) Prepare candidates with similarity to the question (for MMR) ---
    candidates = []
    for r in rows:
        emb = emp_to_float(r)
        sim = cosine_sim(qvec, emb)  # keep your safe cosine_sim
        candidates.append({
            "chunk_id": r.id,
            "section_id": r.section_id,
            "page_from": r.page_from,
            "page_to": r.page_to,
            "content": (r.content or ""),
            "document_pdf": r.document_pdf,
            "embedding": emb,
            "sim_q": sim,
        })

    # 5) MMR re-ranking to reduce redundancy
    #top_k = int(payload.top_k or 15)
    top_k = int(15)
    lam = float(payload.mmr_lambda if payload.mmr_lambda is not None else 0.7)
    selected: List[Dict[str, Any]] = []
    selected_ids = set()

    # start by picking the most relevant candidate
    if candidates:
        best = max(candidates, key=lambda x: x["sim_q"])
        selected.append(best)
        selected_ids.add(best["chunk_id"])

    # iteratively pick items that balance relevance and novelty
    while len(selected) < top_k and len(selected) < len(candidates):
        best_score = None
        best_cand = None
        for c in candidates:
            if c["chunk_id"] in selected_ids:
                continue
            # max similarity to anything already selected (to penalize redundancy)
            if selected:
                max_sim_to_selected = max(
                    cosine_sim(c["embedding"], s["embedding"]) for s in selected
                )
            else:
                max_sim_to_selected = 0.0
            # MMR score
            score = lam * c["sim_q"] - (1.0 - lam) * max_sim_to_selected
            if best_score is None or score > best_score:
                best_score = score
                best_cand = c
        if best_cand is None:
            break
        selected.append(best_cand)
        selected_ids.add(best_cand["chunk_id"])

    # 6) Build snippets for the prompt and for returning to client
    snippets: List[Dict[str, Any]] = []
    for s in selected:
        snippets.append({
            "chunk_id": s["chunk_id"],
            "section_id": s["section_id"],
            "page_from": s["page_from"],
            "page_to": s["page_to"],
            "content": s["content"][:1200],  # cap for prompt size
            "document_pdf": s["document_pdf"],
        })
    
    # 7) Call the chat model with grounded prompt
    prompt = build_prompt(payload.question, snippets)
    chat_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    completion = client.chat.completions.create(
        model=chat_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    answer = completion.choices[0].message.content.strip()
    print("usage - token = ", completion.usage)
    # 8) Return answer with sources (for UI citations)
    return AskResponse(
        answer=answer,
        sources=[{
            "section_id": s["section_id"],
            "page_from": s["page_from"],
            "page_to": s["page_to"],
            "document_pdf": s["document_pdf"],
            "excerpt": s["content"][:400],
        } for s in snippets]
    )
