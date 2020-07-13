# -*- coding: utf-8 -*-
__all__ = ('ROS2SystemStateProbe')

from typing import Dict, List

import attr
import dockerblade
from loguru import logger

from state import SystemState
from .app.instance import AppInstance


@attr.s(frozen=True, auto_attribs=True)
class ROS2SystemStateProbe:
    """Provides an interface for obtaining the instantaneous state of a ROS
    system in terms of its publishers, subscribers, and services."""
    _app_instance: AppInstance = attr.ib()

    def probe(self) -> SystemState:
        """Obtains the instantaneous state of the associated ROS system."""
        mode_dict: Dict[str, Dict[str, List[str]]] = {'pub': {},
                                                      'sub': {},
                                                      'serv': {}}
        command = "rosnode list"
        try:
            output = self._app_instance.shell.check_output(command, text=True)
        except dockerblade.exceptions.CalledProcessError:
            logger.debug("Unable to retrieve rosnode list from command line")
        node_names = output.split('\r\n')
        for name in node_names:
            info = f"ros2 node info '{name}'"
            mode = 'None'
            try:
                output = self._app_instance.shell.check_output(info, text=True)
            except dockerblade.exceptions.CalledProcessError:
                logger.debug(f"Unable to retrieve {info}")
            output = output.replace(' ', '')
            lines = output.split('\r\n')
            for line in lines:
                if "Publications:" in line:
                    mode = 'pub'
                    continue
                elif "Subscriptions:" in line:
                    mode = 'sub'
                    continue
                elif "Services" in line:
                    mode = 'serv'
                    continue
                elif "Action Servers" in line:
                    break

                topic, space, fmt = line.partition(':')
                if topic in mode_dict[mode]:
                    (mode_dict[mode])[topic].append(name)
                else:
                    (mode_dict[mode])[topic] = [name]
                state = SystemState(publishers=mode_dict['pub'],
                                    subscribers=mode_dict['sub'],
                                    services=mode_dict['serv'])
        return state

    __call__ = probe
