import pathlib

HERE = pathlib.Path(__file__).absolute().parent
CLONE_DIR = HERE / 'blender'

from git.repo import Repo

REPO = None
if CLONE_DIR.exists():
    REPO = Repo(CLONE_DIR)

from doit.action import CmdAction

CONFIGURE_FLAGS = ' '.join([
    '-DCMAKE_BUILD_TYPE=Release',
    '-DWITH_INTERNATIONAL=OFF',
    '-DWITH_INPUT_NDOF=OFF',
    '-DWITH_CYCLES=OFF',
    '-DWITH_OPENVDB=OFF',
    '-DWITH_LIBMV=OFF',
    '-DWITH_MEM_JEMALLOC=OFF',
])

BPY_FLAGS = ' '.join([
    '-DWITH_PYTHON_INSTALL=OFF', '-DWITH_PYTHON_INSTALL_NUMPY=OFF',
    '-DWITH_PYTHON_MODULE=ON'
])

if not REPO:

    def task_clone():
        return {
            'actions': [
                CmdAction('git clone https://github.com/blender/blender.git',
                          cwd=CLONE_DIR.parent),
            ]
        }

else:

    def task__worktree():
        for tag in REPO.tags:
            base_dir = HERE / f'tags/{tag.name}'
            worktree = base_dir / 'blender'
            action = {
                'name':
                tag.name,
                'actions': [
                    CmdAction(f'git worktree add {worktree} {tag.name}',
                              cwd=CLONE_DIR),
                    CmdAction(f'git submodule update --init', cwd=worktree)
                ],
                'uptodate': [True],
                'targets':
                [worktree / 'release/scripts/addons/io_scene_obj/__init__.py']
            }
            yield action

    def task_bpy_build():
        for tag in REPO.tags:
            base_dir = HERE / f'tags/{tag.name}'
            install = base_dir / 'bpy_install'
            yield {
                'name':
                tag.name,
                'task_dep': [f'_worktree:{tag.name}'],
                'verbosity':
                2,
                'actions': [
                    CmdAction(
                        f'cmake -S blender -B bpy -G Ninja {CONFIGURE_FLAGS} {BPY_FLAGS}',
                        cwd=base_dir),
                    CmdAction(f'cmake --build bpy', cwd=base_dir),
                    CmdAction(
                        f'cmake --install bpy --config Release --prefix {install}',
                        cwd=base_dir)
                ],
            }

    DOIT_CONFIG = {
        'default_tasks': [],
    }

