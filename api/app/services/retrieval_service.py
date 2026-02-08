from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from openai import AsyncOpenAI

from app.models.document import Chunk, Document, DocumentStatus
from app.config import settings
from app.db import async_session


class RetrievalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Search for relevant chunks using vector similarity.
        Returns list of chunks with scores.
        Uses a separate session to avoid transaction conflicts.
        """
        try:
            # Generate embedding for query
            embedding = await self._embed(query)
            
            # Use separate session for vector search to avoid transaction conflicts
            async with async_session() as session:
                # Vector similarity search
                # Using pgvector's cosine distance
                sql = text("""
                    SELECT 
                        c.id,
                        c.content,
                        c.section_path,
                        c.document_id,
                        d.filename,
                        d.lender,
                        1 - (c.embedding <=> :embedding::vector) as similarity
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE d.status = 'active'
                    ORDER BY c.embedding <=> :embedding::vector
                    LIMIT :limit
                """)
                
                result = await session.execute(
                    sql,
                    {"embedding": str(embedding), "limit": top_k}
                )
                rows = result.fetchall()
                
                return [
                    {
                        "id": str(row.id),
                        "content": row.content,
                        "section_path": row.section_path,
                        "document_id": str(row.document_id),
                        "filename": row.filename,
                        "lender": row.lender,
                        "similarity": float(row.similarity)
                    }
                    for row in rows
                ]
        except Exception as e:
            print(f"RetrievalService.search error: {e}")
            # Return empty list on error to avoid breaking the flow
            return []
    
    async def _embed(self, text: str) -> list[float]:
        """Generate embedding for text using OpenAI."""
        response = await self.client.embeddings.create(
            model=settings.embedding_model,
            input=text
        )
        return response.data[0].embedding
    
    async def embed_and_store(self, document_id: str, chunks: list[dict]) -> None:
        """
        Generate embeddings for chunks and store them.
        """
        for i, chunk in enumerate(chunks):
            embedding = await self._embed(chunk["content"])
            
            chunk_obj = Chunk(
                document_id=document_id,
                content=chunk["content"],
                section_path=chunk.get("section_path"),
                chunk_index=i,
                is_table=chunk.get("is_table", False),
                embedding=embedding
            )
            self.db.add(chunk_obj)
        
        await self.db.flush()
