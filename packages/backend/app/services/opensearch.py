import re
import time
from typing import List, Dict, Any, Optional
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import ConnectionError, TransportError

from app.core.config import settings
from app.core.logging import logger

INDEX_NAME = "aegis_chunks"

INDEX_MAPPING = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "similarity": {
                "default": {
                    "type": "BM25",
                    "b": 0.75,
                    "k1": 1.2
                }
            }
        },
        "analysis": {
            "analyzer": {
                "aegis_text_analyzer": {
                    "type": "standard",
                    "stopwords": "_english_"
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "aegis_text_analyzer",
                "fields": {
                    "keyword": {"type": "keyword", "ignore_above": 256}
                }
            },
            "content": {
                "type": "text",
                "analyzer": "aegis_text_analyzer"
            },
            "source_type": {"type": "keyword"},
            "mime_type": {"type": "keyword"},
            "anchor_label": {"type": "text"},
            "chunk_index": {"type": "integer"},
            "token_count": {"type": "integer"},
            "location_meta": {"type": "object", "enabled": False},
            "created_at": {"type": "date"}
        }
    }
}


class OpenSearchService:
    def __init__(self):
        self.client: Optional[OpenSearch] = None
        self._connected = False
        self._last_probe_time = 0.0
        self._init_client()

    def _init_client(self):
        self._last_probe_time = time.time()
        try:
            self.client = OpenSearch(
                hosts=[settings.OPENSEARCH_URL],
                http_compress=True,
                use_ssl=False,
                verify_certs=False,
                connection_class=RequestsHttpConnection,
                timeout=1.0,
                max_retries=0
            )
            # Quick probe
            if self.client.ping():
                self._connected = True
                self._ensure_index()
                logger.info(f"Connected to OpenSearch at {settings.OPENSEARCH_URL}")
            else:
                self._connected = False
        except Exception as e:
            self._connected = False
            logger.debug(f"OpenSearch not reachable ({e}). Fallback search will be used.")

    def is_connected(self) -> bool:
        if not self._connected:
            now = time.time()
            # Only retry connection probe every 30 seconds
            if now - self._last_probe_time > 30.0:
                self._last_probe_time = now
                try:
                    if self.client and self.client.ping():
                        self._connected = True
                        self._ensure_index()
                except Exception:
                    self._connected = False
        return self._connected

    def _ensure_index(self):
        if not self._connected or not self.client:
            return
        try:
            if not self.client.indices.exists(index=INDEX_NAME):
                self.client.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
                logger.info(f"Created OpenSearch index '{INDEX_NAME}' with BM25 similarity")
        except Exception as e:
            logger.warning(f"Could not verify/create OpenSearch index: {e}")

    def index_chunk(self, doc_payload: Dict[str, Any]) -> bool:
        if not self.is_connected():
            return False
        try:
            chunk_id = doc_payload.get("chunk_id")
            self.client.index(
                index=INDEX_NAME,
                id=chunk_id,
                body=doc_payload,
                refresh=True
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to index chunk {doc_payload.get('chunk_id')} in OpenSearch: {e}")
            return False

    def bulk_index_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        if not self.is_connected() or not chunks:
            return 0
        from opensearchpy.helpers import bulk
        actions = [
            {
                "_index": INDEX_NAME,
                "_id": c["chunk_id"],
                "_source": c
            }
            for c in chunks
        ]
        try:
            success, _ = bulk(self.client, actions, refresh=True)
            return success
        except Exception as e:
            logger.warning(f"OpenSearch bulk indexing error: {e}")
            return 0

    def delete_document_chunks(self, document_id: str) -> bool:
        if not self.is_connected():
            return False
        try:
            query = {
                "query": {
                    "term": {
                        "document_id": document_id
                    }
                }
            }
            self.client.delete_by_query(index=INDEX_NAME, body=query, refresh=True)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete chunks for doc {document_id} from OpenSearch: {e}")
            return False

    def search(
        self,
        query_text: str,
        source_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Executes BM25 search against OpenSearch index with query highlighting.
        Returns None if OpenSearch is not connected.
        """
        if not self.is_connected():
            return None

        must_clauses: List[Dict[str, Any]] = [
            {
                "multi_match": {
                    "query": query_text,
                    "fields": ["title^3", "content", "anchor_label"],
                    "fuzziness": "AUTO",
                    "operator": "or"
                }
            }
        ]

        filters: List[Dict[str, Any]] = []
        if source_type:
            filters.append({"term": {"source_type": source_type}})

        body = {
            "from": offset,
            "size": limit,
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filters
                }
            },
            "highlight": {
                "pre_tags": ["<mark class='bg-amber-400/20 text-amber-200 px-1 rounded'>"],
                "post_tags": ["</mark>"],
                "fields": {
                    "content": {"fragment_size": 180, "number_of_fragments": 2},
                    "title": {"number_of_fragments": 0}
                }
            }
        }

        try:
            start_time = time.perf_counter()
            resp = self.client.search(index=INDEX_NAME, body=body)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            hits = resp.get("hits", {})
            total_hits = hits.get("total", {}).get("value", 0)
            raw_hits = hits.get("hits", [])

            results = []
            for hit in raw_hits:
                src = hit.get("_source", {})
                score = hit.get("_score", 0.0)
                highlight = hit.get("highlight", {})

                # Extract highlighted snippet or fallback to first 200 chars
                snippet = ""
                if "content" in highlight:
                    snippet = " ... ".join(highlight["content"])
                elif "title" in highlight:
                    snippet = highlight["title"][0]
                else:
                    raw_c = src.get("content", "")
                    snippet = raw_c[:200] + ("..." if len(raw_c) > 200 else "")

                results.append({
                    "chunk_id": src.get("chunk_id"),
                    "document_id": src.get("document_id"),
                    "title": src.get("title"),
                    "snippet": snippet,
                    "content": src.get("content"),
                    "score": round(score, 4),
                    "source_type": src.get("source_type"),
                    "mime_type": src.get("mime_type"),
                    "anchor_label": src.get("anchor_label"),
                    "chunk_index": src.get("chunk_index"),
                    "location_meta": src.get("location_meta", {}),
                    "created_at": src.get("created_at")
                })

            return {
                "engine": "opensearch_bm25",
                "total": total_hits,
                "latency_ms": duration_ms,
                "results": results
            }
        except Exception as e:
            logger.error(f"OpenSearch query failed: {e}")
            return None


opensearch_service = OpenSearchService()
