import os
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session
from typing import List
from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.document import Document
from app.services.rag.pipeline import ingest_document
from app.schemas.document import DocumentUploadResponse, DocumentRead
from app.core.logging import logger
from app.core.limiter import limiter

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=DocumentUploadResponse)
@limiter.limit("10/minute")
async def upload_document(
    files: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not files:
        raise HTTPException(status_code=400, detail="没有上传任何文件")

    # 1. 验证文件类型（可选）
    allowed_extensions = {".txt", ".md", ".pdf", ".docx"}

    # 2. 保存上传文件到临时目录
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(files.filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"文件类型不支持: {ext}")

    # 生成唯一文件名，避免覆盖
    file_id = str(uuid.uuid4())
    temp_file_path = upload_dir / f"{file_id}{ext}"

    try:
        with temp_file_path.open("wb") as buffer:
            shutil.copyfileobj(files.file, buffer)
    except Exception as e:
        logger.error(f"保存文件失败: {e}")
        # 清理已保存的文件
        temp_file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="文件保存失败")

    # 调用摄入管道（同步处理）
    try:
        document_id = ingest_document(
            file_path=str(temp_file_path),
            filename=files.filename,
            db=db
        )
        # 查询刚创建的文档记录
        doc = db.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=500, detail="未查询到该文档记录")

        return DocumentUploadResponse(
            document_id=doc.id,
            filename=doc.filename,
            status=doc.status,
            chunk_count=doc.chunk_count,
        )
    except Exception as e:
        logger.error(f"文档摄入失败: {e}")
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")
    finally:
        # 无论成功失败都删除临时文件
        temp_file_path.unlink(missing_ok=True)


@router.get("", response_model=list[DocumentRead])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 目前 Document 模型没有 user_id 字段，后续可添加权限控制
    # 这里先返回所有文档，实际应过滤当前用户
    from sqlmodel import select
    docs = db.exec(select(Document)).all()
    return docs