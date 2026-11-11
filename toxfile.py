"""Project-local tox env customizations."""

from __future__ import annotations

import platform
import ssl
import typing as _t  # noqa: WPS111
from base64 import b64encode
from dataclasses import dataclass
from functools import cached_property
from hashlib import sha256
from logging import getLogger
from os import environ, getenv
from pathlib import Path
from shlex import join as _shlex_join
from sys import path as _sys_path

from tox.config.loader.memory import MemoryLoader
from tox.execute.request import StdinSource
from tox.plugin import impl
from tox.tox_env.python.pip.pip_install import Pip as PipInstaller
from tox.tox_env.python.virtual_env.package.cmd_builder import (
    VirtualEnvCmdBuilder,
)
from tox.tox_env.python.virtual_env.package.pyproject import (
    Pep517VirtualEnvPackager,
)
from tox.tox_env.python.virtual_env.runner import VirtualEnvRunner


if _t.TYPE_CHECKING:
    from tox.config.sets import ConfigSet
    from tox.config.types import Command
    from tox.session.state import State
    from tox.tox_env.api import ToxEnv
    from tox.tox_env.python.api import Python
    from tox.tox_env.register import ToxEnvRegister


_sys_path[:0] = ['bin/']  # noqa: WPS362

# pylint: disable-next=wrong-import-position
from pip_constraint_helpers import (  # noqa: E402
    get_constraint_file_path,
    get_runtime_python_tag,
)


IS_GITHUB_ACTIONS_RUNTIME = getenv('GITHUB_ACTIONS') == 'true'
FILE_APPEND_MODE = 'a'
UNICODE_ENCODING = 'utf-8'
SYS_PLATFORM = platform.system()
IS_WINDOWS = SYS_PLATFORM == 'Windows'
_PINNED_PREFIX = 'pinned-'


logger = getLogger(__name__)


def _log_debug_before_run_commands(msg: str) -> None:
    logger.debug(
        '%s%s> %s',  # noqa: WPS323
        'toxfile',
        ':tox_before_run_commands',
        msg,
    )


def _log_info_before_run_commands(msg: str) -> None:
    logger.info(
        '%s%s> %s',  # noqa: WPS323
        'toxfile',
        ':tox_before_run_commands',
        msg,
    )


def _log_warning_before_run_commands(msg: str) -> None:
    logger.warning(
        '%s%s> %s',  # noqa: WPS323
        'toxfile',
        ':tox_before_run_commands',
        msg,
    )


@impl
def tox_before_run_commands(tox_env: ToxEnv) -> None:  # noqa: WPS210, WPS213
    """Display test runtime info when in GitHub Actions CI/CD.

    This also injects ``SOURCE_DATE_EPOCH`` env var into build-dists.

    :param tox_env: A tox environment object.
    """
    if tox_env.name == 'build-dists':
        _log_debug_before_run_commands(
            'Setting the Git HEAD-based epoch for reproducibility in GHA...',
        )
        git_executable = 'git'
        git_log_cmd = (  # noqa: WPS317
            git_executable,
            '-c',
            'core.pager=',  # prevents ANSI escape sequences
            'log',
            '-1',
            '--pretty=%ct',  # noqa: WPS323
        )
        tox_env.conf['allowlist_externals'].append(git_executable)
        git_log_outcome = tox_env.execute(git_log_cmd, StdinSource.OFF)
        tox_env.conf['allowlist_externals'].pop()
        if git_log_outcome.exit_code:
            _log_warning_before_run_commands(
                f'Failed to look up Git HEAD timestamp. {git_log_outcome!s}',
            )
            return

        git_head_timestamp = git_log_outcome.out.strip()

        _log_info_before_run_commands(
            f'Setting `SOURCE_DATE_EPOCH={git_head_timestamp!s}` environment '
            'variable to facilitate build reproducibility...',
        )
        tox_env.environment_variables['SOURCE_DATE_EPOCH'] = git_head_timestamp

    if tox_env.name not in {'py', 'python'} or not IS_GITHUB_ACTIONS_RUNTIME:
        _log_debug_before_run_commands(
            'Not logging runtime info because this is not a test run on '
            'GitHub Actions platform...',
        )
        return

    _log_info_before_run_commands('INFO Logging runtime details...')

    systeminfo_executable = 'systeminfo'
    systeminfo_cmd = (systeminfo_executable,)
    if IS_WINDOWS:
        tox_env.conf['allowlist_externals'].append(systeminfo_executable)
        tox_env.execute(systeminfo_cmd, stdin=StdinSource.OFF, show=True)
        tox_env.conf['allowlist_externals'].pop()
    else:
        _log_debug_before_run_commands(
            f'Not running {systeminfo_executable!s} because this is '
            'not Windows...',
        )

    _log_info_before_run_commands('Logging platform information...')
    print(  # noqa: T201, WPS421
        'Current platform information:\n'
        f'{platform.platform()=}'
        f'{platform.system()=}'
        f'{platform.version()=}'
        f'{platform.uname()=}'
        f'{platform.release()=}',
    )

    _log_info_before_run_commands('Logging current OpenSSL module...')
    print(  # noqa: T201, WPS421
        'Current OpenSSL module:\n'
        f'{ssl.OPENSSL_VERSION=}\n'
        f'{ssl.OPENSSL_VERSION_INFO=}\n'
        f'{ssl.OPENSSL_VERSION_NUMBER=}',
    )


def _log_debug_after_run_commands(msg: str) -> None:
    logger.debug(
        '%s%s> %s',  # noqa: WPS323
        'toxfile',
        ':tox_after_run_commands',
        msg,
    )


def _compute_sha256sum(file_path: Path) -> str:
    return sha256(file_path.read_bytes()).hexdigest()


def _produce_sha256sum_line(file_path: Path) -> str:
    sha256_str = _compute_sha256sum(file_path)
    return f'{sha256_str!s}  {file_path.name!s}'


@impl
def tox_after_run_commands(tox_env: ToxEnv) -> None:
    """Compute combined dists hash post build-dists under GHA.

    :param tox_env: A tox environment object.
    """
    if tox_env.name == 'build-dists' and IS_GITHUB_ACTIONS_RUNTIME:
        _log_debug_after_run_commands(
            'Computing and storing the base64 representation '
            'of the combined dists SHA-256 hash in GHA...',
        )
        dists_dir_path = Path(__file__).parent / 'dist'
        emulated_sha256sum_output = '\n'.join(
            _produce_sha256sum_line(artifact_path)
            for artifact_path in dists_dir_path.glob('*')
        )
        emulated_base64_w0_output = b64encode(
            emulated_sha256sum_output.encode(),
        ).decode()

        with Path(environ['GITHUB_OUTPUT']).open(
            encoding=UNICODE_ENCODING,
            mode=FILE_APPEND_MODE,
        ) as outputs_file:
            print(  # noqa: T201, WPS421
                'combined-dists-base64-encoded-sha256-hash='
                f'{emulated_base64_w0_output!s}',
                file=outputs_file,
            )


class PinnedPipInstaller(PipInstaller):
    """A constraint-aware pip installer."""

    _non_existing_constraint_files: _t.ClassVar[set[Path]] = set()

    def post_process_install_command(self, cmd: Command) -> Command:
        """Inject an env-specific constraint into pip install.

        :param cmd: The pip install command to post-process.
        :returns: The pip install command with the constraint injected.
        """
        constraint_file_path = get_constraint_file_path(
            req_dir='dependencies/lock-files/',
            toxenv=self._env.name,
            python_tag=get_runtime_python_tag(),
        )
        constraint_cli_arg = f'--constraint={constraint_file_path!s}'
        if constraint_cli_arg in cmd.args:
            logger.debug(
                'tox-lock:%s> `%s` CLI option is already a '  # noqa: WPS323
                'part of the install command. Skipping...',
                self._env.name,
                constraint_cli_arg,
            )
        elif constraint_file_path.is_file():
            logger.info(
                'tox-lock:%s> Applying the pinned constraints '  # noqa: WPS323
                'file `%s` to the current env...',  # noqa: WPS323
                self._env.name,
                constraint_file_path,
            )
            logger.debug(
                'tox-lock:%s> Injecting `%s` into the install '  # noqa: WPS323
                'command...',
                self._env.name,
                constraint_cli_arg,
            )
            cmd.args.append(constraint_cli_arg)
        else:
            if constraint_file_path not in self._non_existing_constraint_files:
                logger.warning(
                    'tox-lock:%s> The expected pinned '  # noqa: WPS323
                    'constraints file for the current env does not exist '
                    '(should be `%s`). Skipping...',  # noqa: WPS323
                    self._env.name,
                    constraint_file_path,
                )
            self._non_existing_constraint_files.add(constraint_file_path)

        return super().post_process_install_command(cmd)


# pylint: disable-next=too-few-public-methods
class PinnedPipInstallerSelectedMixin:
    """A base class with pinned pip installer."""

    @cached_property
    def installer(self) -> PinnedPipInstaller:
        """Constraint-aware pip installer.

        :returns: A pip installer instance applying lock files.
        """
        return PinnedPipInstaller(_t.cast('Python', self))


# pylint: disable-next=too-many-ancestors
class PinnedPep517VirtualEnvPackager(
    PinnedPipInstallerSelectedMixin,
    Pep517VirtualEnvPackager,
):
    """A pinned package env."""

    @staticmethod
    def id() -> str:  # noqa: WPS602, WPS605
        """Render a pinned virtualenv packager identifier.

        :returns: The packager identifier.
        """
        return f'{_PINNED_PREFIX}{Pep517VirtualEnvPackager.id()}'


# pylint: disable-next=too-many-ancestors
class PinnedVirtualEnvCmdBuilder(
    PinnedPipInstallerSelectedMixin,
    VirtualEnvCmdBuilder,
):
    """A pinned run env."""

    @staticmethod
    def id() -> str:  # noqa: WPS602, WPS605
        """Render a pinned virtualenv command builder identifier.

        :returns: The command builder identifier.
        """
        return f'{_PINNED_PREFIX}{VirtualEnvCmdBuilder.id()}'


# pylint: disable-next=too-many-ancestors
class PinnedVirtualEnvRunner(
    PinnedPipInstallerSelectedMixin,
    VirtualEnvRunner,
):
    """A pinned virtualenv."""

    @staticmethod
    def id() -> str:  # noqa: WPS602, WPS605
        """Render a pinned virtualenv runner identifier.

        :returns: The runner identifier.
        """
        return f'{_PINNED_PREFIX}{VirtualEnvRunner.id()}'

    @property
    def _package_tox_env_type(self) -> str:
        return f'{_PINNED_PREFIX}{super()._package_tox_env_type}'

    @property
    def _external_pkg_tox_env_type(self) -> str:
        return f'{_PINNED_PREFIX}{super()._external_pkg_tox_env_type}'


@impl
def tox_register_tox_env(register: ToxEnvRegister) -> None:
    """Register locked virtualenv wrappers.

    :param register: The tox env type registry.
    """
    run_env_id = PinnedVirtualEnvRunner.id()

    logger.debug(
        'tox-lock:tox_register_tox_env> Registering the '  # noqa: WPS323
        'following run environment: %s',
        run_env_id,
    )
    register.add_run_env(PinnedVirtualEnvRunner)

    logger.debug(
        'tox-lock:tox_register_tox_env> Registering the '  # noqa: WPS323
        'following package environment: %s',
        PinnedPep517VirtualEnvPackager.id(),
    )
    register.add_package_env(PinnedPep517VirtualEnvPackager)

    logger.debug(
        'tox-lock:tox_register_tox_env> Registering the '  # noqa: WPS323
        'following package environment: %s',
        PinnedVirtualEnvCmdBuilder.id(),
    )
    register.add_package_env(PinnedVirtualEnvCmdBuilder)

    logger.debug(
        'tox-lock:tox_register_tox_env> Setting the default '  # noqa: WPS323
        'run environment to `%s`',
        run_env_id,
    )
    # pylint: disable-next=protected-access
    register._default_run_env = run_env_id  # noqa: SLF001, WPS437


# NOTE: The hook is marked as optional to keep the plugin loadable under
# NOTE: older tox versions that lack it, like the ones supporting Python 3.8.
@impl(optionalhook=True)
def tox_extend_envs() -> tuple[str, ...]:
    """Declare plugin-provided pip-compile in-memory tox envs.

    :returns: The names of the injected tox envs.
    """
    pip_compile_envs = tuple(env_cls.name for env_cls in pip_compile_env_clss)
    logger.debug(
        'tox-lock:tox_extend_envs> '  # noqa: WPS323
        'Adding ephemeral tox envs: %s',
        ', '.join(pip_compile_envs),
    )
    return pip_compile_envs


# pylint: disable-next=fixme
@dataclass(frozen=True)  # TODO: re-add kw_only=True, slots=True w/ py3.10+
class PipCompileToxEnvBase:
    """A base class for dynamically injected pip-compile envs."""

    _pos_args: tuple[str, ...] | None
    name: _t.ClassVar[str]
    _description: _t.ClassVar[str]
    deps: _t.ClassVar[list[str]] = ['pip-tools']
    commands_pre: _t.ClassVar[list[str]] = []
    commands_post: _t.ClassVar[list[str]] = []
    package: _t.ClassVar[str] = 'skip'

    @property
    def commands(self) -> list[str]:
        """Rendered ``pip-compile`` command.

        :returns: The ``pip-compile`` command line.
        """
        pip_compile_cmd = (
            'python',  # instead of `{envpython}`
            # '-bb',
            '-b',  # BytesWarning: Comparison between bytes and string @ Click
            '-E',
            '-s',
            '-I',
            '-Werror',
            # NOTE: Some dependencies are only shipped as sdists with
            # NOTE: outdated packaging metadata that recent `setuptools`
            # NOTE: versions warn about when building it. The build
            # NOTE: backend warnings get re-emitted as `UserWarning`
            # NOTE: subclasses, are out of our control, and must not fail
            # NOTE: the locking. Other warning categories remain fatal.
            '-Wdefault::UserWarning',
            '-mpiptools',
            'compile',
            *self._first_args,
            *self._trailing_args,
        )

        return [_shlex_join(pip_compile_cmd)]

    @property
    def description(self) -> str:
        """Prefixed tox env description.

        :returns: The tox env description.
        """
        return f'[tox-lock] {self._description}'

    @property
    def set_env(self) -> dict[str, str]:
        """Environment variables for tox env.

        :returns: The environment variables mapping.
        """
        cmd_posargs_trailer = ''
        if self._pos_args is not None:
            quoted_pos_args = _shlex_join(self._pos_args)
            cmd_posargs_trailer = f' -- {quoted_pos_args}'.rstrip()

        return {
            'CUSTOM_COMPILE_COMMAND': 'tox run -qq -e '
            f'{self.name}{cmd_posargs_trailer}',
        }

    def to_memory_loader(self) -> MemoryLoader:
        """Construct a memory loader populated with current settings.

        :returns: A tox in-memory config loader.
        """
        return MemoryLoader(
            base=[],  # disable inheritance for plugin-provided in-memory envs
            commands_pre=self.commands_pre,
            commands=self.commands,
            commands_post=self.commands_post,
            deps=self.deps,
            description=self.description,
            package=self.package,
            set_env=self.set_env,
        )

    @property
    def _first_args(self) -> tuple[str, ...]:
        return ()

    @property
    def _trailing_args(self) -> tuple[str, ...]:
        return ('--help',) if self._pos_args is None else self._pos_args


# pylint: disable-next=fixme
@dataclass(frozen=True)  # TODO: re-add kw_only=True, slots=True w/ py3.10+
class PipCompileToxEnv(PipCompileToxEnvBase):
    """An injected env for pip-compile invocations."""

    name: _t.ClassVar[str] = 'pip-compile'
    # Run `pip-compile {posargs:}` under {envpython}
    _description: _t.ClassVar[str] = 'Invoke pip-compile of pip-tools'


# pylint: disable-next=fixme
@dataclass(frozen=True)  # TODO: re-add kw_only=True, slots=True w/ py3.10+
class PipCompileBuildLockToxEnv(PipCompileToxEnvBase):
    """An injected env for making build env constraint file."""

    name: _t.ClassVar[str] = 'pip-compile-build-lock'
    # Produce a PEP 517/660 build deps lock using {envpython}
    _description: _t.ClassVar[str] = 'Produce a PEP 517/660 build deps lock'

    @property
    def _first_args(self) -> tuple[str, ...]:
        return (
            '--only-build-deps',
            '--all-build-deps',
            '--output-file=dependencies/lock-files/dist-build-constraints.txt',
        )

    @property
    def _trailing_args(self) -> tuple[str, ...]:
        return () if self._pos_args is None else self._pos_args


# pylint: disable-next=fixme
@dataclass(frozen=True)  # TODO: re-add kw_only=True, slots=True w/ py3.10+
class PipCompileToxEnvLockToxEnv(PipCompileToxEnvBase):
    """An injected env for making pre-env constraint files."""

    name: _t.ClassVar[str] = 'pip-compile-tox-env-lock'
    # Produce {posargs} lock file using {envpython}
    _description: _t.ClassVar[str] = (
        'Produce a lock file for the passed tox env using current python'
    )

    @property
    def _first_args(self) -> tuple[str, ...]:
        if not self._pos_args:
            return ()

        toxenv = self._pos_args[0]

        lock_file_name = get_constraint_file_path(
            req_dir='dependencies/lock-files/',
            toxenv=toxenv,
            python_tag=get_runtime_python_tag(),
        )

        return (
            f'--output-file={lock_file_name!s}',
            str(lock_file_name.parents[1] / 'direct' / f'{toxenv}.in')
            if lock_file_name
            else '',
        )

    @property
    def _trailing_args(self) -> tuple[str, ...]:
        return ('--help',) if self._pos_args is None else self._pos_args[1:]


pip_compile_env_clss = {
    PipCompileToxEnv,
    PipCompileBuildLockToxEnv,
    PipCompileToxEnvLockToxEnv,
}


@impl
def tox_add_core_config(
    core_conf: ConfigSet,  # noqa: ARG001  # pylint: disable=unused-argument
    state: State,
) -> None:
    """Define pip-compile in-memory tox environment configs.

    :param core_conf: The tox core configuration (unused).
    :param state: The tox session state.
    """
    # NOTE: Command injections are happening in this hook because this allows
    # NOTE: them to show up in the `tox config` output. In-memory configs do
    # NOTE: not support substitutions like `{posargs}` or `{envpython}`. We
    # NOTE: could've stored the posargs value and used `tox_env.execute()` in
    # NOTE: the `tox_before_run_commands()` hook that has access to the
    # NOTE: virtualenv's interpreter path via either `tox_env.env_python()`, or
    # NOTE: `tox_env.session.interpreter.executable`. This would've allowed us
    # NOTE: to use the absolute path to the executable and the positional args
    # NOTE: smuggled across contexts via a module-global variable. However,
    # NOTE: this would mean that `tox config` would not be able to show that.
    # NOTE: Instead of `{envpython}` that is unusable here, we rely on the
    # NOTE: `python` name in hopes that tox's machinery is good enough not to
    # NOTE: break its path resolution.

    tox_env_definitions = {
        env_cls.name: env_cls(
            # instead of `{posargs}` in commands
            _pos_args=state.conf.pos_args(to_path=None),
        )
        for env_cls in pip_compile_env_clss
    }
    for env_name, tox_env in tox_env_definitions.items():
        in_memory_config_loader = tox_env.to_memory_loader()

        logger.debug(
            'tox-lock:tox_add_core_config> Adding an '  # noqa: WPS323
            'in-memory config for ephemeral `%s` tox environment...',
            env_name,
        )

        state.conf.memory_seed_loaders[env_name].append(
            in_memory_config_loader,  # src/tox/provision.py:provision()
        )


def tox_append_version_info() -> str:
    """Produce text to be rendered in ``tox --version``.

    :returns: A string with the plugin details.
    """
    return '[toxfile]'  # Broken: https://github.com/tox-dev/tox/issues/3508
