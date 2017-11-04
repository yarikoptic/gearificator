import os
from os.path import join as opj

from gearificator.run import load_interface_from_manifest
from gearificator.main import create_gear


def test_ants(tmpdir):
    from nipype.interfaces.ants.registration import ANTS, Registration
    from pprint import pprint
    import json

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
