# Allowed Dependencies

- `micyte/core/`
- `micyte/ports/`

Nothing else. A routine runner that could reach an adapter would be able to write
without going through the write-policy port, which is the one thing this module exists
to make impossible.
