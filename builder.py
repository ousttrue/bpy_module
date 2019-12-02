import argparse
import pathlib
import subprocess
import sys
import os
from typing import List, Tuple
from contextlib import contextmanager

GIT_BLENDER = 'git://git.blender.org/blender.git'


@contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    print(f'pushd: {new_dir}')
    os.chdir(new_dir)
    try:
        yield
    finally:
        print(f'popd: {previous_dir}')
        os.chdir(previous_dir)


def run_command(cmd: str) -> Tuple[int, List[str]]:
    print(f'# {cmd}')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []
    for line_bytes in iter(p.stdout.readline, b''):
        line = line_bytes.rstrip().decode('utf8')
        print(line)
        lines.append(line)
    return p.returncode, lines


class Builder:
    def __init__(self, tag: str, build_dir: pathlib.Path):
        self.tag = tag
        self.build_dir = build_dir
        self.repository = self.build_dir / 'blender'
        print(self)

    def git(self) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)
        # print(f'git: {self.build_dir}')
        with pushd(self.build_dir):
            if not self.repository.exists():
                print(f'clone: {self.repository}')
                # clone
                ret, _ = run_command(f'git clone {GIT_BLENDER} blender')
                if ret:
                    raise Exception(ret)

            with pushd('blender'):
                # switch tag
                ret, tags = run_command(f'git tag')
                if self.tag not in tags:
                    raise Exception(f'unknown tag: {self.tag}')
                ret, _ = run_command(f'git checkout refs/tags/{self.tag}')
                ret, _ = run_command(f'git status')

    def svn(self) -> None:
        print('svn')

    def cmake(self) -> None:
        print('cmake')

    def build(self) -> None:
        print('build')

    def install(self) -> None:
        print('install')


def main():
    parser = argparse.ArgumentParser('blender module builder')
    parser.add_argument("--build", required=True)
    parser.add_argument("--install", required=True)
    parser.add_argument("tag")
    try:
        parsed = parser.parse_args()
    except TypeError as ex:
        print(ex)
        parser.print_help()
        sys.exit(1)

    print(parsed)
    builder = Builder(parsed.tag, pathlib.Path(parsed.build))
    builder.git()
    builder.svn()
    builder.cmake()
    builder.build()
    builder.install()


if __name__ == '__main__':
    main()
