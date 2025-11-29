from sqlalchemy import String, Date, Integer, Text, ForeignKey, CheckConstraint, Index, select
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from pgvector.sqlalchemy import Vector
from app.db import Base
import uuid

def uuidpk() -> str:
    return str(uuid.uuid4())

# --- Insurer ---
class Insurer(Base):
    __tablename__ = "insurer"
    id: Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuidpk)
    name: Mapped[str] = mapped_column(String, nullable=False)
    products = relationship("Product", back_populates="insurer", cascade="all, delete-orphan")

# --- Product ---
class Product(Base):
    __tablename__ = "product"
    id: Mapped[str]               = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuidpk)
    insurer_id: Mapped[str]       = mapped_column(UUID(as_uuid=False), ForeignKey("insurer.id"), nullable=False)
    line_of_business: Mapped[str] = mapped_column(String, nullable=False)  # 'health' | 'motor'
    name: Mapped[str]             = mapped_column(String, nullable=False)

    insurer = relationship("Insurer", back_populates="products")
    policy_versions = relationship("PolicyVersion", back_populates="product", cascade="all, delete-orphan")
    
    __table_args__ = (CheckConstraint("line_of_business in ('health','motor')", name="ck_lob"),)

# --- PolicyVersion (the glue between product and docs/chunks) ---
class PolicyVersion(Base):
    __tablename__ = "policy_version"
    id: Mapped[str]           = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuidpk)
    product_id: Mapped[str]   = mapped_column(UUID(as_uuid=False), ForeignKey("product.id"), nullable=False)
    # UIN = your business identifier (globally unique)
    uin: Mapped[str]          = mapped_column(String, nullable=False, unique=True)
    version_label: Mapped[str]         = mapped_column(String)
    effective_from: Mapped[Date | None]= mapped_column(Date, nullable=True)
    effective_to: Mapped[Date | None]  = mapped_column(Date, nullable=True)
    approval_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    type_of_product: Mapped[str | None]   = mapped_column(String, nullable=True)
    status: Mapped[str]       = mapped_column(String, default="active")

    product   = relationship("Product", back_populates="policy_versions")
    documents = relationship("PolicyDocument", back_populates="policy_version", cascade="all, delete-orphan")
    chunks    = relationship("PolicyChunk",   back_populates="policy_version", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_policy_version_product", "product_id"),
        Index("ix_policy_version_approval_date", "approval_date"),
        CheckConstraint(
            "product_type IN ('individual','family_floater','group','revision','top_up','other') OR product_type IS NULL",
            name="ck_policy_version_product_type"
        )
    )

    # ---- Helper: resolve UUID from UIN ----
    @staticmethod
    def id_from_uin(db: Session, uin: str) -> str:
        row = db.execute(select(PolicyVersion.id).where(PolicyVersion.uin == uin)).first()
        if not row:
            raise ValueError(f"No PolicyVersion found for UIN: {uin}")
        return row[0]

# --- PolicyDocument (links to PolicyVersion) ---
class PolicyDocument(Base):
    __tablename__ = "policy_document"
    id: Mapped[str]                = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuidpk)
    policy_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("policy_version.id"), nullable=False)
    doc_type: Mapped[str]          = mapped_column(String)  # policy_wording | rider | faq | brochure
    source_uri: Mapped[str]        = mapped_column(String)
    title: Mapped[str | None]      = mapped_column(String, nullable=True)

    policy_version = relationship("PolicyVersion", back_populates="documents")
    chunks         = relationship("PolicyChunk", back_populates="document", cascade="all, delete-orphan")

    # Helper: create by UIN (no need to look up UUID outside)
    @classmethod
    def new_for_uin(cls, db: Session, uin: str, **kwargs) -> "PolicyDocument":
        pv_id = PolicyVersion.id_from_uin(db, uin)
        obj = cls(policy_version_id=pv_id, **kwargs)
        db.add(obj)
        db.flush()  # so obj.id is available immediately
        return obj

# --- PolicyChunk (links to both PolicyVersion and PolicyDocument) ---
class PolicyChunk(Base):
    __tablename__ = "policy_chunk"
    id: Mapped[str]                = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuidpk)
    policy_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("policy_version.id"), nullable=False)
    document_id: Mapped[str]       = mapped_column(UUID(as_uuid=False), ForeignKey("policy_document.id"), nullable=False)
    section_id: Mapped[str | None] = mapped_column(String, nullable=True)
    page_from: Mapped[int | None]  = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None]    = mapped_column(Integer, nullable=True)
    content: Mapped[str]           = mapped_column(Text, nullable=False)

    # IMPORTANT: avoid reserved name "metadata" on the Python side.
    # Keep DB column name as "metadata" but expose it as policy_chunk_metadata in Python.
    policy_chunk_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    embedding: Mapped[list]        = mapped_column(Vector(1536))

    policy_version = relationship("PolicyVersion", back_populates="chunks")
    document       = relationship("PolicyDocument", back_populates="chunks")

    # Helper: create by UIN + doc id
    @classmethod
    def new_for_uin_and_doc(cls, db: Session, uin: str, document_id: str, **kwargs) -> "PolicyChunk":
        pv_id = PolicyVersion.id_from_uin(db, uin)
        obj = cls(policy_version_id=pv_id, document_id=document_id, **kwargs)
        #db.add(obj)
        return obj