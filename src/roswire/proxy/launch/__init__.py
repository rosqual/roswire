# -*- coding: utf-8 -*-
"""
This file implements a proxy for parsing the contents of launch files.
"""
__all__ = ('LaunchFileReader',)

from typing import (List, Optional, Sequence, Collection, Dict, Any, Mapping,
                    Tuple)
from copy import deepcopy
import logging
import xml.etree.ElementTree as ET

import attr

from ..substitution import resolve as resolve_args
from ..shell import ShellProxy
from ..file import FileProxy
from ...name import namespace_join
from ...exceptions import FailedToParseLaunchFile

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

_TAG_TO_LOADER = {}


@attr.s(slots=True)
class LaunchConfig:
    nodes = attr.ib(type=List[str])


@attr.s(frozen=True, slots=True)
class Parameter:
    name: str = attr.ib()
    value: str = attr.ib()  # TODO convert to appropriate type


@attr.s(frozen=True, slots=True)
class NodeConfig:
    namespace: str = attr.ib()
    name: str = attr.ib()
    typ: str = attr.ib()
    pkg: str = attr.ib()


@attr.s(frozen=True, slots=True)
class ROSConfig:
    nodes: Tuple[str, ...] = attr.ib(default=tuple())
    executables: Tuple[str, ...] = attr.ib(default=tuple())
    roslaunch_files: Tuple[str, ...] = attr.ib(default=tuple())

    def with_executable(self, executable: str) -> 'ROSConfig':
        """Specify an executable that should be run at launch."""
        executables = self.executables + (executable,)
        return attr.evolve(self, executables=executables)

    def with_roslaunch_file(self, filename: str) -> 'ROSConfig':
        roslaunch_files = self.roslaunch_files + (filename,)
        return attr.evolve(self, roslaunch_files=roslaunch_files)


@attr.s(frozen=True, slots=True)
class LaunchContext:
    filename: str = attr.ib()
    resolve_dict: Mapping[str, Any] = attr.ib()
    include_resolve_dict: Mapping[str, Any] = attr.ib()
    parent: 'LaunchContext' = attr.ib(default=None)
    namespace: str = attr.ib(default='/')
    arg_names: Tuple[str, ...] = attr.ib(default=tuple())
    env_args: Tuple[Tuple[str, str], ...] = attr.ib(default=tuple())
    pass_all_args: bool = attr.ib(default=False)

    def include_child(self,
                      ns: Optional[str],
                      filename: str
                      ) -> 'LaunchContext':
        ctx = self.child(ns)
        ctx = attr.evolve(ctx,
                          filename=filename,
                          arg_names=tuple(),
                          include_resolve_dict={})
        return ctx

    def child(self, ns: Optional[str] = None) -> 'LaunchContext':
        """Creates a child context that inherits from this context."""
        if ns is None:
            child_ns = self.namespace
        elif ns.startswith('/') or ns == '~':
            child_ns = ns
        else:
            child_ns = namespace_join(self.namespace, ns)
        return attr.evolve(self,
                           namespace=child_ns,
                           parent=self,
                           pass_all_args=False)

    def with_pass_all_args(self) -> 'LaunchContext':
        ctx = self
        if 'arg' in self.parent.resolve_dict:
            for var, val in self.parent.resolve_dict['arg'].items():
                ctx = ctx.with_arg(var, value=val)
        return attrs.evolve(ctx, pass_all_args=True)

    def process_include_args(self) -> 'LaunchContext':
        if self.include_resolve_dict is None:
            return self

        arg_dict = self.include_resolve_dict.get('arg', {})
        for arg in self.arg_names:
            if not arg in arg_dict:
                m = f'include arg [{arg}] is missing value.'
                raise FailedToParseLaunchFile(m)

        return attr.evolve(self,
                           arg_names=tuple(),
                           resolve_dict=deepcopy(self.include_resolve_dict),
                           include_resolve_dict=None)

    def with_argv(self, argv: Sequence[str]) -> 'LaunchContext':
        # ignore parameter assignment mappings
        logger.debug("loading argv: %s", argv)
        mappings: Dict[str, str] = {}
        for arg in (a for a in argv if ':=' in a):
            var, sep, val = [a.strip() for a in arg.partition(':=')]
            if not var.startswith('__'):
                mappings[var] = val
        logger.debug("loaded argv: %s", mappings)
        resolve_dict = self.resolve_dict.copy()
        resolve_dict['arg'] = mappings
        return attr.evolve(self, resolve_dict=resolve_dict)

    def with_env_arg(self, var: str, val: Any) -> 'LaunchContext':
        env_args = self.env_args + ((var, val),)
        return attr.evolve(self, env_args=env_args)

    def with_arg(self,
                 name: str,
                 default: Optional[Any] = None,
                 value: Optional[Any] = None,
                 doc: Optional = None
                 ) -> 'LaunchContext':
        logger.debug("adding arg [%s] to context", name)
        arg_names = self.arg_names
        if name in self.arg_names:
            if not self.pass_all_args:
                m = f"arg [{name}] has already been declared"
                raise FailedToParseLaunchFile(m)
        else:
            arg_names = arg_names + (name,)

        # decide which resolve dictionary should be used
        use_include_resolve_dict = self.include_resolve_dict is not None
        if use_include_resolve_dict:
            resolve_dict = self.include_resolve_dict
        else:
            resolve_dict = self.resolve_dict

        resolve_dict = resolve_dict.copy()
        arg_dict = resolve_dict['arg'] = resolve_dict.get('arg', {}).copy()

        if value is not None:
            if name in arg_dict and not self.pass_all_args:
                m = f"arg [{name}] value has already been defined."
                raise FailedToParseLaunchFile(m)
            arg_dict[name] = value
        elif default is not None:
            arg_dict[name] = arg_dict.get(name, default)

        # construct new context
        ctx = attr.evolve(self, arg_names=arg_names)
        if use_include_resolve_dict:
            return attr.evolve(ctx, include_resolve_dict=resolve_dict)
        else:
            return attr.evolve(ctx, resolve_dict=resolve_dict)


def tag(name: str, legal_attributes: Collection[str] = tuple()):
    legal_attributes = frozenset(legal_attributes)
    def wrap(loader):
        def wrapped(self,
                    ctx: LaunchContext,
                    cfg: ROSConfig,
                    elem: ET.Element
                    ) -> Tuple[LaunchContext, ROSConfig]:
            logger.debug("parsing <%s> tag", name)
            for attribute in elem.attrib:
                if attribute not in legal_attributes:
                    raise FailedToParseLaunchFile(m)
            ctx, cfg = loader(self, ctx, cfg, elem)
            logger.debug("new context: %s", ctx)
            return ctx, cfg
        _TAG_TO_LOADER[name] = wrapped
        return wrapped
    return wrap


class LaunchFileReader:
    def __init__(self, shell: ShellProxy, files: FileProxy) -> None:
        self.__shell = shell
        self.__files = files

    def _parse_file(self, fn: str) -> ET.Element:
        """Parses a given XML launch file to a root XML element."""
        root = ET.fromstring(self.__files.read(fn))
        if root.tag != 'launch':
            m = 'root of launch file must have <launch></launch> tags'
            raise FailedToParseLaunchFile(m)
        return root

    def _load_tags(self,
                   ctx: LaunchContext,
                   cfg: ROSConfig,
                   tags: Sequence[ET.Element]
                   ) -> LaunchContext:
        for tag in (t for t in tags if t.tag in _TAG_TO_LOADER):
            loader = _TAG_TO_LOADER[tag.tag]
            ctx, cfg = loader(self, ctx, cfg, tag)
        return ctx, cfg

    @tag('arg', ['name', 'type', 'pkg'])
    def _load_node_tag(self,
                       ctx: LaunchContext,
                       cfg: ROSConfig,
                       tag: ET.Element
                       ) -> Tuple[LaunchContext, ROSConfig]:
        name = tag.attrib['name']
        pkg = tag.attrib['type']
        node_type = tag.attrib['type']

        allowed = {'remap', 'rosparam', 'env', 'param'}
        self._load_tags([t for t in tags if t.tag in allowed])

        node = NodeConfig(name=name,
                          namespace=ctx.namespace,
                          pkg=pkg,
                          node_type=node_type)
        logger.debug("found node: %s", node)
        return ctx, cfg

    @tag('arg', ['name', 'default', 'value', 'doc'])
    def _load_arg_tag(self,
                      ctx: LaunchContext,
                      cfg: ROSConfig,
                      tag: ET.Element
                      ) -> Tuple[LaunchContext, ROSConfig]:
        ctx = ctx.with_arg(name=tag.attrib['name'],
                           value=tag.attrib.get('value'),
                           default=tag.attrib.get('default'),
                           doc=tag.attrib.get('doc'))
        return ctx, cfg

    @tag('env', ['name', 'value'])
    def _load_env_tag(self,
                      ctx: LaunchContext,
                      cfg: ROSConfig,
                      tag: ET.Element
                      ) -> Tuple[LaunchContext, ROSConfig]:
        ctx = ctx.with_env_arg(tag.attrib['name'], tag.attrib['value'])
        return ctx, cfg

    @tag('include', ['file', 'pass_all_args', 'ns', 'clear_params'])
    def _load_include_tag(self,
                          ctx: LaunchContext,
                          cfg: ROSConfig,
                          tag: ET.Element
                          ) -> Tuple[LaunchContext, ROSConfig]:
        include_filename = self._resolve_args(tag.attrib['file'])
        logger.debug("include file: %s", include_filename)

        # construct child context
        ctx_child = self._handle_ns_and_clear_params(ctx,
                                                     tag,
                                                     include_filename=include_filename)

        # TODO handle with_pass_all_args
        # if instructed to pass along args, then those args must be added to
        # the child context

        if 'pass_all_args' in tag.attrib:
            # TODO resolve and convert to boolean
            pass_all_args_s = tag.attrib['pass_all_args'].value
            pass_all_args = self._resolve_args(pass_all_args_s)
            if pass_all_args:
                ctx_child = ctx_child.with_pass_all_args()

        # handle child tags
        child_tags = [t for t in tag if t.tag in ('env', 'arg')]
        ctx_child, cfg = self._load_tags(ctx_child, cfg, child_tags)
        ctx_child = ctx_child.process_include_args()
        logger.debug("prepared include context: %s", ctx_child)

        return ctx, cfg

    def _handle_ns_and_clear_params(self,
                                    ctx: LaunchContext,
                                    tag: ET.Element,
                                    include_filename: Optional[str] = None
                                    ) -> LaunchContext:
        ns: Optional[str] = None
        if 'namespace' in tag.attrib:
            ns = tag.attrib['namespace']
            ns = self._resolve_args(ns)
            if not ns:
                m = f"<{tag.tag}> has empty attribute [namespace]"
                raise FailedToParseLaunchFile(m)

        if include_filename:
            ctx_child = ctx.include_child(ns, include_filename)
        else:
            ctx_child = ctx.child(ns)

        # TODO clear params

        return ctx_child

    def _resolve_args(self, s: str) -> str:
        """Resolves all substitution args in a given string."""
        return resolve_args(self.__shell, self.__files, s)

    def _load_launch(self,
                     ctx: LaunchContext,
                     cfg: ROSConfig,
                     launch: ET.Element
                     ) -> Tuple[LaunchContext, ROSConfig]:
        return self._load_tags(ctx, cfg, list(launch))

    def read(self, fn: str, argv: Optional[Sequence[str]] = None) -> None:
        """Parses the contents of a given launch file.

        Reference
        ---------
            http://wiki.ros.org/roslaunch/XML/node
            http://docs.ros.org/kinetic/api/roslaunch/html/roslaunch.xmlloader.XmlLoader-class.html
        """
        cfg = ROSConfig()
        ctx = LaunchContext(namespace='/',
                            filename=fn,
                            resolve_dict={},
                            include_resolve_dict={},
                            arg_names=tuple())
        if argv:
            ctx = ctx.with_argv(argv)

        launch = self._parse_file(fn)
        return self._load_launch(ctx, cfg, launch)
