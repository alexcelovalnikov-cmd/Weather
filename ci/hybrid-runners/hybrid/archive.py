"""Extract verified runner payloads into a fresh disposable directory.
Regular files first, validated relative symlinks last: no archive entry follows a link.
"""
import os
import pathlib
import tarfile


def extract_runner(archive, destination):
    root=pathlib.Path(destination).resolve()
    if any(root.iterdir()):raise ValueError('destination must be empty')
    with tarfile.open(archive) as tf:
        members=tf.getmembers();links=[];seen=set()
        for m in members:
            relative=pathlib.PurePosixPath(m.name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('unsafe member path')
            target=(root/m.name).resolve()
            if not target.is_relative_to(root) or m.isdev() or m.islnk():
                raise ValueError('unsafe archive member')
            if str(relative) in seen:raise ValueError('duplicate archive entry')
            seen.add(str(relative))
            if m.issym():
                link=pathlib.PurePosixPath(m.linkname)
                resolved=(target.parent/m.linkname).resolve()
                if link.is_absolute() or not resolved.is_relative_to(root):
                    raise ValueError('unsafe symlink')
                links.append(m)
            elif not (m.isfile() or m.isdir()):raise ValueError('unsupported archive entry')
        # Reject payloads that would require traversing a symlink while writing a file.
        link_paths={pathlib.PurePosixPath(m.name) for m in links}
        for m in members:
            if any(parent in link_paths for parent in pathlib.PurePosixPath(m.name).parents):
                raise ValueError('member below a symlink')
        for m in members:
            if not m.issym():tf.extract(m,root)
        for m in links:
            target=root/m.name
            target.parent.mkdir(parents=True,exist_ok=True)
            os.symlink(m.linkname,target)
