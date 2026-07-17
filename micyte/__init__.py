"""MiCyte — a datum operating environment.

The MOS (Mycelial Ontological Schema) and everything that reads or writes it:
the datum core, its ports, the SQL and filesystem stores, the portal state
machine, and the tools that render a sandbox.

This package must import nothing of FND's grantee services. That is the property
that lets it ship on its own, and it is enforced, not hoped for — see
MyCiteV2/tests/architecture/test_micyte_fnd_boundary.py.
"""

__version__ = "0.1.0"
