"""Per-block churn via `git log -L start,end:file`.

`git log -L` walks the line range backwards through history, following the
range as the file's diffs shift it around. We parse the diff output and count
+/- content lines (skipping `+++`/`---` file-headers and `@@` hunk-headers).
Each call is one git invocation; results are cached by file blob SHA.
"""
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from hotspottriage.cache import Cache, cache_path_for


def file_blob_shas(repo: Path) -> dict[str, str]:
    """Return blob SHA at HEAD for every tracked file (one ls-tree call)."""
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split(" ")
        if len(parts) >= 3:
            out[path] = parts[2]
    return out


def _parse_added_deleted(diff_output: str) -> int:
    total = 0
    for line in diff_output.splitlines():
        if not line:
            continue
        if line.startswith(("+++ ", "--- ")):
            continue
        c = line[0]
        if c == "+" or c == "-":
            total += 1
    return total


def compute_one(
    repo: Path,
    file_path: str,
    start: int,
    end: int,
    since: str | None,
    until: str | None,
) -> int:
    cmd = [
        "git", "-C", str(repo),
        "log", f"-L{start},{end}:{file_path}",
        "--format=",
    ]
    if since:
        cmd.append(f"--since={since}")
    if until:
        cmd.append(f"--until={until}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # Common cause: file added in a single commit and -L can't bracket it.
        # Don't fail the whole run for one block.
        print(
            f"warning: git log -L failed for {file_path}:{start},{end}: "
            f"{r.stderr.strip().splitlines()[:1]}",
            file=sys.stderr,
        )
        return 0
    return _parse_added_deleted(r.stdout)


def compute_many(
    repo: Path,
    requests: list[tuple[str, str, int, int]],  # (file_path, blob_sha, start, end)
    since: str | None,
    until: str | None,
    cache: Cache,
    workers: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[tuple[str, int, int], int]:
    """Compute churn for many blocks in parallel, cached by blob SHA."""
    workers = workers or min(16, (os.cpu_count() or 4) * 2)

    results: dict[tuple[str, int, int], int] = {}
    pending: list[tuple[str, str, int, int]] = []
    for file_path, blob_sha, start, end in requests:
        key = Cache.make_key(blob_sha, start, end, since, until)
        cached = cache.get(key)
        if cached is not None:
            results[(file_path, start, end)] = cached
        else:
            pending.append((file_path, blob_sha, start, end))

    if not pending:
        return results

    def task(file_path: str, blob_sha: str, start: int, end: int) -> tuple[str, str, int, int, int]:
        v = compute_one(repo, file_path, start, end, since, until)
        return file_path, blob_sha, start, end, v

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(task, *p) for p in pending]
        done = 0
        total = len(futures)
        if on_progress:
            on_progress(done, total)
        for fut in as_completed(futures):
            file_path, blob_sha, start, end, value = fut.result()
            results[(file_path, start, end)] = value
            cache.put(Cache.make_key(blob_sha, start, end, since, until), value)
            done += 1
            if on_progress:
                on_progress(done, total)

    return results
