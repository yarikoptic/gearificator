#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""Utilities for gear creation/management
"""

import json
import os
import shutil
import subprocess
from collections import OrderedDict
from importlib import import_module
from os import path as op
from subprocess import Popen

from gearificator import __version__, get_logger
from gearificator.consts import (
    GEAR_FLYWHEEL_DIR,
    GEAR_RUN_FILENAME, GEAR_MANIFEST_FILENAME,
    MANIFEST_CUSTOM_SECTION, MANIFEST_CUSTOM_INTERFACE, MANIFEST_CUSTOM_OUTPUTS,
    GEAR_INPUTS_DIR, GEAR_OUTPUT_DIR, GEAR_CONFIG_FILENAME,
)
from gearificator.exceptions import UnknownBackend
from gearificator.run import load_interface_from_manifest
from gearificator.validator import validate_manifest

lgr = get_logger('gear')


def subprocess_call(cmd, cwd=None, logsdir=None, env=None):
    """A helper to run a command, under cwd and logs stored under logsdir

    Returns stdout, stderr
    """
    # TODO: if not logsdir - make tempdir
    if not op.exists(logsdir):
        os.makedirs(logsdir)
    # now just execute that gear in the directory
    log_stdout_path = op.join(logsdir, 'out')
    log_stderr_path = op.join(logsdir, 'err')
    with open(log_stdout_path, 'w') as log_stdout, \
            open(log_stderr_path, 'w') as log_stderr:
        lgr.debug("Running %s", cmd)
        exit_code = subprocess.call(
            cmd,
            stdin=subprocess.PIPE,
            stdout=log_stdout,
            stderr=log_stderr,
            env=env,
            cwd=cwd
        )
    outs = [
        open(f).read() for f in [log_stdout_path, log_stderr_path]
    ]
    if exit_code:
        # TODO: make custom one to return outs
        raise RuntimeError(
            "Running %s under %s failed. Exit: %d. See %s"
            % (" ".join(map(
                    lambda x: "'%s'" % x, cmd))  # to avoid u''
               if isinstance(cmd, (list, tuple)) else cmd,
               cwd, exit_code, log_stderr_path))
    lgr.debug(" finished running with out=%s err=%s", *outs)
    return outs


def run_gear_native(gearpath, testdir):
    # if we run natively, we have to copy manifest for the gear
    for f in [GEAR_RUN_FILENAME, GEAR_MANIFEST_FILENAME]:
        shutil.copy(op.join(gearpath, f), testdir)
    #logsdir = op.join(testdir, '.gearificator', 'logs')
    logsdir = op.join(testdir, 'logs')
    outs = subprocess_call(
        './run', cwd=testdir, logsdir=logsdir,
        env=dict(os.environ, FLYWHEEL='.'))  # op.abspath(testdir)),)
    return outs


def run_gear_docker(dockerimage, testdir):
    # copy/paste largely for now to RF later TODO
    logsdir = op.join(testdir, 'logs')  # common

    def _m(s):
        return ["-v", "%s/%s:%s/%s" % (testdir, s, GEAR_FLYWHEEL_DIR, s)]

    outs = subprocess_call(
        ['docker', 'run', '--rm']
        + [_m(s) for s in [GEAR_INPUTS_DIR, GEAR_OUTPUT_DIR, GEAR_CONFIG_FILENAME]]
        + [dockerimage],
        cwd=testdir,
        logsdir=logsdir,
        env=dict(os.environ, FLYWHEEL='.')
    )
    return outs


def create_gear(obj,
                outdir,
                manifest_fields={}, defaults={},
                build_docker=True,
                validate=True,
                deb_packages=[],
                pip_packages=[],
                source_files=[],
                dummy=False,
                base_image=None,
                # TODO:
                # category="analysis" # or "converter"
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
    lgr.info("Creating gear for %s", obj)
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

    # category is not part of the manifest (yet) so we will pass it into custom
    if 'category' in manifest:
        custom[MANIFEST_CUSTOM_SECTION]['category'] = manifest.pop('category')

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

    if 'label' not in manifest:
        manifest['label'] = getattr(obj, '__name__')

    # Save manifest
    manifest_fname = os.path.join(outdir, GEAR_MANIFEST_FILENAME)
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
        base_image=base_image or getattr(backend, 'DOCKER_BASE_IMAGE', 'neurodebian'),
        deb_packages=getattr(backend, 'DEB_PACKAGES', []),
        extra_deb_packages=deb_packages,
        pip_packages=getattr(backend, 'PIP_PACKAGES', []) + pip_packages,
        dummy=dummy
    )

    gear_spec['docker_image'] = docker_image
    if build_docker:
        out, err = build_gear(outdir, docker_image)
        gear_spec['docker_build_stdout'] = out
        gear_spec['docker_build_stderr'] = err
    return gear_spec


def build_gear(buildir, docker_image):
    # TODO: docker build -t image_name
    lgr.info("Running docker build")
    build_cmd = ['docker', 'build', '-t', docker_image, '.']
    print(build_cmd)
    popen = Popen(build_cmd, cwd=buildir)
    res = popen.wait()
    if res:
        raise RuntimeError(
            "Failed to build docker image: exit code was %d"
            % res
        )
    return "TODO stdout", "TODO stderr"


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
# TEMPMOVE RUN git clone git://github.com/yarikoptic/gearificator /srv/gearificator && echo "6"
# TEMPMOVE RUN pip install -e /srv/gearificator
"""
    template += """
# Common to all gears settings
ENV FLYWHEEL %s
RUN mkdir -p ${FLYWHEEL}

# e.g. Nipype and other pythonish beasts might crash unless 
ENV LC_ALL C.UTF-8
""" % GEAR_FLYWHEEL_DIR

    if not dummy:
        template += """
# Now we do this particular Gear specific installations
%(extra_deb_packages_line)s
RUN apt-get clean
%(pip_line)s
    """
    # TEMP do it here for now since it is volatile
    template += """
RUN git clone git://github.com/yarikoptic/gearificator /srv/gearificator && echo "6"
RUN pip install -e /srv/gearificator

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