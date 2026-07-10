# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-07-10

### Fixed

- `agora_forget`: Now properly clears both L1 and L2 caches (previously only L1 was cleared, leading to potential stale results after deletion).
- `agora_crossref` (by `entry_id`): Now performs a direct ID-based retrieval from the ChromaDB collection instead of treating the opaque entry ID as a semantic query string. Cross references are now correctly derived from the actual stored document text.

### Changed / Improved

- **Startup performance**: Moved the heavy `VectorStore` (ChromaDB) import inside `create_server()` so that a bare `import agora.server` no longer triggers the expensive dependency load at module import time.
- Improved test coverage for cache invalidation and cross-reference behavior using the real shipped tool implementations.
- Added internal cache attachments (`_agora_l1_cache`, `_agora_l2_cache`) for reliable verification of L2 behavior in tests.
- `.gitignore` updated to ignore `mcps/` (tool schema captures, out of core scope).

### Verification

- All changes are covered by real tests that exercise the shipped code paths.
- Explicit verification of L2 cache invalidation (pre-forget L2 hit → forget → post-forget miss with no stale data).
- MCP handshake responsiveness test remains passing.

## [0.4.0] - Previous release

Initial public release (see git history for details).
