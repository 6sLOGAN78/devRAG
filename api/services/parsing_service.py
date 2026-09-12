import os
import json
import uuid
import tempfile
from pathlib import Path
from datetime import datetime

from playhouse.shortcuts import model_to_dict

from api.db.db_models import Document, DocumentTask, DocumentChunk
from api.services.storage_service import storage_service
from deepdoc.parsers.txt_parser import TxtParser
from deepdoc.parsers.pdf_parser import PdfParser
from deepdoc.parsers.md_parser import MarkdownParser
from deepdoc.chunker.general import GeneralChunker
from deepdoc.chunker.qa import QAChunker
from deepdoc.chunker.manual import ManualChunker
from api.db.db_models import Dataset
from deepdoc.chunker.base import TokenCounter
from api.db.connection import db

class ParsingService:
    def __init__(self):
        self.parsers = {
            'txt': TxtParser(),
            'md': MarkdownParser(),
            'markdown': MarkdownParser(),
            'pdf': PdfParser()
        }
        # Chunker instantiated per-task based on parser_id

    def _get_file_extension(self, file_path: str) -> str:
        return file_path.split('.')[-1].lower() if '.' in file_path else ''

    def process_task(self, task_id: str, document_id: str):
        try:
            # 1. Validate task and document
            task = DocumentTask.get_or_none(DocumentTask.id == task_id)
            if not task:
                raise Exception(f"Task {task_id} not found")
            if task.status != 'running':
                raise Exception(f"Task {task_id} is not in 'running' state")

            doc = Document.get_or_none(Document.id == document_id)
            if not doc:
                self._fail_task(task, "Document not found")
                return

            ext = self._get_file_extension(doc.name)
            parser = self.parsers.get(ext)
            if not parser:
                self._fail_task(task, f"Unsupported document type: {ext}")
                return

            # 2. Extract MinIO info
            # The minio_path is typically something like "ragflow/tenant/...".
            # RAGFlow conventionally uses bucket name as the first part. Let's assume bucket is extracted from path, or devRAG uses a static bucket. 
            # In Phase 01 / settings, there's no bucket. Let's assume the path stores the bucket as first segment.
            # devRAG hardcodes the bucket as 'devrag-documents' in Go
            bucket_name = "devrag-documents"
            object_name = doc.minio_path.strip('/')

            # 3. Download to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                temp_path = tmp.name

            try:
                storage_service.download_file(bucket_name, object_name, temp_path)
            except Exception as e:
                os.remove(temp_path)
                self._fail_task(task, f"Storage download failed: {str(e)}")
                return

            # 4. Parse
            try:
                document_structure = parser.parse(Path(temp_path))
            except Exception as e:
                os.remove(temp_path)
                self._fail_task(task, f"Parsing failed: {str(e)}")
                return

            # 5. Chunk
            try:
                dataset = Dataset.get_or_none(Dataset.id == doc.dataset_id)
                parser_id = dataset.parser_id if dataset else "naive"
                
                if parser_id == "qa":
                    chunker = QAChunker()
                elif parser_id == "manual":
                    chunker = ManualChunker()
                else:
                    chunker = GeneralChunker()
                    
                chunks = chunker.chunk(document_structure)
            except Exception as e:
                os.remove(temp_path)
                self._fail_task(task, f"Chunking failed: {str(e)}")
                return

            # 6. Clean up temp file
            os.remove(temp_path)

            # 7. Persist chunks and update task transactionally
            try:
                with DocumentChunk._meta.database.atomic():
                    # Delete existing chunks if idempotency requires replacing
                    DocumentChunk.delete().where(DocumentChunk.document_id == document_id).execute()

                    # Batch insert
                    chunk_data = []
                    for c in chunks:
                        chunk_data.append({
                            "id": str(uuid.uuid4()),
                            "document_id": document_id,
                            "tenant_id": doc.tenant_id,
                            "content": c.text,
                            "chunk_index": c.chunk_index,
                            "content_type": c.content_type,
                            "page_numbers": json.dumps(c.page_numbers),
                            "source_regions": json.dumps([r.model_dump() for r in c.source_regions]),
                            "source_block_ids": json.dumps(c.source_block_ids),
                            "metadata": json.dumps(c.metadata),
                            "token_count": TokenCounter().count(c.text), # Fallback if tokens attribute missing
                            "created_at": datetime.now(),
                            "updated_at": datetime.now()
                        })
                    
                    if chunk_data:
                        batch_size = 100
                        for i in range(0, len(chunk_data), batch_size):
                            DocumentChunk.insert_many(chunk_data[i:i+batch_size]).execute()

                    # 8. Index Chunks to Vector DB
                    from api.services.indexing_service import indexing_service
                    # We pass the real objects that were just saved, or re-fetch them.
                    # 'chunks' contains the DocumentChunk instances generated by chunker, 
                    # but they don't have IDs yet. Let's fetch them from DB to have IDs matching what was saved.
                    saved_chunks = list(DocumentChunk.select().where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index))
                    try:
                        indexing_service.index_document(document_id, doc.dataset_id, saved_chunks)
                    except Exception as e:
                        # If indexing fails, we fail the task and the outer block handles it
                        raise Exception(f"Indexing failed: {e}")

                    # Update task status under lock
                    from common.redis_conn import RedisDistributedLock
                    try:
                        with RedisDistributedLock("update_progress", timeout=10, blocking_timeout=5):
                            # Refetch task to ensure we are updating latest state
                            t = DocumentTask.get_by_id(task.id)
                            t.status = 'success'
                            t.progress = 100
                            t.updated_at = datetime.now()
                            t.save()
                    except Exception as lock_err:
                        # Fallback if Redis fails, just update the DB transactionally
                        task.status = 'success'
                        task.progress = 100
                        task.updated_at = datetime.now()
                        task.save()
                    
                    doc.parse_status = 'success'
                    doc.updated_at = datetime.now()
                    doc.save()

            except Exception as e:
                self._fail_task(task, f"Database persistence failed: {str(e)}")
                return

        except Exception as e:
            # Catch all unexpected outer errors
            print(f"Unhandled error processing task {task_id}: {e}")
            
            

    def _fail_task(self, task: DocumentTask, error_msg: str):
        try:
            from common.redis_conn import RedisDistributedLock
            try:
                with RedisDistributedLock("update_progress", timeout=10, blocking_timeout=5):
                    t = DocumentTask.get_by_id(task.id)
                    t.status = 'failed'
                    t.error_msg = error_msg
                    t.updated_at = datetime.now()
                    t.save()
            except Exception as lock_err:
                task.status = 'failed'
                task.error_msg = error_msg
                task.updated_at = datetime.now()
                task.save()
            
            doc = Document.get_or_none(Document.id == task.document_id)
            if doc:
                doc.parse_status = 'failed'
                doc.save()
        except Exception as e:
            print(f"Failed to record failure for task {task.id}: {e}")

parsing_service = ParsingService()
