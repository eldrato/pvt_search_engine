import os
import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.core.config import settings
from app.core.logging import logger

COLLECTION_NAME = "aegis_chunks"
DEFAULT_DIMENSION = 384
QDRANT_STORAGE_DIR = os.path.join(os.getcwd(), "aegis_qdrant_storage")


def _to_uuid(id_str: str) -> str:
    """Converts any arbitrary string into a valid deterministic UUID string for Qdrant point IDs."""
    try:
        # Check if already a valid UUID
        return str(uuid.UUID(id_str))
    except (ValueError, AttributeError):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(id_str)))


class QdrantService:
    """
    Qdrant Dense Vector Store Service.
    Indexes chunk embeddings and executes approximate nearest neighbor (ANN) cosine retrieval.
    Includes automatic local disk-persisted fallback if the Qdrant container is unreachable.
    """

    def __init__(self, url: Optional[str] = None, storage_path: Optional[str] = None):
        self.url = url or settings.QDRANT_URL
        self.storage_path = storage_path or QDRANT_STORAGE_DIR
        self.collection_name = COLLECTION_NAME
        self.dimension = DEFAULT_DIMENSION
        self.client: Optional[QdrantClient] = None
        self._is_local = False
        self._connect()

    def _connect(self):
        # 1. Attempt connection to Qdrant server container
        try:
            client = QdrantClient(url=self.url, timeout=1.5)
            # Probe collections to verify connectivity
            client.get_collections()
            self.client = client
            self._is_local = False
            logger.info(f"Connected to Qdrant vector engine at {self.url}")
            self.init_collection()
            return
        except Exception as e:
            logger.warning(
                f"Qdrant server at {self.url} unreachable ({e}). Initializing persistent local embedded Qdrant."
            )

        # 2. Local disk-persisted embedded Qdrant fallback
        try:
            os.makedirs(self.storage_path, exist_ok=True)
            self.client = QdrantClient(path=self.storage_path)
            self._is_local = True
            logger.info(f"Initialized persistent local embedded Qdrant at: {self.storage_path}")
            self.init_collection()
        except Exception as local_err:
            logger.warning(
                f"Could not initialize disk storage ({local_err}). Using in-memory Qdrant fallback."
            )
            self.client = QdrantClient(location=":memory:")
            self._is_local = True
            self.init_collection()

    def init_collection(self) -> bool:
        """Ensures the vector collection exists with cosine distance and target dimensions."""
        if not self.client:
            return False

        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.dimension,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection '{self.collection_name}' (dim={self.dimension})")
            return True
        except Exception as e:
            logger.error(f"Error initializing Qdrant collection: {e}")
            return False

    def upsert_chunks(
        self,
        payloads: List[Dict[str, Any]],
        vectors: List[List[float]]
    ) -> int:
        """
        Upserts chunk vectors and accompanying metadata into Qdrant.
        """
        if not self.client or not payloads or not vectors:
            return 0

        if len(payloads) != len(vectors):
            raise ValueError(f"Payload count ({len(payloads)}) != Vector count ({len(vectors)})")

        points = []
        for payload, vector in zip(payloads, vectors):
            chunk_id = payload.get("chunk_id") or str(uuid.uuid4())
            point_id = _to_uuid(chunk_id)

            # Store the original chunk_id in payload for consistent SSOT mapping
            point_payload = {**payload, "raw_chunk_id": chunk_id}

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=point_payload
                )
            )

        try:
            # Batch upsert in chunks of 100
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch,
                    wait=True
                )
            return len(points)
        except Exception as e:
            logger.error(f"Error upserting vectors into Qdrant: {e}")
            return 0

    def search_vectors(
        self,
        query_vector: List[float],
        source_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Executes an approximate nearest neighbor (ANN) cosine similarity search.
        """
        if not self.client:
            return []

        query_filter = None
        if source_type:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="source_type",
                        match=MatchValue(value=source_type)
                    )
                ]
            )

        try:
            # Modern QdrantClient 1.19+ uses query_points
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True
            )

            hits = []
            for pt in response.points:
                payload = pt.payload or {}
                chunk_id = payload.get("raw_chunk_id") or payload.get("chunk_id") or str(pt.id)
                hits.append({
                    "chunk_id": chunk_id,
                    "document_id": payload.get("document_id", ""),
                    "title": payload.get("title", "Untitled Document"),
                    "snippet": payload.get("content", "")[:240] + ("..." if len(payload.get("content", "")) > 240 else ""),
                    "content": payload.get("content", ""),
                    "score": round(float(pt.score), 4),
                    "semantic_score": round(float(pt.score), 4),
                    "source_type": payload.get("source_type", "upload"),
                    "mime_type": payload.get("mime_type", "text/plain"),
                    "anchor_label": payload.get("anchor_label", "Chunk"),
                    "chunk_index": payload.get("chunk_index", 0),
                    "location_meta": payload.get("location_meta", {}),
                    "created_at": payload.get("created_at")
                })
            return hits
        except Exception as e:
            logger.error(f"Error querying Qdrant vectors: {e}")
            return []

    def delete_by_document_id(self, document_id: str) -> bool:
        """Deletes all vector points associated with a specific document ID."""
        if not self.client:
            return False

        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors for document {document_id}: {e}")
            return False

    def count_vectors(self) -> int:
        """Returns the total number of vector points indexed."""
        if not self.client:
            return 0
        try:
            info = self.client.get_collection(self.collection_name)
            return info.points_count or 0
        except Exception:
            return 0

    def is_connected(self) -> bool:
        return self.client is not None

    def is_local_fallback(self) -> bool:
        return self._is_local


qdrant_service = QdrantService()
