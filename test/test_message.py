# -*- coding: utf-8 -*-
import pytest
import roswire
from roswire.definitions import Time


@pytest.mark.parametrize('app', ['fetch'], indirect=True)
def test_encode_and_decode(app: roswire.App):
    Header = app.description.types['std_msgs/Header']
    orig = Header(seq=32, stamp=Time(secs=9781, nsecs=321), frame_id='')
    assert orig == Header.decode(orig.encode())


@pytest.mark.parametrize('app', ['fetch'], indirect=True)
def test_to_and_from_dict(app: roswire.App):
    Quaternion = app.description.types['geometry_msgs/Quaternion']
    Point = app.description.types['geometry_msgs/Point']
    Pose = app.description.types['geometry_msgs/Pose']
    orientation = Quaternion(x=0.5, y=1.0, z=2.0, w=3.0)
    position = Point(x=10.0, y=20.0, z=30.0)
    pose = Pose(position=position, orientation=orientation)
    assert pose.to_dict() == {
        'orientation': {
            'x': orientation.x,
            'y': orientation.y,
            'z': orientation.z,
            'w': orientation.w},
        'position': {
            'x': position.x,
            'y': position.y,
            'z': position.z
        }}


def test_message_with_optional_default_values():
    package = 'rcl_interfaces'
    name = 'ParameterDescriptor'

    test_dir = os.path.dirname(__file__)
    msg_filename = os.path.join(test_dir, 'msg/ParameterDescriptor.msg')
    with open(msg_filename, 'r') as f:
        definition = f.read()

    msg_format = MsgFormat.from_string(package, name, definition)
    assert msg_format.package == package
    assert msg_format.name == name
    assert msg_format.text == definition
    assert not msg_format.constants
    assert len(msg_format.fields) == 7
