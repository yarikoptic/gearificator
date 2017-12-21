import json
import os
from os.path import join as opj
from pprint import pprint

from gearificator.run import load_interface_from_manifest
from gearificator.main import create_gear
from gearificator.utils import chpwd


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


def test_ants(tmpdir):
    from nipype.interfaces.ants.registration import ANTS, Registration

    tmpdir = '/tmp/gearificator_output'
    #geardir = str(tmpdir)
    geardir = opj(tmpdir, 'gear')
    indir = opj(tmpdir, 'inputs')
    outdir = opj(tmpdir, 'outputs')

    print("output dir: %s" % tmpdir)
    ants_class = ANTS
    gear_spec = create_gear(
        ants_class,
        geardir,
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
            name="nipype-ants-ants",
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
        build_docker=False
    )
    print(json.dumps(gear_spec, indent=2))

    manifest_file = opj(geardir, 'manifest.json')
    interface = load_interface_from_manifest(manifest_file)
    assert interface is ants_class

    from gearificator.run import get_interface
    config = {
        'fixed_image': opj(indir, "fixed.nii.gz"),
        'moving_image': opj(indir, "moving.nii.gz"),
    }
    interface = get_interface(manifest_file, config, indir, outdir)
    cmdline = interface.cmdline
    print(cmdline)
    assert "undefined" not in cmdline
    assert cmdline == \
"ANTS 3 --image-metric CC[ %(fixed_image)s, %(moving_image)s, 1, 1 ] " \
"--number-of-affine-iterations 10000x10000x10000x10000x10000 " \
"--number-of-iterations 50x35x15 --output-naming out " \
"--regularization Gauss[3.0,0.0] --transformation-model SyN " \
"--use-Histogram-Matching 0" % config


def test_fsl_bet(tmpdir):
    from nipype.interfaces.fsl.preprocess import BET

    tmpdir = '/tmp/gearificator_output'
    if os.path.exists(tmpdir):
        import shutil
        shutil.rmtree(tmpdir)
    #geardir = str(tmpdir)
    geardir = tmpdir
    indir = opj(tmpdir, 'inputs')
    outdir = opj(tmpdir, 'outputs')
    for d in geardir, indir, outdir:
        if not os.path.exists(d):
            os.makedirs(d)

    print("output dir: %s" % tmpdir)
    class_ = BET
    gear_spec = create_gear(
        class_,
        geardir,
        # Additional fields for the
        manifest_fields=dict(
            author="Yaroslav O. Halchenko",
            license='Other',  # BSD-3-Clause + FSL license (non-commercial)',
            maintainer="Yaroslav O. Halchenko <debian@onerussian.com>",
            # name="nipype-fsl-bet",
            label="FSL BET (Brain Extraction Tool)",
            source="https://github.com/yarikoptic/gearificator",  # URL to the gearificator? or we will publish a generated collection somewhere?
        ),
        defaults=dict(
            output_type='NIFTI_GZ',
        ),
        deb_packages=['fsl-core'],
        source_files=['/etc/fsl/fsl.sh'],
        build_docker=False
    )
    #print(json.dumps(gear_spec, indent=2))

    manifest_file = opj(geardir, 'manifest.json')
    interface = load_interface_from_manifest(manifest_file)
    assert interface is class_

    from gearificator.run import get_interface

    config = create_config(geardir,
        in_file = opj(indir, "in_file", "fixed.nii.gz"),
        # "cheating" -- the problem is that
        # nipype would operate from cwd while composing the output
        # filename if not specified, so in run we actually can do that
        # but can't do here since output dir does not necessarily exist
        out_file=opj(outdir, "fixed_BRAIN.nii.gz"),
        skull=True,
    )
    create_sample_nifti(config['in_file'])
    interface = get_interface(manifest_file, config, indir, outdir)
    cmdline = interface.cmdline
    assert "undefined" not in cmdline
    assert cmdline == "bet %(in_file)s %(out_file)s -s" \
           % (config)

    config.pop('out_file')
    with chpwd(outdir):
        interface = get_interface(manifest_file, config, indir, outdir)
        cmdline = interface.cmdline
        assert "undefined" not in cmdline
        assert cmdline == "bet %s %s -s" \
               % (config['in_file'], opj(outdir, "fixed_brain.nii.gz"))
