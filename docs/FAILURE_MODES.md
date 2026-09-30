# Archive integrity and remaining failure limits

**Retained ZIP changed after archiving — detected as of 2026-09-30.** Before extraction, the archive now recomputes `original.zip`'s SHA-256 and raises an error if it differs from the selected hash. This prevents tracing replacement ZIP bytes under the old hash and receipt. The regression `test_mismatched_retained_zip_cannot_be_traced_under_old_hash` passes. The full Conda suite ran 112 tests and passed on 2026-09-30 after updating the separate path-escape fixture to contain the unsafe member before archiving. Automatic repair or re-download of a mismatched ZIP remains undefined.

The extracted `feed/` directory still preserves and trusts existing files. The new check validates the retained ZIP, not the bytes of previously extracted files. A separate decision and verification would be needed to establish extraction-cache integrity under accidental modification or damage. This limitation does not imply an observed MBTA archive failure.
