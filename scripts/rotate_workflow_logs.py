#!/usr/bin/env python3
"""Archive oversized logs without discarding concurrent writers' source bytes.

POSIX only. Rotation keeps up to ten highest numeric versions within 200 KiB.
Full source logs remain in docs/archive, including the inode held by an existing
writer. Run only when editors are idle; advisory locks coordinate tool users.
"""
import argparse
import fcntl
import os
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 200 * 1024
KEEP = 10
MAX_INPUT = 16 * 1024 * 1024
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def sections(text):
    """Version headings outside fenced examples, with exact source offsets."""
    headings, offset, fence = [], 0, None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None:
            match = re.match(r'^## (?:Prompt )?v(\d+(?:\.\d+)*)(?:\s|$)', line)
            if match:
                headings.append((offset, tuple(map(int, match.group(1).split('.')))))
        offset += len(line)
    return headings


def child_directory(parent, name):
    try:
        os.mkdir(name, dir_fd=parent)
    except FileExistsError:
        pass
    return os.open(name, FLAGS, dir_fd=parent)


def identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def rotate(root=ROOT, check=False):
    root = Path(root)
    root_fd = os.open(root, FLAGS)
    needed = []
    try:
        for name in ('memory.md', 'prompts.md'):
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
            except FileNotFoundError:
                continue
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                before = os.fstat(fd)
                if before.st_size <= LIMIT:
                    continue
                if before.st_size > MAX_INPUT:
                    raise ValueError(f'{name} exceeds supported 16 MiB input; archive manually')
                if any(re.fullmatch(rf'\.?{re.escape(name)}\.sw.', p) for p in os.listdir(root_fd)):
                    raise ValueError(f'editor swap file exists for {name}')
                with os.fdopen(os.dup(fd), encoding='utf-8') as stream:
                    original = stream.read(MAX_INPUT + 1)
                if len(original.encode()) > MAX_INPUT:
                    raise ValueError(f'{name} exceeds supported input size')
                headings = sections(original)
                if len(headings) < 2:
                    raise ValueError(f'{name} has no separable version sections; archive manually')
                ranked = sorted(headings, key=lambda row: row[1])
                retained = original
                for keep in range(min(KEEP, len(headings)-1), 0, -1):
                    selected = {offset for offset, _ in ranked[-keep:]}
                    retained = original[:headings[0][0]] + ''.join(
                        original[start:headings[i+1][0] if i+1 < len(headings) else len(original)]
                        for i, (start, _) in enumerate(headings) if start in selected)
                    if len(retained.encode()) <= LIMIT:
                        break
                else:
                    raise ValueError(f'{name} latest section alone exceeds limit; split it manually')
                # Validate directory ancestry even in check mode, without creating it.
                if (root/'docs').is_symlink() or (root/'docs/archive').is_symlink():
                    raise ValueError('refusing symlink archive ancestry')
                needed.append(name)
                if check:
                    continue
                docs_fd = child_directory(root_fd, 'docs')
                try:
                    archive_fd = child_directory(docs_fd, 'archive')
                finally:
                    os.close(docs_fd)
                try:
                    token = uuid.uuid4().hex
                    snapshot = f'{Path(name).stem}-{token}-snapshot.md'
                    saved = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                    0o600, dir_fd=archive_fd)
                    with os.fdopen(saved, 'w', encoding='utf-8') as stream:
                        stream.write(original)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if identity(os.stat(name, dir_fd=root_fd, follow_symlinks=False)) != identity(before):
                        raise ValueError(f'{name} changed; snapshot preserved, source untouched')
                    retired = f'{Path(name).stem}-{token}-full.md'
                    # Move rather than replace/delete the source inode. A writer
                    # holding an old fd can still append to this full archive.
                    os.rename(name, retired, src_dir_fd=root_fd, dst_dir_fd=archive_fd)
                    if identity(os.stat(retired, dir_fd=archive_fd)) != identity(before):
                        try:
                            os.link(retired, name, src_dir_fd=archive_fd, dst_dir_fd=root_fd,
                                    follow_symlinks=False)
                        except FileExistsError:
                            pass  # a concurrent writer owns the new source; preserve it
                        raise ValueError(f'{name} changed during rotation; full logs preserved')
                    try:
                        new_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                         0o600, dir_fd=root_fd)
                    except FileExistsError as exc:
                        raise ValueError(f'{name} was recreated concurrently; full archive preserved') from exc
                    with os.fdopen(new_fd, 'w', encoding='utf-8') as stream:
                        stream.write(retained)
                finally:
                    os.close(archive_fd)
            finally:
                os.close(fd)
    finally:
        os.close(root_fd)
    return needed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    needed = rotate(check=args.check)
    if args.check and needed:
        raise SystemExit('Rotation needed: '+', '.join(needed))
    print('Workflow logs: '+(', '.join(needed) if needed else 'within limit'))


if __name__ == '__main__':
    main()
