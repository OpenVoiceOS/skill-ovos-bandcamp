#!/usr/bin/env python3
from setuptools import setup

# skill_id=package_name:SkillClass
PLUGIN_ENTRY_POINT = 'skill-bandcamp.jarbasai=skill_bandcamp:BandCampSkill'

setup(
    # this is the package name that goes on pip
    name='skill-bandcamp',
    version='0.0.1',
    description='ovos common play bandcamp skill plugin',
    url='https://github.com/JarbasSkills/skill-bandcamp',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    package_dir={"skill_bandcamp": ""},
    package_data={'skill_bandcamp': ['locale/*', 'vocab/*', "dialog/*"]},
    packages=['skill_bandcamp'],
    include_package_data=True,
    install_requires=["ovos-plugin-manager>=0.0.1a3",
                      "py_bandcamp~=0.7.0",
                      "ovos_workshop~=0.0.5a1"],
    keywords='ovos skill plugin',
    entry_points={'ovos.plugin.skill': PLUGIN_ENTRY_POINT}
)
