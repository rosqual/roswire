# -*- coding: utf-8 -*-
__all__ = (
    "CMakeInfo",
    "CMakeTarget",
    "CMakeExtractor",
    "PackageCMakeTargets",
    "SourceLanguage",
)

import abc
import enum
import os
import typing as t
from pathlib import Path
from typing import Any, Iterable  # noqa: F401, E501 # Needed for tuple_from_iterable and argparse

import attr
import dockerblade
from loguru import logger

from . import Package
from .cmake import (
    argparse as cmake_argparse,
    ParserContext,
)
from .nodelet_xml import NodeletInfo

if t.TYPE_CHECKING:
    from .. import AppInstance


class SourceLanguage(enum.Enum):
    CXX = "cxx"
    PYTHON = "python"


@attr.s(auto_attribs=True, slots=True)
class CMakeTarget:
    name: t.Optional[str]
    language: SourceLanguage
    sources: t.Set[str]
    restrict_to_paths: t.Set[str]

    def to_dict(self) -> t.Dict[str, t.Any]:
        return {"name": self.name,
                "language": self.language.value,
                "sources": list(self.sources),
                "path_restrictions": list(self.restrict_to_paths)}

    @classmethod
    def from_dict(cls, info: t.Dict[str, t.Any]) -> "CMakeTarget":
        return CMakeTarget(info["name"],
                           SourceLanguage(info["language"]),
                           set(info["sources"]),
                           set(info["path_restrictions"]))


@attr.s(auto_attribs=True, slots=True)
class PackageCMakeTargets:
    """Describes the CMake build targets for a given package

    Attributes
    ----------
    package: Package
        the package to which these sources belong
    targets: t.Collection[CMakeTarget]
        the build targets that are contained within this package
    """

    package: Package
    targets: t.Collection[CMakeTarget]


@attr.s(auto_attribs=True, slots=True)
class CMakeBinaryTarget(CMakeTarget):
    @property
    def entrypoint(self) -> t.Optional[str]:
        if self.language == SourceLanguage.CXX:
            return "main"
        else:
            return None


@attr.s(auto_attribs=True, slots=True)
class CMakeLibraryTarget(CMakeBinaryTarget):
    _entrypoint: t.Optional[str] = attr.ib(init=False)

    @property
    def entrypoint(self) -> t.Optional[str]:
        return self._entrypoint

    @entrypoint.setter
    def entrypoint(self, entrypoint: str) -> None:
        self._entrypoint = entrypoint

    def to_dict(self) -> t.Dict[str, t.Any]:
        d = super().to_dict()
        if self.entrypoint:
            d['entrypoint'] = self.entrypoint
        return d

    @classmethod
    def from_dict(cls, info: t.Dict[str, t.Any]) -> 'CMakeLibraryTarget':
        target = CMakeLibraryTarget(info["name"],
                                    SourceLanguage(info["language"]),
                                    set(info["sources"]),
                                    set(info["path_restrictions"]),
                                    )
        if 'entrypoint' in info:
            target.entrypoint = info['entrypoint']
        return target


@attr.s(auto_attribs=True, slots=True, frozen=True)
class CMakeInfo:
    targets: t.Mapping[str, CMakeTarget]


@attr.s(auto_attribs=True)
class CMakeExtractor(abc.ABC):
    _files: dockerblade.FileSystem

    @classmethod
    @abc.abstractmethod
    def for_app_instance(
        cls,
        app_instance: "AppInstance"
    ) -> "CMakeExtractor":
        ...

    @abc.abstractmethod
    def get_cmake_info(
        self,
        package: Package
    ) -> CMakeInfo:
        ...

    @abc.abstractmethod
    def package_paths(self, package: Package) -> t.Set[str]:
        ...

    def get_nodelet_entrypoints(self, package: Package) -> t.Mapping[str, str]:
        entrypoints: t.Dict[str, str] = {}
        workspace = package.path
        nodelets_xml_path = os.path.join(workspace, 'nodelet_plugins.xml')
        if self._files.exists(nodelets_xml_path):
            nodelet_info = NodeletInfo.from_nodelet_xml(
                self._files.read(nodelets_xml_path)
            )
            for info in nodelet_info.libraries:
                package_and_name = info.class_name.split('/')
                # TODO can package in XML nodelet differ from package.name?
                name = package_and_name[1]
                entrypoint = info.class_type + "::onInit"
                entrypoints[name] = entrypoint
        return entrypoints

    def _process_cmake_contents(
        self,
        file_contents: str,
        package: Package,
        cmake_env: t.Dict[str, str],
    ) -> CMakeInfo:
        """
        Processes the contents of a CMakeLists.txt file for information about
        executables. Recursively includes other CMakeLists.txt files that may
        be included.

        Parameters
        ----------
        file_contents: str
            The contents of the CMakeLists.txt file
        package: Package
            The package where the CMakeLists.txt file is defined
        cmake_env: t.Dict[str, str]
            Any context variables for processing the contents

        Returns
        -------
        CMakeInfo:
            Information about the targets in CMakeLists.txt
        """
        executables: t.Dict[str, CMakeTarget] = {}
        context = ParserContext().parse(file_contents, skip_callable=False)
        for cmd, args, _arg_tokens, (_fname, _line, _column) in context:
            cmd = cmd.lower()
            if cmd == "set":
                opts, args = cmake_argparse(
                    args,
                    {"PARENT_SCOPE": "-", "FORCE": "-", "CACHE": "*"}
                )
                cmake_env[args[0]] = ";".join(args[1:])
            if cmd == "unset":
                opts, args = cmake_argparse(args, {"CACHE": "-"})
                cmake_env[args[0]] = ""
            if cmd == "add_executable" or cmd == 'cuda_add_executable':
                self.__process_add_executable(
                    args,
                    cmake_env,
                    executables,
                    package)
            if cmd == "catkin_install_python":
                self.__process_python_executables(
                    args,
                    cmake_env,
                    executables)
            if cmd == 'add_library' or cmd == 'cuda_add_library':
                self.__process_add_library(
                    args,
                    cmake_env,
                    executables,
                    package)
            if cmd == "add_subdirectory":
                executables = self.__process_add_subdirectory(
                    args,
                    cmake_env,
                    executables,
                    package)
        return CMakeInfo(executables)

    def __process_add_subdirectory(
        self,
        args: t.List[str],
        cmake_env: t.Dict[str, str],
        executables: t.Dict[str, CMakeTarget],
        package: Package
    ) -> t.Dict[str, CMakeTarget]:
        new_env = cmake_env.copy()
        new_env['cwd'] = os.path.join(cmake_env.get('cwd', '.'), args[0])
        join = os.path.join(package.path, new_env['cwd'])
        cmakelists_path = os.path.join(join, 'CMakeLists.txt')
        logger.debug(f"Processing {cmakelists_path}")
        included_package_info = self._process_cmake_contents(
            self._files.read(cmakelists_path),
            package,
            new_env,
        )
        executables = {
            **executables,
            **{s: included_package_info.targets[s]
               for s in included_package_info.targets}
        }
        return executables

    def __process_add_executable(
        self,
        args: t.List[str],
        cmake_env: t.Dict[str, str],
        executables: t.Dict[str, CMakeTarget],
        package: Package
    ) -> None:
        name = args[0]
        sources: t.Set[str] = set()
        for source in args[1:]:
            if 'cwd' in cmake_env:
                sources.add(os.path.join(cmake_env['cwd'], source))
            else:
                sources.add(source)
        logger.debug(f"Adding C++ sources for {name}")
        executables[name] = CMakeBinaryTarget(
            name=name,
            language=SourceLanguage.CXX,
            sources=sources,
            restrict_to_paths=self.package_paths(package))

    def __process_add_library(
        self,
        args: t.List[str],
        cmake_env: t.Dict[str, str],
        executables: t.Dict[str, CMakeTarget],
        package: Package
    ) -> None:
        name = args[0]
        if 'cwd' in cmake_env:
            sources = {os.path.join(cmake_env['cwd'], s) for s in args[1:]}
        else:
            sources = set(args[1:])
        logger.debug(f"Adding C++ library {name}")
        executables[name] = CMakeLibraryTarget(
            name,
            SourceLanguage.CXX,
            sources,
            self.package_paths(package))

    def __process_python_executables(
        self,
        args: t.List[str],
        cmake_env: t.Dict[str, str],
        executables: t.Dict[str, CMakeTarget]
    ) -> None:
        opts, args = cmake_argparse(
            args,
            {"PROGRAMS": "*", "DESTINATION": "*"}
        )
        if 'PROGRAMS' not in opts:
            raise ValueError('PROGRAMS not specified in catin_install_python')

        for program in opts['PROGRAMS']:
            # http://docs.ros.org/en/jade/api/catkin/html/howto/format2/installing_python.html  # noqa: F401, E501
            # Convention is that ros python nodes are in nodes/ directory.
            # All others are in scripts/. So just include python installs
            # that are in nodes/
            if program.startswith("nodes/"):
                name = Path(program[0]).stem
                sources: t.Set[str] = set()
                if 'cwd' in cmake_env:
                    sources = set()
                    sources.add(os.path.join(cmake_env['cwd'], program))
                else:
                    sources.add(program)
                logger.debug(f"Adding Python sources for {name}")
                executables[name] = CMakeTarget(name,
                                                SourceLanguage.PYTHON,
                                                sources,
                                                set())
