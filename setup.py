#!/usr/bin/env python3
from setuptools import setup
import os
from os import walk, path


URL = "https://github.com/OpenVoiceOS/skill-ovos-bandcamp"
SKILL_CLAZZ = "BandCampSkill"  # needs to match __init__.py class name
PYPI_NAME = "skill-bandcamp"  # pip install PYPI_NAME


# below derived from github url to ensure standard skill_id
SKILL_AUTHOR, SKILL_NAME = URL.split(".com/")[-1].split("/")
SKILL_PKG = SKILL_NAME.lower().replace('-', '_')
PLUGIN_ENTRY_POINT = f'{SKILL_NAME.lower()}.{SKILL_AUTHOR.lower()}={SKILL_PKG}:{SKILL_CLAZZ}'
# skill_id=package_name:SkillClas

setup(
    name=PYPI_NAME,
    version='0.0.1',
    description='ovos common play bandcamp skill plugin',
    url=URL,
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    package_dir={SKILL_PKG: ""},
    package_data={SKILL_PKG: find_resource_files()},
    packages=[SKILL_PKG],
    include_package_data=True,
    install_requires=["ovos-plugin-manager>=0.0.1a3",
                      "py_bandcamp~=0.7.0",
                      "ovos_workshop~=0.0.5a1"],
    keywords='ovos skill plugin',
    entry_points={'ovos.plugin.skill': PLUGIN_ENTRY_POINT}
)
