#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""Utilities for gear creation/management
"""

import json
import os
import shutil
import subprocess
import tempfile

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
from gearificator.run import load_interface_from_manifest, get_manifest
from gearificator.validator import validate_manifest

lgr = get_logger('gear')


def subprocess_call(cmd, cwd=None, logsdir=None, env=None):
    """A helper to run a command, under cwd and logs stored under logsdir

    Returns stdout, stderr
    """
    if not logsdir:
        logsdir = tempfile.mkdtemp(prefix="gearificator")
        delete_logs = True
    else:
        delete_logs = False

    try:
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
    finally:
        pass
    if exit_code:
        # TODO: make custom one to return outs
        raise RuntimeError(
            "Running %s under %s failed. Exit: %d. See %s"
            % (" ".join(map(
                    lambda x: "'%s'" % x, cmd))  # to avoid u''
               if isinstance(cmd, (list, tuple)) else cmd,
               cwd, exit_code, log_stderr_path))
    else:
        # delete logs only if clear since otherwise nothing to inspect above
        if delete_logs:
            shutil.rmtree(logsdir)

    lgr.debug(" finished running with out=%s err=%s", *outs)
    return outs


def run_gear_native(gearpath, testdir):
    # if we run natively, we have to copy manifest for the gear
    for f in [GEAR_RUN_FILENAME, GEAR_MANIFEST_FILENAME]:
        shutil.copy(op.join(gearpath, f), testdir)
    #logsdir = op.join(testdir, '.gearificator', 'logs')
    logsdir = op.join(testdir, 'logs')
    outs = subprocess_call(
        './run',
        cwd=testdir,
        logsdir=logsdir,
        env=dict(os.environ, FLYWHEEL='.'))  # op.abspath(testdir)),)
    return outs


def run_gear_docker(dockerimage, testdir):
    # copy/paste largely for now to RF later TODO
    logsdir = op.join(testdir, 'logs')  # common

    def _m(s):
        return ["-v", "%s/%s:%s/%s"
                % (op.realpath(testdir), s, GEAR_FLYWHEEL_DIR, s)]

    outs = subprocess_call(
        ['docker', 'run', '--rm']
        + sum(map(_m, [GEAR_INPUTS_DIR, GEAR_OUTPUT_DIR, GEAR_CONFIG_FILENAME]), [])
        + [dockerimage],
        cwd=testdir,
        logsdir=logsdir,
        env=dict(os.environ, FLYWHEEL='.')
    )
    return outs


def build_gear(buildir, docker_image):
    lgr.info("Building gear docker image %s", docker_image)
    if len(docker_image) > 128:
        raise ValueError("too long (%d) tag: %s" % len(docker_image), docker_image)
    return subprocess_call(
        ['docker', 'build', '-t', docker_image, '.'],
        cwd=buildir,
    )


def docker_push_gear(docker_image):
    lgr.info("Pushing gear docker image %s", docker_image)
    return subprocess_call(
        ['docker', 'push', docker_image]
    )


def fw_upload_gear(geardir):
    lgr.info("fw gear upload %s", geardir)
    return subprocess_call(
            ['fw', 'gear', 'upload'],
            cwd=geardir,
    )


def copy_to_exchange(geardir, exchangedir):
    """

    Parameters
    ----------
    geardir
    exchangedir

    Returns
    -------

    """
    outpath = op.normpath(op.join(exchangedir, 'gears', 'gearificator'))
    if not op.exists(outpath):
        os.mkdir(outpath)
    manifestpath = op.join(geardir, GEAR_MANIFEST_FILENAME)
    manifest = get_manifest(manifestpath)
    outname = op.join(outpath, '%(name)s.json' % manifest)
    lgr.info("Copying manifest into %s", outname)
    shutil.copy(manifestpath, outname)


def create_gear(obj,
                outdir,
                manifest_fields={}, defaults={},
                build_docker=True,
                validate=True,
                deb_packages=[],
                pip_packages=[],
                source_files=[],
                prepend_paths=[],
                envvars={},
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
    ) + '.3'

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
            'gearificator/%s:%s' % (name, version)
            #'%s/%s:%s' % (DOCKER_IMAGE_REPO, name, version)
    # to please gear-buidler -- duplicate for now
    custom['gear-builder'] = {'image': custom['docker-image']}

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    if 'label' not in manifest:
        manifest['label'] = getattr(obj, '__name__')

    # Save manifest
    manifest_fname = os.path.join(outdir, GEAR_MANIFEST_FILENAME)
    save_manifest(manifest, manifest_fname)

    if validate:
        validate_manifest(manifest_fname)

    # sanity check
    interface = load_interface_from_manifest(manifest_fname)
    assert interface is obj

    # TODO: create run
    gear_spec['run'] = create_run(
        os.path.join(outdir, 'run'),
        source_files=source_files,
        prepend_paths=prepend_paths,
        envvars=envvars
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

    if hasattr(backend, 'get_suite'):
        custom["flywheel"] = {
            "suite": backend.get_suite(obj, docker_image)
        }
        # and we resave it again, so inside gear docker it might actually differ
        # unfortunately, but shouldn't matter I guess
        save_manifest(manifest, manifest_fname)

    return gear_spec


def save_manifest(manifest, manifest_fname):
    with open(manifest_fname, 'w') as f:
        json.dump(manifest, f, indent=2, separators=(',', ': '))


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

    # to minimize image layers size
    cleanup_cmd = "rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*"

    deb_packages_line = ' '.join(deb_packages) if deb_packages else ''
    extra_deb_packages_str = (' '.join(extra_deb_packages) if extra_deb_packages else '')
    extra_deb_packages_line = """
RUN apt-get update \\ 
    && apt-get install -y --no-install-recommends %(extra_deb_packages_str)s \\
    && %(cleanup_cmd)s
""" % locals()
    pip_packages_str = ' '.join(pip_packages) if pip_packages else ''
    pip_line = "RUN pip install %(pip_packages_str)s && %(cleanup_cmd)s" \
            % locals()

    if dummy:
        base_image = 'busybox:latest'

    template = """\
FROM %(base_image)s
MAINTAINER Yaroslav O. Halchenko <debian@onerussian.com>
    """
    if not dummy:
        if base_image.startswith('neurodebian:'):
            template += """
# Make image reproducible based on the date/state of things in Debian/NeuroDebian
# land.
# Time format yyyymmdd 
RUN nd_freeze 20181221
"""
        else:
            raise NotImplementedError(
                "Did not bother implementing support for freeze for "
                "non-neurodebian base images")
            # Also below removed eatmydata since now by default is used for
            # apt-get on neurodebian images
# Not doing it since now using nd_freeze, no mirrors
#         template += """
# # Install additional APT mirror for NeuroDebian for better availability/resilience
# RUN echo deb http://neurodeb.pirsquared.org data main contrib non-free >> /etc/apt/sources.list.d/neurodebian.sources.list
# RUN echo deb http://neurodeb.pirsquared.org stretch main contrib non-free >> /etc/apt/sources.list.d/neurodebian.sources.list
# """
        template += """
# To prevent interactive debconf during installations
ARG DEBIAN_FRONTEND=noninteractive

# Make directory for flywheel spec (v0)
# TODO:  gearificator prepare-docker recipename_or_url
# cons: would somewhat loose cached steps (pre-installation, etc)
# For now -- entire manual template
RUN apt-get update && echo "count 1" \\
    && apt-get install -y --no-install-recommends python-pip %(deb_packages_line)s \\
    && %(cleanup_cmd)s

# Download/Install gearificator suite
# TODO  install git if we do via git
RUN apt-get update \\ 
    && apt-get install -y git python-setuptools \\
    && %(cleanup_cmd)s
# TEMPMOVE RUN git clone git://github.com/yarikoptic/gearificator /srv/gearificator && echo 7
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
%(pip_line)s
    """

        # TEMP do it here for now since it is volatile
        template += """
RUN git clone git://github.com/yarikoptic/gearificator /srv/gearificator && echo 7
RUN pip install -e /srv/gearificator && %(cleanup_cmd)s
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


def create_run(fname, source_files, prepend_paths=None, envvars={}):
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

    if prepend_paths:
        content += 'export PATH=%s:$PATH\n' % (':'.join(prepend_paths))
    if envvars:
        for var in envvars.items():
            content += 'export %s=%s\n' % var
    # Finally actually run the thing
    content += "python -m gearificator \"$@\"\n"
    with open(fname, 'w') as f:
        f.write(content)
    # make it executable
    os.chmod(fname, 0o755)
    return content
