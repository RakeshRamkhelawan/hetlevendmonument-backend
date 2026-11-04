"""
Tenant-specific Vector Store Manager

Manages ChromaDB collections per tenant for multi-tenant isolation.
"""

import logging
from typing import Any, Optional, cast

import chromadb
from chromadb.api.types import Embeddings, Metadata, QueryResult
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class TenantVectorManager:
    """
    Manages tenant-specific vector namespaces in ChromaDB

    Each tenant gets an isolated collection with:
    - Unique namespace prefix
    - Separate embeddings storage
    - No cross-tenant data leakage allowed

    Usage:
        manager = TenantVectorManager()
        collection = manager.get_collection(tenant_id=1)
        collection.add(documents=["..."], embeddings=[[...]]])
    """

    COLLECTION_PREFIX = "tenant_"

    def __init__(
        self,
        persist_directory: str = "./data/chromadb",
        embedding_function: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Initialize the tenant vector manager

        Args:
            persist_directory: Directory for persistent storage
            embedding_function: Optional custom embedding function
        """
        self.persist_directory = persist_directory
        self.embedding_function = embedding_function

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )

        # Cache for tenant collections
        self._collections: dict[int, chromadb.Collection] = {}

        logger.info(f"TenantVectorManager initialized: {persist_directory}")

    def get_collection_name(self, tenant_id: int) -> str:
        """Generate unique collection name for tenant"""
        return f"{self.COLLECTION_PREFIX}{tenant_id}"

    def get_collection(self, tenant_id: int, create_if_missing: bool = True) -> chromadb.Collection:
        """
        Get or create collection for a tenant

        Args:
            tenant_id: Tenant ID
            create_if_missing: Create collection if it doesn't exist

        Returns:
            ChromaDB Collection for the tenant
        """
        if tenant_id in self._collections:
            return self._collections[tenant_id]

        collection_name = self.get_collection_name(tenant_id)

        try:
            if create_if_missing:
                collection = self.client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=self.embedding_function,
                    metadata={"tenant_id": tenant_id},
                )
            else:
                collection = self.client.get_collection(
                    name=collection_name, embedding_function=self.embedding_function
                )

            self._collections[tenant_id] = collection
            logger.info(f"Collection ready: {collection_name}")
            return collection

        except Exception as e:
            logger.error(f"Failed to get collection for tenant {tenant_id}: {e}")
            raise

    def add_documents(
        self,
        tenant_id: int,
        documents: list[str],
        embeddings: Embeddings,
        ids: list[str],
        metadatas: list[Metadata] | None = None,
    ) -> None:
        """
        Add documents to tenant's collection

        Args:
            tenant_id: Tenant ID
            documents: Document texts
            embeddings: Document embeddings
            ids: Document IDs
            metadatas: Optional metadata for each document
        """
        collection = self.get_collection(tenant_id)

        # Prepare metadatas with proper type
        prepared_metadatas: list[Metadata] | None = metadatas if metadatas else None
        if prepared_metadatas is None:
            prepared_metadatas = [{} for _ in documents]

        collection.add(
            documents=documents,
            embeddings=embeddings,
            ids=ids,
            metadatas=prepared_metadatas,
        )

        logger.info(f"Added {len(documents)} docs to tenant {tenant_id}")

    def search(
        self,
        tenant_id: int,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> QueryResult:
        """
        Search within tenant's collection only

        Args:
            tenant_id: Tenant ID (REQUIRED for isolation)
            query_embedding: Query vector
            top_k: Number of results
            where: Optional filter conditions

        Returns:
            Search results from tenant's collection only
        """
        collection = self.get_collection(tenant_id, create_if_missing=False)

        results = collection.query(
            query_embeddings=cast(Embeddings, [query_embedding]),
            n_results=top_k,
            where=where,
        )

        return results

    def delete_collection(self, tenant_id: int) -> bool:
        """Delete a tenant's entire collection"""
        collection_name = self.get_collection_name(tenant_id)

        try:
            self.client.delete_collection(collection_name)
            self._collections.pop(tenant_id, None)
            logger.info(f"Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False

    def list_tenants(self) -> list[int]:
        """List all tenant IDs with collections"""
        collections = self.client.list_collections()
        tenant_ids: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for col in collections:
            # col can be a collection object or a name string depending on chroma version
            name = col.name if hasattr(col, "name") else str(col)
            if name.startswith(self.COLLECTION_PREFIX):
                try:
                    tid = int(name.replace(self.COLLECTION_PREFIX, ""))
                    tenant_ids.append(tid)
                except ValueError:
                    pass

        return tenant_ids

    def get_tenant_stats(
        self, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get statistics for a tenant's collection"""
        collection = self.get_collection(tenant_id, create_if_missing=False)
        return {
            "tenant_id": tenant_id,
            "document_count": collection.count(),
            "collection_name": collection.name,
        }


#: Het gedeelde exemplaar, LUI opgebouwd (ADR-036 OP-220, 2026-09-09).
#:
#: Hier stond `tenant_vector_manager = TenantVectorManager()` op moduleniveau. Die constructor
#: bouwt een `chromadb.PersistentClient` op `./data/chromadb`, dus het IMPORTEREN van deze
#: module deed schijf-I/O en liet ChromaDB zijn sqlite-migraties uitvoeren.
#:
#: **Wat er gebeurde.** De blokkerende CI-poort viel twee keer om tijdens de COLLECTIE, op
#: `import src.core.knowledge.tenant_vector_manager` vanuit
#: `tests/unit/test_context_retriever.py`, met
#: `InternalError: error returned from database: (code: 1) table collections already exists`
#: (runs 34351173308 en 34351321996). De eerste van die twee zat op een commit die ALLEEN
#: documentatie wijzigde, dus het is geen gevolg van code, en een uur eerder was dezelfde stap
#: op dezelfde codeweg groen.
#:
#: **Wat NIET is aangetoond, expliciet.** Het mechanisme. Drie hypotheses zijn nagemeten en
#: alle drie afgevallen: een versiesprong van chromadb (in beide runs vastgezet op 1.5.9,
#: identiek), een botsing tussen gelijktijdige imports (8 gelijktijdig, 3 pogingen, op een
#: afwezige map: nul falen), en een tweede import over een bestaande map (slaagt). Een eerdere
#: "reproductie bij zes gelijktijdige imports" bleek een VALS positief van de meetopzet zelf:
#: die verwijderde de map met `shutil.rmtree`, en dat loopt op Windows achter, waardoor een
#: nieuwe client een half verwijderde sqlite zag.
#:
#: **Waarom deze wijziging dan toch.** Niet omdat ze het mechanisme repareert -- dat is
#: onbekend -- maar omdat ze het hele faaloppervlak weghaalt: de fout treedt op tijdens een
#: IMPORT, en na deze wijziging doet die import geen schijf-I/O meer. Een module importeren
#: mag hoe dan ook geen database aanmaken. Het gedeelde exemplaar blijft bestaan en het gedrag
#: voor aanroepers is identiek; het wordt alleen pas gebouwd bij het EERSTE gebruik. De echte
#: bevestiging kan alleen een groene CI-run zijn.
_gedeeld_exemplaar: TenantVectorManager | None = None


def get_tenant_vector_manager() -> TenantVectorManager:
    """Geef het gedeelde exemplaar, en bouw het bij de eerste aanroep."""
    global _gedeeld_exemplaar
    if _gedeeld_exemplaar is None:
        _gedeeld_exemplaar = TenantVectorManager()
    return _gedeeld_exemplaar
