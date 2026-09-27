"""Tool-package port: what an installable tool package is, and what installing one may do.

The marketplace is a PORT, like PayPal — `micyte.com` is the authoritative source and a
side-loaded package runs without being listed. Installing writes a PRESENTATION control and
grants nothing; see `contracts` for why that separation is the whole design.
"""

from .contracts import (
    FEATURE_SCOPES,
    FITS,
    INCOMPATIBLE,
    SOURCE_LOCAL,
    SOURCE_OFFICIAL,
    SOURCES,
    UNMET,
    AppSandbox,
    ArchetypeMismatch,
    DocumentRequirement,
    PortDeclaration,
    PortFill,
    PortFunction,
    ScopedFeature,
    SourceRequirement,
    ToolPackage,
    ToolPackageError,
    ToolPackageSource,
    ToolRequirement,
    compatibility,
    eligible_fills,
    extensions,
    installable_tools,
    unmet_requirements,
)

__all__ = [
    "FEATURE_SCOPES",
    "FITS",
    "INCOMPATIBLE",
    "UNMET",
    "SOURCES",
    "SOURCE_LOCAL",
    "SOURCE_OFFICIAL",
    "AppSandbox",
    "ArchetypeMismatch",
    "DocumentRequirement",
    "PortDeclaration",
    "PortFill",
    "PortFunction",
    "ScopedFeature",
    "SourceRequirement",
    "ToolPackage",
    "ToolPackageError",
    "ToolPackageSource",
    "ToolRequirement",
    "compatibility",
    "eligible_fills",
    "extensions",
    "installable_tools",
    "unmet_requirements",
]
