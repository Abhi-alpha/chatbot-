from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import PolicyVersion, Product, Insurer

router = APIRouter(prefix="/policy-versions", tags=["policy-versions"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", summary="List policy versions with UINs")
def list_policy_versions(db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            PolicyVersion.id,
            PolicyVersion.uin,
            PolicyVersion.version_label,
            PolicyVersion.status,
            Product.name.label("product"),
            Insurer.name.label("insurer"),
        )
        .join(Product, PolicyVersion.product_id == Product.id)
        .join(Insurer, Product.insurer_id == Insurer.id)
        .order_by(Insurer.name, Product.name, PolicyVersion.uin)
    ).all()

    return [
        {
            "id": r.id,
            "uin": r.uin,
            "version_label": r.version_label,
            "status": r.status,
            "product": r.product,
            "insurer": r.insurer,
        }
        for r in rows
    ]
