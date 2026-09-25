# Analyse repository snapshots pinned to a commit SHA

A run resolves the target branch to a commit SHA and downloads that tarball, instead of cloning. All derived data (chunks, embeddings, injection scores, symbol graph) is cached under `owner/repo@sha`. Re-asking about the same snapshot costs nothing, citations stay valid forever, and eval datasets can pin exact SHAs. Scope is capped at Python and TypeScript sources, about 2k files, excluding vendored and generated code. History is capped at 12 months or 2k commits, whichever is smaller, to stay inside GitHub's API rate limit.
