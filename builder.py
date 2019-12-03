import argparse
import pathlib
import subprocess
import sys
import os
import shutil
import multiprocessing
from typing import List, Tuple
from contextlib import contextmanager

GIT_BLENDER = 'git://git.blender.org/blender.git'
HERE = pathlib.Path(__file__).parent
VSWHERE = HERE / 'vswhere.exe'


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


def run_command(cmd: str, encoding='utf-8') -> Tuple[int, List[str]]:
    print(f'# {cmd}')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []
    for line_bytes in iter(p.stdout.readline, b''):
        line = line_bytes.rstrip().decode(encoding)
        print(line)
        lines.append(line)
    return p.returncode, lines


def get_cmake() -> pathlib.Path:
    ret, outs = run_command(
        f'{VSWHERE} -latest -products * -requires Microsoft.VisualStudio.Component.VC.CMake.Project -property installationPath'
    )
    return pathlib.Path(
        f'{outs[0]}/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    )


def get_msbuild() -> pathlib.Path:
    ret, outs = run_command(
        f'{VSWHERE} -latest -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe'
    )
    return pathlib.Path(outs[0])


class Builder:
    def __init__(self, tag: str, workspace: pathlib.Path):
        self.tag = tag
        self.workspace = workspace
        self.build_dir: pathlib.Path = self.workspace / 'build'
        self.repository: pathlib.Path = self.workspace / 'blender'
        print(self)

    def git(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        with pushd(self.workspace):
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
                ret, _ = run_command(
                    f'git submodule update --init --recursive')
                ret, _ = run_command(f'git status')

    def svn(self) -> None:
        # print('svn')
        make_update_py = self.repository / 'build_files/utils/make_update.py'
        with pushd(self.repository):
            run_command(f'{sys.executable} {make_update_py}')

    def clear_build_dir(self) -> None:
        shutil.rmtree(self.build_dir, ignore_errors=True)

    def cmake(self) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)
        cmake = get_cmake()
        with pushd(self.build_dir):
            run_command(
                f'{cmake} ../blender -DWITH_PYTHON_INSTALL=OFF -DWITH_PYTHON_INSTALL_NUMPY=OFF -DWITH_PYTHON_MODULE=ON -DWITH_OPENCOLLADA=OFF'
            )

    def build(self) -> None:
        print('build')
        msbuild = get_msbuild()
        sln = next(self.build_dir.glob('*.sln'))
        count = multiprocessing.cpu_count()
        with pushd(self.build_dir):
            run_command(f'{msbuild} INSTALL.vcxproj -maxcpucount:{count} -p:configuration=Release',
                        encoding='cp932')

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
    builder.clear_build_dir()
    builder.cmake()
    builder.build()
    builder.install()


if __name__ == '__main__':
    main()
