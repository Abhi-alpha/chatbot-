from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.sql import literal_column
from sqlalchemy import over
from app.db import SessionLocal
from app.models import Insurer, Product, PolicyVersion, PolicyDocument

router = APIRouter(prefix="/catalog", tags=["catalog"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/filters", summary="Values for dropdowns")
def get_filters(db: Session = Depends(get_db)) -> Dict[str, List[str]]:
    # Distinct UINs
    uins = [r[0] for r in db.execute(select(func.distinct(PolicyVersion.uin)).order_by(PolicyVersion.uin)).all()]
    # Distinct Insurers
    insurers = [r[0] for r in db.execute(select(func.distinct(Insurer.name)).order_by(Insurer.name)).all()]
    # Distinct Product Types
    type_of_product = [r[0] for r in db.execute(
        select(func.distinct(PolicyVersion.type_of_product))
        .where(PolicyVersion.type_of_product.isnot(None))
        .order_by(PolicyVersion.type_of_product)
    ).all()]

    return {
        "uins": uins,
        "insurers": insurers,
        "type_of_product": type_of_product,
    }

@router.get("/search", summary="Search policy versions (rows) by filters")
def search_versions(
    uin: Optional[str] = Query(None, description="Exact UIN"),
    insurer_name: Optional[str] = Query(None, description="Exact insurer name"),
    type_of_product: Optional[str] = Query(None, description="Exact product type"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns rows: UIN, Insurer, Product, Effective Date, Product Type, Approval Date, Document PDF (latest)
    """

    # Latest policy_wording document per policy_version using window function
    rn = func.row_number().over(
        partition_by=PolicyDocument.policy_version_id,
        order_by=PolicyDocument.id.desc()
    ).label("rn")

    latest_doc_sq = (
        select(
            PolicyDocument.policy_version_id.label("pv_id"),
            PolicyDocument.source_uri.label("pdf_path"),
            PolicyDocument.doc_type,
            rn
        )
        .where(PolicyDocument.doc_type == "policy_wording")
        .subquery()
    )

    # Base query with joins
    stmt = (
        select(
            PolicyVersion.uin.label("uin"),
            Insurer.name.label("insurer"),
            Product.name.label("product_name"),
            PolicyVersion.effective_from.label("effective_date"),
            PolicyVersion.type_of_product.label("type_of_product"),
            PolicyVersion.approval_date.label("approval_date"),
            latest_doc_sq.c.pdf_path.label("document_pdf")
        )
        .join(Product, PolicyVersion.product_id == Product.id)
        .join(Insurer, Product.insurer_id == Insurer.id)
        .join(latest_doc_sq, latest_doc_sq.c.pv_id == PolicyVersion.id, isouter=True)
        .where((latest_doc_sq.c.rn == 1) | (latest_doc_sq.c.rn.is_(None)))
        .order_by(Insurer.name, Product.name, PolicyVersion.uin)
    )

    if uin:
        stmt = stmt.where(PolicyVersion.uin == uin.strip())
    if insurer_name:
        stmt = stmt.where(Insurer.name == insurer_name.strip())
    if type_of_product:
        stmt = stmt.where(PolicyVersion.type_of_product == type_of_product.strip())

    rows = db.execute(stmt).all()

    return [
        {
            "uin": r.uin,
            "insurer": r.insurer,
            "product_name": r.product_name,
            "effective_date": r.effective_date,
            "type_of_product": r.type_of_product,
            "approval_date": r.approval_date,
            "document_pdf": r.document_pdf,  # can be None if not ingested yet
        }
        for r in rows
    ]
