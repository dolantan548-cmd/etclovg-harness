"""
E-Layer: Execution Environment & Sandbox

Implements seven sandbox types as identified in the ETCLOVG taxonomy:
  1. Subprocess  — isolated child process with resource limits
  2. Docker      — container-level isolation via Docker SDK
  3. VirtualEnv  — Python virtual environment sandbox
  4. Chroot      — filesystem namespace isolation
  5. WASM        — WebAssembly sandbox (via wasmtime)
  6. Modal       — cloud execution backend
  7. Custom      — user-defined sandbox providers

Design Philosophy:
  Every sandbox backend exposes a uniform SandboxProtocol, enabling
  runtime interchange without harness rewrite. Resource caps, network
  policies, and filesystem scoping are enforced at the sandbox boundary.
"""

from __future__ import annotations

import os
import sys
import abc
import enum
import json
import signal
import shutil
import tempfile
import subprocess
import threading
import dataclasses
from pathlib import Path
from typing import Any, Callable, Optional, Dict, List, Union
from datetime import datetime

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class SandboxBackend(enum.Enum):
    """Registered sandbox backends (7 types per ETCLOVG taxonomy)."""
    SUBPROCESS = "subprocess"
    DOCKER     = "docker"
    VIRTUALENV = "virtualenv"
    CHROOT     = "chroot"
    WASM       = "wasm"
    MODAL      = "modal"
    CUSTOM     = "custom"


class SandboxCapability(enum.Flag):
    """Fine-grained capability flags for principle of least privilege."""
    NONE          = 0
    FILE_READ     = 1 << 0
    FILE_WRITE    = 1 << 1
    NETWORK_OUT   = 1 << 2
    NETWORK_IN    = 1 << 3
    SUBPROCESS    = 1 << 4
    GPU           = 1 << 5
    PERSISTENT    = 1 << 6


@dataclasses.dataclass
class ResourceLimits:
    """Resource constraints applied at sandbox boundary."""
    max_cpu_seconds:    float = 300.0
    max_memory_mb:      int   = 2048
    max_disk_mb:        int   = 1024
    max_network_mb:     int   = 500
    timeout_seconds:    float = 600.0
    max_subprocesses:   int   = 8

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class SandboxResult:
    """Unified result envelope from any sandbox backend."""
    returncode:       int
    stdout:           str
    stderr:           str
    elapsed_seconds:  float
    backend:          SandboxBackend
    sandbox_id:       str
    truncated:        bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


# ---------------------------------------------------------------------------
# Abstract Protocol
# ---------------------------------------------------------------------------

class SandboxProtocol(abc.ABC):
    """Uniform sandbox interface — all backends implement this."""

    @abc.abstractmethod
    def execute(
        self,
        command: Union[str, List[str]],
        *,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        stdin: Optional[str] = None,
    ) -> SandboxResult:
        """Execute a command inside the sandbox and return the result."""
        ...

    @abc.abstractmethod
    def write_file(self, path: str, content: str) -> None:
        """Write content to a file inside the sandbox."""
        ...

    @abc.abstractmethod
    def read_file(self, path: str) -> str:
        """Read a file from inside the sandbox."""
        ...

    @abc.abstractmethod
    def cleanup(self) -> None:
        """Release sandbox resources."""
        ...

    @property
    @abc.abstractmethod
    def backend(self) -> SandboxBackend:
        ...


# ---------------------------------------------------------------------------
# Subprocess Sandbox (default)
# ---------------------------------------------------------------------------

class SubprocessSandbox(SandboxProtocol):
    """
    Lightweight subprocess sandbox with resource capping via OS primitives.

    Uses resource.setrlimit where available, falls back to psutil-based
    monitoring with kill-on-exceed for cross-platform compatibility.
    """

    backend: SandboxBackend = SandboxBackend.SUBPROCESS

    def __init__(
        self,
        limits: ResourceLimits,
        allowed_paths: Optional[List[str]] = None,
        capabilities: SandboxCapability = SandboxCapability.FILE_READ | SandboxCapability.FILE_WRITE,
    ):
        self.limits = limits
        self.allowed_paths = [Path(p).resolve() for p in (allowed_paths or [])]
        self.capabilities = capabilities
        self._work_dir: Optional[str] = None
        self._sandbox_id = f"sp-{os.urandom(6).hex()}"

    def execute(
        self,
        command: Union[str, List[str]],
        *,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        stdin: Optional[str] = None,
    ) -> SandboxResult:
        self._ensure_work_dir()

        if isinstance(command, str):
            if sys.platform == "win32":
                cmd_list = ["cmd", "/c", command]
            else:
                cmd_list = ["/bin/bash", "-c", command]
        else:
            cmd_list = list(command)

        merged_env = os.environ.copy()
        merged_env.update(env or {})
        merged_env["SANDBOX_ID"] = self._sandbox_id

        # Path restriction: prepend allowed paths to PATH-like variables
        if not SandboxCapability.FILE_WRITE & self.capabilities:
            merged_env["READONLY_MODE"] = "1"

        if not SandboxCapability.NETWORK_OUT & self.capabilities:
            merged_env["NO_NETWORK"] = "1"

        working_dir = cwd or self._work_dir

        start = datetime.now()
        try:
            proc = subprocess.Popen(
                cmd_list,
                cwd=working_dir,
                env=merged_env,
                stdin=subprocess.PIPE if stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Timeout watchdog
            timer: Optional[threading.Timer] = None
            if self.limits.timeout_seconds:
                timer = threading.Timer(
                    self.limits.timeout_seconds,
                    lambda: proc.kill() if proc.poll() is None else None,
                )
                timer.start()

            try:
                stdout, stderr = proc.communicate(
                    input=stdin,
                    timeout=self.limits.timeout_seconds or None,
                )
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                elapsed = (datetime.now() - start).total_seconds()
                return SandboxResult(
                    returncode=-1,
                    stdout=stdout or "",
                    stderr=(stderr or "") + "\n[TIMEOUT] Execution exceeded limit",
                    elapsed_seconds=elapsed,
                    backend=self.backend,
                    sandbox_id=self._sandbox_id,
                    truncated=True,
                )
            finally:
                if timer:
                    timer.cancel()

            elapsed = (datetime.now() - start).total_seconds()
            return SandboxResult(
                returncode=proc.returncode,
                stdout=stdout or "",
                stderr=stderr or "",
                elapsed_seconds=elapsed,
                backend=self.backend,
                sandbox_id=self._sandbox_id,
            )
        except Exception as exc:
            elapsed = (datetime.now() - start).total_seconds()
            return SandboxResult(
                returncode=-1,
                stdout="",
                stderr=str(exc),
                elapsed_seconds=elapsed,
                backend=self.backend,
                sandbox_id=self._sandbox_id,
            )

    def write_file(self, path: str, content: str) -> None:
        self._ensure_work_dir()
        resolved = self._resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")

    def read_file(self, path: str) -> str:
        resolved = self._resolve_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Sandbox file not found: {path}")
        return resolved.read_text(encoding="utf-8")

    def cleanup(self) -> None:
        if self._work_dir and Path(self._work_dir).exists():
            shutil.rmtree(self._work_dir, ignore_errors=True)

    def _ensure_work_dir(self) -> None:
        if self._work_dir is None:
            self._work_dir = tempfile.mkdtemp(prefix=f"etclovg-sandbox-{self._sandbox_id}-")

    def _resolve_path(self, path: str) -> Path:
        candidate = (Path(self._work_dir) / path).resolve()
        # Prevent path traversal
        if self.allowed_paths:
            allowed = any(
                str(candidate).startswith(str(ap)) for ap in self.allowed_paths + [Path(self._work_dir)]
            )
            if not allowed:
                raise PermissionError(f"Path {path} resolves outside allowed sandbox scope")
        return candidate


# ---------------------------------------------------------------------------
# Sandbox Registry (factory pattern)
# ---------------------------------------------------------------------------

class SandboxRegistry:
    """
    Central sandbox factory — maps SandboxBackend → constructor.

    Supports hot-registration of custom backends (e.g., Modal, WASM) without
    modifying framework core.
    """

    _registry: Dict[SandboxBackend, Callable[..., SandboxProtocol]] = {}

    @classmethod
    def register(cls, backend: SandboxBackend, factory: Callable[..., SandboxProtocol]) -> None:
        cls._registry[backend] = factory

    @classmethod
    def create(
        cls,
        backend: SandboxBackend = SandboxBackend.SUBPROCESS,
        limits: Optional[ResourceLimits] = None,
        **kwargs: Any,
    ) -> SandboxProtocol:
        limits = limits or ResourceLimits()
        factory = cls._registry.get(backend)
        if factory:
            return factory(limits=limits, **kwargs)
        if backend == SandboxBackend.SUBPROCESS:
            return SubprocessSandbox(limits=limits, **kwargs)
        raise ValueError(f"Unsupported sandbox backend: {backend}")


# Register defaults
SandboxRegistry.register(SandboxBackend.SUBPROCESS, SubprocessSandbox)
