# -*- coding: utf-8 -*-
__all__ = ('ROS2LaunchManager',)

from typing import Collection, List, Mapping, Optional, Sequence, Tuple, Union
import os
import shlex

from loguru import logger
import attr
import dockerblade

from .config import LaunchConfig
from .controller import ROSLaunchController
from ... import exceptions as exc
from .app.app import App

@attr.s(eq=False)
class ROS2LaunchManager:
    

    """Provides access to `roslaunch <wiki.ros.org/roslaunch/>`_ for an
    associated ROS system. This interface is used to locate, read, and write
    `launch XML files <http://wiki.ros.org/roslaunch/XML>`_,
    and to launch ROS nodes using those files.
    """
    _shell: dockerblade.shell.Shell = attr.ib(repr=False)
    _files: dockerblade.files.FileSystem = attr.ib(repr=False)

    def read(self,
             filename: str,
             *,
             package: Optional[str] = None,
             argv: Optional[Sequence[str]] = None
             ) -> LaunchConfig:
        """Produces a summary of the effects of a launch file.

        Parameters
        ----------
        filename: str
            The name of the launch file, or an absolute path to the launch
            file inside the container.
        package: str, optional
            The name of the package to which the launch file belongs.
        argv: Sequence[str], optional
            An optional sequence of command-line arguments that should be
            supplied to :code:`roslaunch`.

        Raises
        ------
        PackageNotFound
            If the given package could not be found.
        LaunchFileNotFound
            If the given launch file could not be found in the package.
        """
    raise NotImplementedError("ROS2 might not be able to read")

    def write(self,
              config: LaunchConfig,
              *,
              filename: Optional[str] = None
              ) -> str:
        """Writes a given launch configuration to disk as an XML launch file.

        Parameters
        ----------
        config: LaunchConfig
            A launch configuration.
        filename: str, optional
            The name of the file to which the configuration should be written.
            If no filename is given, a temporary file will be created. It is
            the responsibility of the caller to ensure that the temporary file
            is appropriately destroyed.

        Returns
        -------
        str
            The absolute path to the generated XML launch file.
        """
    raise NotImplementedError("ROS2 might not be able to write")

    def locate(self, 
               filename: str, 
               *, 
               app: App, 
               package: Optional[str] = None
               ) -> str:
        """Locates a given launch file.

        Parameters
        ----------
        filename: str
            The name of the launch file, or an absolute path to the launch
            file inside the container.
        package: str, optional
            Optionally specifies the name of the package to which the launch
            file belongs.

        Returns
        -------
        The absolute path to the launch file, if it exists.

        Raises
        ------
        PackageNotFound
            If the given package could not be found.
        LaunchFileNotFound
            If the given launch file could not be found in the package.
        """
        if not package:
            assert os.path.isabs(filename)
            return filename

        filename_original = filename
        app_description = app.describe()
        package_path = app_description.packages[package].path
        filename = os.path.join(package_path, 'launch', filename_original)
        if not self._files.isfile(filename):
            raise exc.LaunchFileNotFound(path=filename)
        logger.debug('determined location of launch file'
                     f' [{filename_original}] in package [{package}]: '
                     f'{filename}')
        return filename

    def launch(self,
               filename: str,
               *,
               app: App,
               package: Optional[str] = None,
               args: Optional[Mapping[str, Union[int, str]]] = None,
               prefix: Optional[str] = None,
               launch_prefixes: Optional[Mapping[str, str]] = None,
               node_to_remappings: Optional[Mapping[str, Collection[Tuple[str, str]]]] = None  # noqa
               ) -> ROSLaunchController:
        """Provides an interface to the roslaunch command.

        Parameters
        ----------
        filename: str
            The name of the launch file, or an absolute path to the launch
            file inside the container.
        package: str, optional
            The name of the package to which the launch file belongs.
        args: Dict[str, Union[int, str]], optional
            Keyword arguments that should be supplied to roslaunch.
        prefix: str, optional
            An optional prefix to add before the roslaunch command.
        launch_prefixes: Mapping[str, str], optional
            An optional mapping from nodes, given by their names, to their
            individual launch prefix.
        node_to_remappings: Mapping[str, Collection[Tuple[str, str]]], optional
            A collection of name remappings for each node, represented as a
            mapping from node names to a collection of remappings for that
            node, where each remapping is a tuple of the
            form :code:`(to, from)`.

        Returns
        -------
        ROSLaunchController
            An interface for inspecting and managing the launch process.

        Raises
        ------
        PackageNotFound
            If the given package could not be found.
        LaunchFileNotFound
            If the given launch file could not be found in the package.
        """
        shell = self._shell
        if not args:
            args = {}
        if not launch_prefixes:
            launch_prefixes = {}
        filename = self.locate(filename, app, package=package)

        if node_to_remappings or launch_prefixes:
            m = "Requires self.read: not yet implemented"
            raise NotImplementedError(m)

        cmd = ['ros2 launch', shlex.quote(filename)]
        launch_args: List[str] = [f'{arg}:={val}' for arg, val in args.items()]
        cmd += launch_args
        if prefix:
            cmd = [prefix] + cmd
        cmd_str = ' '.join(cmd)
        popen = shell.popen(cmd_str, stdout=True, stderr=True)

        return ROSLaunchController(filename=filename,
                                   popen=popen)

    __call__ = launch
