"""Foundation Portal storage service (BE-EP-036-SVC, ADR-029 gap P0-3).

Single place that knows where uploaded bytes land. Backend switch via
``settings.storage_backend`` (O4):

- ``local`` (default, dev/test): writes under ``local_upload_dir`` and returns
  a relative URL path ``/uploads/foundation/...`` (serving is out of scope).
- ``azure``: Azure Blob Storage via connection string (O5). Returns the
  canonical blob URL WITHOUT a SAS token (Gate-2 review HIGH-2, 2026-09-09):
  SAS generation belongs to the future serve endpoint (P1, with P0-7;
  user-delegation SAS via managed identity is the hardening there).

Object key is always ``foundation/<tenant_id>/<content_id>/<uuid4><ext>``;
the extension is derived from the DETECTED MIME type, never from the
client-supplied filename.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import unquote, urlparse
from uuid import uuid4

import aiofiles
import puremagic

from src.core.shared.config import Settings, get_settings

if TYPE_CHECKING:
    from azure.storage.blob import BlobClient

logger = logging.getLogger(__name__)


class FoundationStorageError(Exception):
    """Base error for foundation storage failures."""


class FoundationStorageNotConfiguredError(FoundationStorageError):
    """Storage backend is selected but not configured (endpoint maps to 503)."""


# MIME allowlist from ADR-029 (spec BE-EP-036, section "MIME-allowlist").
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
        # BE-EP-056: spraakopnames van iPhone en Android (.m4a) en opnames uit
        # Safari (MediaRecorder) zijn audio/mp4.
        "audio/mp4",
        "application/pdf",
        "text/plain",
        "video/mp4",
        "video/webm",
        # BE-EP-057: een iPhone neemt video op als .mov (QuickTime); dezelfde
        # blokindeling als MP4, dus de metadata wordt op dezelfde manier gewist.
        "video/quicktime",
    }
)

# Extension is derived from the detected MIME type, not from the filename.
_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}


#: Zelfde tekenset als `foundation_bagit._SAFE_SEGMENT`: een naam die de bag accepteert, moet
#: de opslag ook accepteren (Gate 2 L2).
_ARCHIEF_NAAM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


def mime_extension(mime_type: str | None) -> str | None:
    """De bestandsextensie die deze dienst bij een MIME-type gebruikt, of None (BE-EP-054)."""
    if mime_type is None:
        return None
    return _MIME_TO_EXT.get(mime_type)


def secure_filename(name: str | None) -> str:
    """Sanitize a filename to prevent path traversal and unsafe chars.

    Same pattern as documents/upload_router.py. The sanitized name is never
    used in the object key (uuid4-based); it is defense-in-depth for any
    future consumer of the original name.
    """
    if not name:
        return "unnamed"
    name = name.replace("\\", "_").replace("/", "_").replace("\x00", "")
    safe = ""
    for ch in name:
        if ch.isalnum() or ch in "._-":
            safe += ch
        else:
            safe += "_"
    return safe or "unnamed"


def detect_allowed_mime(
    data: bytes,
    *,
    filename: str | None,
    declared_content_type: str | None,
) -> str | None:
    """Detect MIME from magic bytes; return an allowlisted MIME or None.

    ``text/plain`` exception (spec O-rule): plain text has no reliable magic
    bytes, so it is accepted only when detection finds nothing AND the
    filename ends in ``.txt`` AND the declared Content-Type is ``text/plain``
    AND the content decodes as UTF-8. Anything detected that is not on the
    allowlist is rejected (e.g. an executable with a ``.png`` name).
    """
    if not data:
        # Empty upload: puremagic raises on empty input (PureError in 1.x,
        # PureValueError in 2.x). An empty file has no magic bytes and no
        # fallback -> rejected.
        return None
    try:
        matches = puremagic.magic_string(data)
    except (puremagic.PureError, ValueError):
        # Pinned 1.30 (CI runs Python 3.11; puremagic 2.x requires >=3.12)
        # raises PureError("Could not identify file") instead of returning
        # an empty list when nothing matches. Treat as: no magic detected.
        matches = []
    for match in matches:
        # puremagic ships no type stubs; mime_type is Any at runtime it is
        # always a str ("" when unknown, which is never on the allowlist).
        match_mime = cast(str, match.mime_type)
        if match_mime in ALLOWED_MIME_TYPES:
            return match_mime
    if matches:
        # Magic bytes detected a type that is not on the allowlist.
        return None
    # Normalize "text/plain; charset=utf-8" -> "text/plain" before comparing.
    declared = (declared_content_type or "").split(";")[0].strip().lower()
    if filename is not None and filename.lower().endswith(".txt") and declared == "text/plain":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return "text/plain"
    return None


class BestandOnleesbaarError(FoundationStorageError):
    """Het bestand kon niet worden gelezen of is te groot om te verwerken (endpoint: 400)."""


#: BE-EP-056: afbeeldingen waaruit de metadata wordt verwijderd. GIF valt erbuiten:
#: dat formaat heeft geen EXIF en opnieuw opslaan breekt animaties.
_METADATA_VERWIJDEREN: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})

#: BE-EP-056: MP4-bestanden (video en .m4a-opnames) waaruit de metadata wordt gewist.
_MP4_SOORTEN: frozenset[str] = frozenset({"video/mp4", "audio/mp4", "video/quicktime"})

#: Bovengrens in pixels; daarboven weigeren in plaats van uitpakken (decompression bomb).
_MAX_PIXELS = 50_000_000

#: MP4-blokken met persoonlijke metadata: locatie (bijv. het blok met de coordinaten),
#: maker, toestel en titel. Een iPhone-opname krijgt standaard de straatnaam als titel.
#: ``uuid``-blokken zijn fabrikantuitbreidingen; daarin staat o.a. XMP, dat ook een
#: GPS-positie kan bevatten (BE-EP-057).
_MP4_WISSEN: frozenset[bytes] = frozenset({b"udta", b"meta", b"uuid"})

#: MP4-blokken waarin die metadata kan zitten en waar we dus in moeten kijken.
_MP4_HOUDERS: frozenset[bytes] = frozenset({b"moov", b"trak"})


def _wis_mp4_metadata(data: bytearray, start: int, eind: int) -> None:
    """Wis de metadata-blokken in een MP4 zonder de bestandsindeling te veranderen.

    Elk metadata-blok krijgt het type ``free`` en wordt met nullen gevuld. De lengte
    van elk blok blijft gelijk, dus de verwijzingen naar de beeld- en geluidsdata
    (absolute posities in het bestand) blijven kloppen en de video speelt gewoon.
    """
    pos = start
    while pos + 8 <= eind:
        grootte = int.from_bytes(data[pos : pos + 4], "big")
        soort = bytes(data[pos + 4 : pos + 8])
        kop = 8
        if grootte == 1:
            if pos + 16 > eind:
                raise ValueError("MP4-blok met afgebroken lengte")
            grootte = int.from_bytes(data[pos + 8 : pos + 16], "big")
            kop = 16
        elif grootte == 0:
            grootte = eind - pos
        if grootte < kop or pos + grootte > eind:
            raise ValueError("MP4-blok met ongeldige lengte")
        if soort in _MP4_WISSEN:
            data[pos + 4 : pos + 8] = b"free"
            data[pos + kop : pos + grootte] = bytes(grootte - kop)
        elif soort in _MP4_HOUDERS:
            _wis_mp4_metadata(data, pos + kop, pos + grootte)
        pos += grootte


def verwijder_metadata(data: bytes, mime_type: str) -> bytes:
    """Haal locatie en andere persoonlijke metadata uit foto's, video's en opnames (BE-EP-056).

    Telefoons schrijven de plek waar een foto of video is gemaakt in het bestand,
    vaak het huisadres van de verteller. Die gegevens mogen niet in het archief komen.

    - Foto's (JPEG, PNG, WebP) worden opnieuw opgeslagen zonder EXIF en tekstblokken.
      De stand (EXIF Orientation) wordt eerst in de pixels verwerkt; het
      kleurprofiel (ICC) blijft, dat zegt niets over de persoon.
    - MP4-video en .m4a-opnames: de metadata-blokken worden gewist (zie
      ``_wis_mp4_metadata``); beeld en geluid blijven byte voor byte gelijk.

    Andere bestandstypen komen ongewijzigd terug.
    """
    if mime_type in _MP4_SOORTEN:
        buffer = bytearray(data)
        try:
            _wis_mp4_metadata(buffer, 0, len(buffer))
        except ValueError as exc:
            raise BestandOnleesbaarError("MP4-bestand kon niet worden gelezen") from exc
        return bytes(buffer)

    if mime_type not in _METADATA_VERWIJDEREN:
        return data

    import io

    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as bron:
            breedte, hoogte = bron.size
            if breedte * hoogte > _MAX_PIXELS:
                raise BestandOnleesbaarError("Afbeelding is te groot om te verwerken")
            gedraaid = ImageOps.exif_transpose(bron)
            beeld = gedraaid if gedraaid is not None else bron
            icc = bron.info.get("icc_profile")
            uit = io.BytesIO()
            opties: dict[str, object] = {}
            if icc:
                opties["icc_profile"] = icc
            if mime_type == "image/jpeg":
                if beeld.mode not in ("RGB", "L", "CMYK"):
                    beeld = beeld.convert("RGB")
                beeld.save(uit, format="JPEG", quality=90, optimize=True, **opties)
            elif mime_type == "image/png":
                beeld.save(uit, format="PNG", optimize=True, **opties)
            else:
                if beeld.mode not in ("RGB", "RGBA"):
                    beeld = beeld.convert("RGBA")
                beeld.save(uit, format="WEBP", quality=90, **opties)
            return uit.getvalue()
    except BestandOnleesbaarError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise BestandOnleesbaarError("Afbeelding kon niet worden gelezen") from exc


class FoundationStorageService:
    """Stores foundation content files on the configured backend (O4)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings if settings is not None else get_settings()

    @property
    def max_upload_size_bytes(self) -> int:
        """Upload cap (O2): same value as the global body-size middleware."""
        return self._settings.max_upload_size_bytes

    async def upload(
        self,
        *,
        tenant_id: int,
        content_id: int,
        filename: str | None,
        data: bytes,
        mime_type: str,
    ) -> str:
        """Store ``data`` and return its canonical URL.

        Local backend: relative path ``/uploads/foundation/...``. Azure
        backend: the bare blob URL WITHOUT a SAS token (Gate-2 review HIGH-2,
        2026-09-09): a SAS URL expires and would leave a dead reference in
        ``content.file_url``. SAS generation belongs to the future serve
        endpoint (P1, together with P0-7).
        """
        # Sanitized for defense-in-depth; the object key below never contains it.
        safe_name = secure_filename(filename)
        ext = _MIME_TO_EXT.get(mime_type)
        if ext is None:
            raise FoundationStorageError(f"No extension mapping for MIME type: {mime_type}")
        object_name = f"foundation/{tenant_id}/{content_id}/{uuid4().hex}{ext}"
        logger.debug(
            "foundation storage upload: tenant=%s content=%s name=%s key=%s",
            tenant_id,
            content_id,
            safe_name,
            object_name,
        )
        backend = self._settings.storage_backend
        if backend == "local":
            return await self._upload_local(object_name, data)
        if backend == "azure":
            return await self._upload_azure(object_name, data, mime_type)
        raise FoundationStorageNotConfiguredError(f"Unknown storage backend: {backend}")

    async def _upload_local(self, object_name: str, data: bytes) -> str:
        root = Path(self._settings.local_upload_dir)
        path = root.joinpath(*object_name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return f"/uploads/{object_name}"

    async def _upload_azure(self, object_name: str, data: bytes, mime_type: str) -> str:
        connection_string = self._settings.azure_storage_connection_string
        if not connection_string:
            raise FoundationStorageNotConfiguredError(
                "azure_storage_connection_string is not configured"
            )
        # Lazy import: the azure SDK is only needed when the backend is active.
        from azure.storage.blob import BlobServiceClient, ContentSettings

        service_client = BlobServiceClient.from_connection_string(connection_string)
        container = self._settings.foundation_blob_container
        blob_client = service_client.get_blob_client(container=container, blob=object_name)
        # The azure SDK is synchronous; keep the event loop free.
        await asyncio.to_thread(
            blob_client.upload_blob,
            data,
            overwrite=False,
            content_settings=ContentSettings(content_type=mime_type),
        )
        # Canonical blob URL, WITHOUT SAS token (HIGH-2, 2026-09-09). Read-SAS
        # generation moves to the future serve endpoint (P1, with P0-7); a
        # stored SAS URL would expire and leave a dead file_url in the DB.
        return blob_client.url

    async def upload_archive(self, *, tenant_id: int, bag_name: str, data: bytes) -> str:
        """Sla een BagIt-archiefpakket (zip) op en geef de canonieke URL terug (BE-EP-054).

        Eigen sleutelruimte `foundation-archief/<tenant>/` zodat een archiefpakket nooit
        botst met, of te vinden is via, de publieke uploadpaden van content. Een korte uuid in
        de objectnaam: twee exports in dezelfde seconde overschrijven elkaar nooit (Gate 2).
        """
        if not _ARCHIEF_NAAM.match(bag_name):
            raise FoundationStorageError(f"Ongeldige bag-naam: {bag_name!r}")
        object_name = f"foundation-archief/{tenant_id}/{bag_name}-{uuid4().hex[:8]}.zip"
        backend = self._settings.storage_backend
        try:
            if backend == "local":
                return await self._upload_local(object_name, data)
            if backend == "azure":
                return await self._upload_azure(object_name, data, "application/zip")
        except FoundationStorageError:
            raise
        except Exception as e:
            # Azure-SDK- en OS-fouten hebben geen gemeenschappelijke basisklasse met de
            # domeinfout; de aanroeper vangt alleen FoundationStorageError.
            raise FoundationStorageError(f"opslaan mislukt: {type(e).__name__}") from e
        raise FoundationStorageNotConfiguredError(f"Unknown storage backend: {backend}")

    async def delete_archive(self, file_url: str, *, tenant_id: int) -> None:
        """Verwijder een archiefpakket dat zonder vastlegging is achtergebleven (BE-EP-054)."""
        object_name = self._object_name(file_url, tenant_id=tenant_id)
        backend = self._settings.storage_backend
        try:
            if backend == "local":
                pad = Path(self._settings.local_upload_dir).resolve().joinpath(
                    *object_name.split("/")
                )
                pad.unlink(missing_ok=True)
                return
            if backend == "azure":
                blob_client = self._azure_blob_client(object_name)
                await asyncio.to_thread(blob_client.delete_blob)
                return
        except FoundationStorageError:
            raise
        except Exception as e:
            raise FoundationStorageError(f"verwijderen mislukt: {type(e).__name__}") from e
        raise FoundationStorageNotConfiguredError(f"Unknown storage backend: {backend}")

    async def read_bytes(self, file_url: str, *, tenant_id: int) -> bytes:
        """Lees een opgeslagen bestand van DEZE tenant terug (lokaal of Azure Blob).

        Het object moet onder `foundation/<tenant>/` of `foundation-archief/<tenant>/` liggen:
        een file_url die naar het object van een andere tenant wijst, wordt geweigerd, ook al
        staat het in dezelfde container (Gate 2, BE-EP-054).
        """
        object_name = self._object_name(file_url, tenant_id=tenant_id)
        backend = self._settings.storage_backend
        try:
            if backend == "local":
                pad = Path(self._settings.local_upload_dir).resolve().joinpath(
                    *object_name.split("/")
                )
                if not pad.is_file():
                    raise FoundationStorageError(f"Bestand niet gevonden: {object_name}")
                async with aiofiles.open(pad, "rb") as f:
                    return await f.read()
            if backend == "azure":
                blob_client = self._azure_blob_client(object_name)
                downloader = await asyncio.to_thread(blob_client.download_blob)
                return await asyncio.to_thread(downloader.readall)
        except FoundationStorageError:
            raise
        except Exception as e:
            raise FoundationStorageError(f"lezen mislukt: {type(e).__name__}") from e
        raise FoundationStorageNotConfiguredError(f"Unknown storage backend: {backend}")

    def _object_name(self, file_url: str, *, tenant_id: int) -> str:
        """Objectnaam uit een canonieke URL, alleen als hij bij deze tenant hoort."""
        backend = self._settings.storage_backend
        if backend == "azure":
            container = self._settings.foundation_blob_container
            pad = unquote(urlparse(file_url).path)
            if not pad.startswith(f"/{container}/"):
                raise FoundationStorageError("URL hoort niet bij de geconfigureerde container")
            object_name = pad[len(container) + 2 :]
        else:
            if file_url.startswith(("http://", "https://")):
                raise FoundationStorageError("lokale opslag verwacht een relatief pad")
            object_name = unquote(file_url).lstrip("/")
            if object_name.startswith("uploads/"):
                object_name = object_name[len("uploads/") :]
        delen = object_name.split("/")
        if any(deel in ("", ".", "..") or "\\" in deel for deel in delen):
            raise FoundationStorageError("ongeldig pad")
        if len(delen) < 3 or delen[0] not in ("foundation", "foundation-archief"):
            raise FoundationStorageError("pad buiten de foundation-opslag")
        if delen[1] != str(tenant_id):
            raise FoundationStorageError("bestand hoort niet bij deze tenant")
        return object_name

    def _azure_blob_client(self, object_name: str) -> BlobClient:
        connection_string = self._settings.azure_storage_connection_string
        if not connection_string:
            raise FoundationStorageNotConfiguredError(
                "azure_storage_connection_string is not configured"
            )
        from azure.storage.blob import BlobServiceClient

        service_client = BlobServiceClient.from_connection_string(connection_string)
        return service_client.get_blob_client(
            container=self._settings.foundation_blob_container, blob=object_name
        )

    def get_local_file_path(self, file_url: str) -> Path | None:
        """Resolve and validate a local file_url against local_upload_dir.

        Returns the verified absolute Path, or None if outside root or invalid.
        Strictly prevents path traversal attacks (O8).
        """
        if file_url.startswith("http://") or file_url.startswith("https://"):
            return None

        # Strip leading /uploads/ or /
        rel_path = file_url.lstrip("/")
        if rel_path.startswith("uploads/"):
            rel_path = rel_path[len("uploads/") :]

        root = Path(self._settings.local_upload_dir).resolve()
        candidate = root.joinpath(*rel_path.split("/")).resolve()

        try:
            if not candidate.is_relative_to(root):
                logger.warning(
                    "Path traversal attempt detected in get_local_file_path: %s", file_url
                )
                return None
        except AttributeError:
            if not str(candidate).startswith(str(root)):
                return None

        return candidate

    async def generate_read_url(
        self,
        file_url: str,
        *,
        expiry_minutes: int = 30,
        download: bool = False,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> str:
        """Generate a secure, time-limited read URL for the given file_url (ADR-029 P1-4).

        For local storage, returns the URL directly.
        For Azure Blob storage, generates a User-Delegation or Account SAS token
        with read permissions, response headers, and short expiry (default: 30 minutes).
        """
        backend = self._settings.storage_backend
        if backend == "local" or not file_url.startswith("http"):
            return file_url

        if backend == "azure":
            return await self._generate_azure_sas_url(
                file_url,
                expiry_minutes=expiry_minutes,
                download=download,
                filename=filename,
                mime_type=mime_type,
            )

        return file_url

    async def _generate_azure_sas_url(
        self,
        file_url: str,
        *,
        expiry_minutes: int = 30,
        download: bool = False,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> str:
        connection_string = self._settings.azure_storage_connection_string
        account_url = self._settings.azure_storage_account_url
        if not connection_string and not account_url:
            raise FoundationStorageNotConfiguredError(
                "Azure storage backend is selected but neither azure_storage_connection_string "
                "nor azure_storage_account_url is configured."
            )

        from urllib.parse import urlparse

        parsed = urlparse(file_url)
        path = parsed.path.lstrip("/")
        if "/" not in path:
            return file_url

        container, blob_name = path.split("/", 1)

        def _sync_generate_sas() -> str:
            from datetime import datetime, timedelta, timezone
            from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas

            service_client: BlobServiceClient | None = None
            if account_url:
                try:
                    from azure.identity import DefaultAzureCredential

                    service_client = BlobServiceClient(
                        account_url, credential=DefaultAzureCredential()
                    )
                except Exception:
                    service_client = None

            if service_client is None and connection_string:
                service_client = BlobServiceClient.from_connection_string(connection_string)

            if service_client is None:
                raise FoundationStorageNotConfiguredError(
                    "Failed to initialize BlobServiceClient for Azure SAS generation."
                )

            now = datetime.now(timezone.utc)
            start_time = now - timedelta(minutes=5)
            expiry_time = now + timedelta(minutes=expiry_minutes)

            # Try user delegation key first if credential supports Entra ID OAuth
            user_delegation_key = None
            try:
                if hasattr(service_client, "get_user_delegation_key"):
                    user_delegation_key = service_client.get_user_delegation_key(
                        start_time, expiry_time
                    )
            except Exception:
                user_delegation_key = None

            account_name = service_client.account_name
            if not account_name:
                raise FoundationStorageNotConfiguredError(
                    "Azure storage account_name could not be determined for SAS generation."
                )

            account_key = getattr(service_client.credential, "account_key", None)

            extra_sas_kwargs: dict[str, str] = {}
            if filename:
                safe_name = secure_filename(filename)
                disposition_type = "attachment" if download else "inline"
                extra_sas_kwargs["content_disposition"] = (
                    f'{disposition_type}; filename="{safe_name}"'
                )
            elif download:
                extra_sas_kwargs["content_disposition"] = "attachment"

            if mime_type:
                extra_sas_kwargs["content_type"] = mime_type

            if user_delegation_key:
                sas_token = generate_blob_sas(
                    account_name=account_name,
                    container_name=container,
                    blob_name=blob_name,
                    user_delegation_key=user_delegation_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=expiry_time,
                    start=start_time,
                    **extra_sas_kwargs,
                )
            elif account_key:
                sas_token = generate_blob_sas(
                    account_name=account_name,
                    container_name=container,
                    blob_name=blob_name,
                    account_key=account_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=expiry_time,
                    start=start_time,
                    **extra_sas_kwargs,
                )
            else:
                raise FoundationStorageNotConfiguredError(
                    "Neither user delegation key nor account key is available to generate SAS token."
                )

            return f"{parsed.scheme}://{parsed.netloc}/{container}/{blob_name}?{sas_token}"

        return await asyncio.to_thread(_sync_generate_sas)
