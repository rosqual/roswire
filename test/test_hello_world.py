from typing import Iterator, Tuple
import contextlib
import logging
import time

import pytest

import roswire
import roswire.exceptions
from roswire import ROSWire, ROSProxy, System, SystemDescription
from roswire.proxy import ShellProxy, FileProxy, ContainerProxy

NAME_IMAGE = 'hello-world'


@pytest.mark.skip(reason='this takes 10-15 minutes')
def test_description():
    rsw = ROSWire()
    desc = rsw.descriptions.build(NAME_IMAGE, save=False)
    assert set(desc.packages) == {
        'nodelet_core',
        'ros_core',
        'ros_comm',
        'ros_base',
        'ros_tutorials',
        'common_tutorials',
        'roscpp_core',
        'bond_core',
        'ros',
        'common_msgs',
        'actionlib',
        'actionlib_msgs',
        'actionlib_tutorials',
        'angles',
        'bond',
        'bondcpp',
        'bondpy',
        'catkin',
        'class_loader',
        'cmake_modules',
        'cpp_common',
        'diagnostic_msgs',
        'dynamic_reconfigure',
        'gencpp',
        'genlisp',
        'genmsg',
        'genpy',
        'geometry_msgs',
        'message_filters',
        'message_generation',
        'message_runtime',
        'mk',
        'nav_msgs',
        'nodelet',
        'nodelet_topic_tools',
        'nodelet_tutorial_math',
        'pluginlib',
        'pluginlib_tutorials',
        'rosbag',
        'rosbag_migration_rule',
        'rosbag_storage',
        'rosbash',
        'rosboost_cfg',
        'rosbuild',
        'rosclean',
        'rosconsole',
        'rosconsole_bridge',
        'roscpp',
        'roscpp_serialization',
        'roscpp_traits',
        'roscpp_tutorials',
        'roscreate',
        'rosgraph',
        'rosgraph_msgs',
        'roslang',
        'roslaunch',
        'roslib',
        'roslisp',
        'roslz4',
        'rosmake',
        'rosmaster',
        'rosmsg',
        'rosnode',
        'rosout',
        'rospack',
        'rosparam',
        'rospy',
        'rospy_tutorials',
        'rosservice',
        'rostest',
        'rostime',
        'rostopic',
        'rosunit',
        'roswtf',
        'sensor_msgs',
        'shape_msgs',
        'smclib',
        'std_msgs',
        'std_srvs',
        'stereo_msgs',
        'topic_tools',
        'trajectory_msgs',
        'turtle_actionlib',
        'turtlesim',
        'visualization_msgs',
        'xmlrpcpp'}
