import json
import os
from os.path import join as opj
from pprint import pprint

from gearificator.run import load_interface_from_manifest
from gearificator.main import create_gear
from gearificator.utils import chpwd

from pytest import fixture


def create_sample_nifti(fname, shape=(32, 32, 32), affine=None):
    import nibabel as nib
    import numpy as np
    if not affine:
        affine = np.eye(len(shape)+1) * 3  # a simple one
        affine[-1, -1] = 1
    ni = nib.Nifti1Image(np.random.normal(1000, 1000, shape), affine)
    dirname = os.path.dirname(fname)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    ni.to_filename(fname)
    return ni


def create_config(filename, **config):
    import json
    out_config = {'config': config}
    with open(opj(filename, 'config.json'), 'w') as f:
        json.dump(out_config, f, indent=2)
    return config


@fixture
def geardir(tmpdir):
    """A fixture to create a tempdir for a gear

    with all critical sub paths provided as attributes
    """
    from gearificator.consts import \
        GEAR_INPUTS_DIR, GEAR_OUTPUT_DIR, GEAR_MANIFEST_FILENAME
    indir = tmpdir.join(GEAR_INPUTS_DIR)
    outdir = tmpdir.join(GEAR_OUTPUT_DIR)
    for d in tmpdir, indir, outdir:
        if not os.path.exists(str(d)):
            os.makedirs(str(d))
    # print("output dir: %s" % tmpdir)
    tmpdir.inputs = str(indir)
    tmpdir.outputs = str(outdir)
    tmpdir.manifest = str(tmpdir.join(GEAR_MANIFEST_FILENAME))
    return tmpdir


def test_ants(geardir):
    from nipype.interfaces.ants.registration import ANTS, Registration

    ants_class = ANTS  # Registration is tougher -- TODO
    gear_spec = create_gear(
        ants_class,
        str(geardir),
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
        # Additional fields for the
        manifest_fields=dict(
            author="The Machine",
            description="Registration using ANTS from ANTs toolkit",
            label="ANTs ANTS",
            license='BSD-3-Clause',
            maintainer="You?",
            name="nipype-ants-registration",
            source="",  # URL to the gearificator? or we will publish a generated collection somewhere?
            url="",  # TODO automagically based on nipype docs",
        ),
        # Provide some sensible defaults for some options even though nipype
        # does not
        defaults=dict(
            transformation_model='SyN',
            # output_transform_prefix='/tmp/MY',
            dimension=3,
            metric=['CC'],
            metric_weight=[1.0],
            # following ones are somewhat too detailed...
            radius=[1],
            regularization='Gauss',
            regularization_gradient_field_sigma=3,
            regularization_deformation_field_sigma=0,
            # and for fun
            number_of_iterations=[50, 35, 15],
            number_of_affine_iterations=[10000, 10000, 10000, 10000, 10000],
        ),
        deb_packages=['ants'],
        build_docker=False
    )

    interface = load_interface_from_manifest(geardir.manifest)
    assert interface is ants_class

    from gearificator.run import get_interface
    indir = str(geardir.inputs)
    outdir = str(geardir.outputs)
    config = {
        'fixed_image': opj(indir, "fixed.nii.gz"),
        'moving_image': opj(indir, "moving.nii.gz"),
    }
    # we need to precreate it since it does validation
    for f in config.values():
        with open(f, 'w'):
            pass

    interface = get_interface(geardir.manifest, config, indir, outdir)
    cmdline = interface.cmdline
    print(cmdline)
    assert "undefined" not in cmdline
    assert cmdline == \
"ANTS 3 --image-metric CC[ %(fixed_image)s, %(moving_image)s, 1, 1 ] " \
"--number-of-affine-iterations 10000x10000x10000x10000x10000 " \
"--number-of-iterations 50x35x15 --output-naming out " \
"--regularization Gauss[3.0,0.0] --transformation-model SyN " \
"--use-Histogram-Matching 0" % config


def test_fsl_bet(geardir):
    from nipype.interfaces.fsl import preprocess

    # for local testing
    # tmpdir = '/tmp/gearificator_output'
    # if os.path.exists(tmpdir):
    #     import shutil
    #     shutil.rmtree(tmpdir)
    class_ = preprocess.BET
    #class_ = preprocess.MCFLIRT
    gear_spec = create_gear(
        class_,
        str(geardir),
        # Additional fields for the
        manifest_fields=dict(
            author="Yaroslav O. Halchenko",
            license='Other',  # BSD-3-Clause + FSL license (non-commercial)',
            maintainer="Yaroslav O. Halchenko <debian@onerussian.com>",
            # name="nipype-fsl-bet",
            label="FSL BET (Brain Extraction Tool)",
            #label="FSL MCFLIRT (Motion Correction for fMRI)",
            source="https://github.com/yarikoptic/gearificator",  # URL to the gearificator? or we will publish a generated collection somewhere?
        ),
        defaults=dict(
            output_type='NIFTI_GZ',
        ),
        deb_packages=['fsl-core'],
        source_files=['/etc/fsl/fsl.sh'],
        build_docker=False,
        dummy=True
    )
    #print(json.dumps(gear_spec, indent=2))
    assert isinstance(gear_spec, dict)

    interface = load_interface_from_manifest(geardir.manifest)
    assert interface is class_

    from gearificator.run import get_interface

    config = create_config(
        str(geardir),
        in_file=str(geardir.join("in_file", "fixed.nii.gz")),
        # "cheating" -- the problem is that
        # nipype would operate from cwd while composing the output
        # filename if not specified, so in run we actually can do that
        # but can't do here since output dir does not necessarily exist
        out_file=opj(str(geardir.outputs), "fixed_BRAIN.nii.gz"),
        skull=True,
    )
    create_sample_nifti(config['in_file'])
    interface_args = (geardir.manifest, config, geardir.inputs, geardir.outputs)
    interface = get_interface(*interface_args)
    cmdline = interface.cmdline
    assert "undefined" not in cmdline
    assert cmdline == "bet %(in_file)s %(out_file)s -s" \
           % (config)

    config.pop('out_file')
    with chpwd(geardir.outputs):
        interface = get_interface(*interface_args)
        cmdline = interface.cmdline
        assert "undefined" not in cmdline
        assert cmdline == "bet %s %s -s" \
               % (config['in_file'], opj(geardir.outputs, "fixed_brain.nii.gz"))
