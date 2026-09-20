import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.schemas.document import DocumentChunkRead, DocumentRead, DocumentUploadResponse
from app.services.rag.loader import DocumentParseError
from app.services.rag.pipeline import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    files: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # slowapi 通过 request 获取客户端信息并执行限流。
    if not files:
        raise HTTPException(status_code=400, detail="没有上传任何文件")

    # UploadFile.filename 可能为 None（极少见），统一兜底为空串便于后续类型收窄。
    filename = files.filename or ""

    # 1. 验证文件类型（可选）
    allowed_extensions = {".txt", ".md", ".pdf", ".docx", ".xlsx"}

    # 2. 保存上传文件到临时目录
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix.lower()
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
        raise HTTPException(status_code=500, detail="文件保存失败") from e

    # 调用摄入管道（同步处理）
    try:
        document_id = ingest_document(file_path=str(temp_file_path), filename=filename, db=db)
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
    except DocumentParseError as e:
        logger.warning(f"文档内容无效: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"文档摄入失败: {e}")
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}") from e
    finally:
        # 无论成功失败都删除临时文件
        temp_file_path.unlink(missing_ok=True)


@router.get("", response_model=list[DocumentRead])
def list_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 目前 Document 模型没有 user_id 字段，后续可添加权限控制
    # 这里先返回所有文档，实际应过滤当前用户
    docs = db.exec(select(Document)).all()
    return docs


@router.get("/{document_id}/chunks/{chunk_index}", response_model=DocumentChunkRead)
def get_document_chunk(
    document_id: str,
    chunk_index: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回 RAG 回答所引用的共享知识库片段。"""

    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    chunk = db.exec(
        select(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_index == chunk_index,
        )
    ).first()
    if chunk is None:
        raise HTTPException(status_code=404, detail="文档片段不存在")

    return DocumentChunkRead(
        document_id=document.id,
        filename=document.filename,
        file_type=document.file_type,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
    )
