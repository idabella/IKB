"""
Knowledge Base router — searchable document list.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

try:
    from database import get_session
    from models import Document, DocumentCreate, DocumentRead
except ImportError:
    from backend.database import get_session
    from backend.models import Document, DocumentCreate, DocumentRead

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _doc_to_read(d: Document) -> DocumentRead:
    return DocumentRead(
        id=d.id,
        title=d.title,
        type=d.type,
        category=d.category,
        excerpt=d.excerpt,
        machines=json.loads(d.machines_json),
        date=d.date,
        author=d.author,
    )


@router.get("", response_model=List[DocumentRead])
def list_documents(
    q: Optional[str] = None,
    category: Optional[str] = None,
    session: Session = Depends(get_session),
):
    docs = session.exec(select(Document)).all()

    if q:
        ql = q.lower()
        docs = [
            d for d in docs
            if ql in d.title.lower()
            or ql in d.excerpt.lower()
            or ql in d.machines_json.lower()
        ]

    if category and category not in ("All", "Documents"):
        docs = [d for d in docs if d.category == category]

    return [_doc_to_read(d) for d in docs]


@router.get("/{doc_id}", response_model=DocumentRead)
def get_document(doc_id: str, session: Session = Depends(get_session)):
    d = session.get(Document, doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_to_read(d)


@router.post("", response_model=DocumentRead, status_code=201)
def create_document(doc: DocumentCreate, session: Session = Depends(get_session)):
    db_doc = Document.model_validate(doc)
    session.add(db_doc)
    session.commit()
    session.refresh(db_doc)
    return _doc_to_read(db_doc)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, session: Session = Depends(get_session)):
    d = session.get(Document, doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    session.delete(d)
    session.commit()


# ---------------------------------------------------------------------------
# File upload endpoint
# ---------------------------------------------------------------------------

import os
import shutil
import uuid
from datetime import date as _date

from fastapi import File, Form, UploadFile

_UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(_UPLOADS_DIR, exist_ok=True)

ALLOWED_TYPES = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/msword": "DOCX",
    "text/plain": "TXT",
}


@router.post("/upload", response_model=DocumentRead, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    category: str = Form("Documents"),
    author: str = Form(""),
    machines: str = Form("[]"),       # JSON-encoded list of machine names
    excerpt: str = Form(""),
    session: Session = Depends(get_session),
):
    # Validate file type
    content_type = file.content_type or ""
    file_type = ALLOWED_TYPES.get(content_type)
    if not file_type:
        # Fallback: guess from extension
        ext = (file.filename or "").rsplit(".", 1)[-1].upper()
        file_type = ext if ext in ("PDF", "DOCX", "TXT") else None
    if not file_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{content_type}'. Upload PDF, DOCX, or TXT files.",
        )

    # Save file to uploads/
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest = os.path.join(_UPLOADS_DIR, safe_name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Auto-derive title from filename if not provided
    if not title.strip():
        title = (file.filename or "Untitled").rsplit(".", 1)[0].replace("_", " ").replace("-", " ")

    # Auto-derive excerpt from filename / category if not provided
    if not excerpt.strip():
        excerpt = f"{file_type} document uploaded to the {category} knowledge base."

    doc_id = f"doc-{uuid.uuid4().hex[:12]}"
    today = _date.today().isoformat()

    db_doc = Document(
        id=doc_id,
        title=title,
        type=file_type,
        category=category,
        excerpt=excerpt,
        machines_json=machines,
        date=today,
        author=author or "Uploaded",
    )
    session.add(db_doc)
    session.commit()
    session.refresh(db_doc)
    return _doc_to_read(db_doc)
