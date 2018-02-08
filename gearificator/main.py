"""Provide high level interface for gear creation
"""

import json
import os

from importlib import import_module
from collections import OrderedDict
from subprocess import Popen

from gearificator import __version__, get_logger
from gearificator.consts import (
    DOCKER_IMAGE_REPO,
    MANIFEST_FILENAME,
    MANIFEST_CUSTOM_SECTION,
    MANIFEST_CUSTOM_INTERFACE,
    MANIFEST_CUSTOM_OUTPUTS,
)
from gearificator.exceptions import UnknownBackend

from gearificator.run import load_interface_from_manifest
from gearificator.validator import validate_manifest

lgr = get_logger('main')
"""
        # # May be add a re-mapping of some fields
        # fields_mapping={
        #     'fixed_image': 'target_image',
        # },
        # # or even generalize it to provide needed augmentation
        # # so we could provide missing in nipype specs information
        # add_inputs={
        #     'target_image': {
        #         'original': 'fixed_image',
        #         'type': {'enum': ["nifti"]}
        #     }
        # },

"""
def create_gear(obj,
                outdir, manifest_fields={}, defaults={},
                build_docker=True,
                validate=True,
                deb_packages=[],
                pip_packages=[],
                source_files=[],
                dummy=False,
                ):
    """Given some obj, figure out which backend to use and create a gear in
    outdir

    Parameters
    ----------
    TODO
    dummy: bool, optional
      Generate a dummified dockerfile, which would not install any needed
      software.  To be used primarily for small uploads to troubleshoot
      web UI and our configuration settings
    """
    gear_spec = OrderedDict() # just to ease inspection etc, let's return the full structure

    # figure out backend
    backend_name = obj.__module__.split('.')[0]
    try:
        backend = import_module('gearificator.backends.%s' % backend_name)
    except ImportError as exc:
        raise UnknownBackend('Failed to import backend %s: %s' % (backend_name, exc))

    version = __version__ + (
        backend.get_version() if hasattr(backend, 'get_version') else ''
    ) + '.1'

    manifest, outputs = backend.extract_manifest(obj, defaults=defaults)
    if version:
        manifest['version'] = version
    manifest.update(manifest_fields)
    if dummy:
        for f in 'name', 'version':
            manifest[f] += '-dummy'
    name = manifest['name']
    # Filter out undefined which were added just for consistent order
    for f in manifest:
        if manifest[f] is None:
            manifest.pop(f)

    gear_spec['manifest'] = manifest
    # Store our custom settings
    if 'custom' not in manifest:
        manifest['custom'] = {}
    custom = manifest['custom']
    custom[MANIFEST_CUSTOM_SECTION] = {
        MANIFEST_CUSTOM_INTERFACE: '%s:%s' % (obj.__module__, obj.__name__),
        MANIFEST_CUSTOM_OUTPUTS: outputs or {}
    }

    # XXX it seems for an upload by gear-builder it must
    # reside (also?) in custom.gear-builder.image
    docker_image = custom.get('docker_image')
    if not docker_image:
        custom['docker-image'] = docker_image = \
            '%s:%s' % (name, version)
            #'%s/%s:%s' % (DOCKER_IMAGE_REPO, name, version)
    # to please gear-buidler -- duplicate for now
    custom['gear-builder'] = {'image': custom['docker-image']}

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Save manifest
    manifest_fname = os.path.join(outdir, MANIFEST_FILENAME)
    with open(manifest_fname, 'w') as f:
        json.dump(manifest, f, indent=2)
    if validate:
        validate_manifest(manifest_fname)

    # sanity check
    interface = load_interface_from_manifest(manifest_fname)
    assert interface is obj

    # TODO: create run
    gear_spec['run'] = create_run(
        os.path.join(outdir, 'run'),
        source_files=source_files,
    )

    # Create a dedicated Dockerfile
    gear_spec['Dockerfile'] = create_dockerfile(
        os.path.join(outdir, "Dockerfile"),
        base_image=getattr(backend, 'DOCKER_BASE_IMAGE', 'neurodebian'),
        deb_packages=getattr(backend, 'DEB_PACKAGES', []),
        extra_deb_packages=deb_packages,
        pip_packages=getattr(backend, 'PIP_PACKAGES', []) + pip_packages,
        dummy=dummy
    )

    if build_docker:
        # TODO: docker build -t image_name
        lgr.info("Running docker build")
        build_cmd = ['docker', 'build', '-t', docker_image, '.']
        print(build_cmd)
        popen = Popen(build_cmd, cwd=outdir)
        res = popen.wait()
        if res:
            raise RuntimeError(
                "Failed to build docker image: exit code was %d"
                % res
            )
        gear_spec['docker_build_stdout'] = 'TODO'
        gear_spec['docker_build_stderr'] = 'TODO'
    return gear_spec


def create_dockerfile(
        fname,
        base_image,
        deb_packages=[], extra_deb_packages=[], pip_packages=[],
        dummy=False
    ):
    """Create a Dockerfile for the gear

    ATM we aren't bothering establishing a common base image. So will rebuild
    entire spec
    """

    deb_packages_line = ' '.join(deb_packages) if deb_packages else ''
    extra_deb_packages_line = 'RUN eatmydata apt-get install -y --no-install-recommends ' \
                               + ' '.join(extra_deb_packages)  if extra_deb_packages else ''
    pip_line = "RUN pip install %s" % (' '.join(pip_packages)) if pip_packages else ''

    if dummy:
        base_image = 'busybox:latest'

    template = """\
FROM %(base_image)s
MAINTAINER Yaroslav O. Halchenko <debian@onerussian.com>
    """
    if not dummy:
        template += """
# TODO: use snapshots for reproducible image!
# Install additional APT mirror for NeuroDebian for better availability/resilience
RUN echo deb http://neurodeb.pirsquared.org data main contrib non-free >> /etc/apt/sources.list.d/neurodebian.sources.list
RUN echo deb http://neurodeb.pirsquared.org stretch main contrib non-free >> /etc/apt/sources.list.d/neurodebian.sources.list

# To prevent interactive debconf during installations
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \\
    apt-get install -y eatmydata

# Make directory for flywheel spec (v0)
# TODO:  gearificator prepare-docker recipename_or_url
# cons: would somewhat loose cached steps (pre-installation, etc)
# For now -- entire manual template
RUN eatmydata apt-get update && \\
    eatmydata apt-get install -y --no-install-recommends python-pip %(deb_packages_line)s

# Download/Install gearificator suite
# TODO  install git if we do via git
RUN eatmydata apt-get install -y git python-setuptools
RUN git clone git://github.com/yarikoptic/gearificator /srv/gearificator && echo "4"
RUN pip install -e /srv/gearificator
"""
    template += """
# Common to all gears settings
ENV FLYWHEEL /flywheel/v0
RUN mkdir -p ${FLYWHEEL}

# e.g. Nipype and other pythonish beasts might crash unless 
ENV LC_ALL C.UTF-8
"""
    if not dummy:
        template += """
# Now we do this particular Gear specific installations
%(extra_deb_packages_line)s
RUN apt-get clean
%(pip_line)s
    """
    template += """
COPY run ${FLYWHEEL}/run
COPY manifest.json ${FLYWHEEL}/manifest.json

# Configure entrypoint
ENTRYPOINT ["/flywheel/v0/run"]
"""
    content = template % locals()
    with open(fname, "w") as f:
        f.write(content)
    return content


def create_run(fname, source_files):
    """Create the mighty "run" file which would be exactly the same in all of them
    """
    content = """\
#!/bin/sh
# Just a simple runner for the gearificator'ed interface.
#
# All needed information should be specified via manifest.conf and config.json 

set -eu
"""
    if source_files:
        for f in source_files:
            content += '. %s\n' % f

    # Finally actually run the thing
    content += "python -m gearificator \"$@\"\n"
    with open(fname, 'w') as f:
        f.write(content)
    # make it executable
    os.chmod(fname, 0o755)
    return content