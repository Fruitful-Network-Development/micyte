"""Agriculture-package datum helpers: anchors, chronology, farm document shape.

Was MyCiteV2/scripts/agro_erp_doc_lib.py. It is a library, not a script — its
only CLI-ness was its address. It sat in scripts/ while micyte/tools imported it,
which meant MiCyte could not be installed without FND's script tree: the wheel
built fine and then died on `import micyte.tools`.
"""
