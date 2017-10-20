import os
from os.path import join as opj

from gearificator.run import load_interface_from_manifest
from gearificator.main import create_gear

def test_ants(tmpdir):
    from nipype.interfaces.ants.registration import ANTS, Registration
    from pprint import pprint
    import json

    outdir = '/tmp/gearificator_output'
    #outdir = str(tmpdir)

    print("output dir: %s" % outdir)
    gear_spec = create_gear(
        ANTS,
        outdir,
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
        defaults={
            'transformation_model': 'SyN',
            'dimension': 3,
            'metric': ['CC'],
        }
    )
    print(json.dumps(gear_spec, indent=2))

    interface = load_interface_from_manifest(opj(outdir, 'manifest.json'))
    assert interface is ANTS