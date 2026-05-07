from setuptools import find_packages, setup

package_name = 'robot_voice'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/robot.launch.py', 'launch/remote.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pitosalas',
    maintainer_email='pitosalas@gmail.com',
    description='ROS-free voice pipeline: wake word, STT, intent mapping, audio feedback.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'voice_smoke_test = robot_voice.runtime:main',
            'voice_input = robot_voice.voice_input_node:main',
        ],
    },
)
