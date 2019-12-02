import argparse
import pathlib
import subprocess
import sys
import os
from contextlib import contextmanager

VERSIONS = ['2.80', '2.81']

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


def run_command(cmd: str) -> int:
    print(f'# {cmd}')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in iter(p.stdout.readline, b''):
        print(line.rstrip().decode("utf8"))
    return p.returncode


class Builder:
    def __init__(self, version: str, build_dir: pathlib.Path):
        self.version = version
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
                ret = run_command(f'git clone {GIT_BLENDER} blender')
                if ret:
                    raise Exception(ret)

            with pushd('blender'):
                # switch tag
                print(f'switch: {self.version}')
                ret = run_command(f'git tags')

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
    parser.add_argument("version", default="2.81")
    try:
        parsed = parser.parse_args()
    except TypeError as ex:
        print(ex)
        parser.print_help()
        sys.exit(1)

    print(parsed)
    builder = Builder(parsed.version, pathlib.Path(parsed.build))
    builder.git()
    builder.svn()
    builder.cmake()
    builder.build()
    builder.install()


if __name__ == '__main__':
    main()
