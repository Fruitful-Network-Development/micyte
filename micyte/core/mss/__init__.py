"""MSS — the datum document standard, and the ``.mss`` artifacts built on it.

The package has three layers, and keeping them straight is what stops the format
from re-fragmenting:

``magnitude`` / ``document_codec`` / ``canonicalization``
    The **codec**. How a datum closure becomes a bitstream and a hash.
``document_adapter`` / ``datum_identity``
    The **projection**. How the repo's raw-row model becomes that closure.
``envelope`` / ``still`` / ``hyphae``
    The **artifact**. One container (``.mss``) with two declared payload kinds —
    a document set, or one datum's focus closure — carrying whatever leaves the
    instance, to a website, to a peer, or over a channel.
"""

from .canonicalization import (
    canonicalize_iteration_addresses,
    canonicalize_value_group_ordering,
)
from .datum_identity import compute_mss_hash, derive_hyphae_chain
from .document_adapter import (
    CatalogEntry,
    DocumentScopedIndex,
    MssAdapterReport,
    binary_hyphae_value,
    build_catalog_index,
    datum_closure_to_mss,
    document_closure_to_mss,
    document_scoped_index,
)
from .document_codec import (
    MSS_DOC_POLICY,
    EncodedMss,
    MssDatum,
    MssFormatError,
    MssTuple,
    decode_document,
    encode_document,
    mss_document_hash,
    reindex_into_isolated_anthology,
)
from .envelope import (
    KIND_DOCUMENT_SET,
    KIND_HYPHAE,
    KIND_NAMES,
    KIND_PROJECTION,
    MSS_FORMAT_VERSION,
    MSS_MAGIC,
    MSS_MAX_DECOMPRESSED_BYTES,
    MssEnvelopeError,
    decode_envelope,
    encode_envelope,
    peek_kind,
)
from .hyphae import (
    HYPHAE_SCHEMA,
    Hyphae,
    build_hyphae,
    decode_hyphae,
    encode_hyphae,
    hyphae_to_datums,
    hyphae_tokens,
    verify_hyphae,
    verify_hyphae_round_trip,
)
from .magnitude import (
    MAG_BOOL,
    MAG_INT,
    MAG_TEXT,
    MagnitudeError,
    decode_magnitude,
    encode_magnitude,
)
from .still import (
    STILL_POLICY,
    STILL_SCHEMA,
    Still,
    StillDocument,
    StillFormatError,
    build_still,
    decode_still,
    encode_still,
    still_to_documents,
    verify_still,
    verify_still_round_trip,
)

__all__ = [
    "HYPHAE_SCHEMA",
    "KIND_DOCUMENT_SET",
    "KIND_HYPHAE",
    "KIND_NAMES",
    "KIND_PROJECTION",
    "MAG_BOOL",
    "MAG_INT",
    "MAG_TEXT",
    "MSS_DOC_POLICY",
    "MSS_FORMAT_VERSION",
    "MSS_MAGIC",
    "MSS_MAX_DECOMPRESSED_BYTES",
    "STILL_POLICY",
    "STILL_SCHEMA",
    "CatalogEntry",
    "DocumentScopedIndex",
    "EncodedMss",
    "Hyphae",
    "MagnitudeError",
    "MssAdapterReport",
    "MssDatum",
    "MssEnvelopeError",
    "MssFormatError",
    "MssTuple",
    "Still",
    "StillDocument",
    "StillFormatError",
    "binary_hyphae_value",
    "build_catalog_index",
    "build_hyphae",
    "build_still",
    "canonicalize_iteration_addresses",
    "canonicalize_value_group_ordering",
    "compute_mss_hash",
    "datum_closure_to_mss",
    "decode_document",
    "decode_envelope",
    "decode_hyphae",
    "decode_magnitude",
    "decode_still",
    "derive_hyphae_chain",
    "document_closure_to_mss",
    "document_scoped_index",
    "encode_document",
    "encode_envelope",
    "encode_hyphae",
    "encode_magnitude",
    "encode_still",
    "hyphae_to_datums",
    "hyphae_tokens",
    "mss_document_hash",
    "peek_kind",
    "reindex_into_isolated_anthology",
    "still_to_documents",
    "verify_hyphae",
    "verify_hyphae_round_trip",
    "verify_still",
    "verify_still_round_trip",
]
