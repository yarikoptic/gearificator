from ..nipype import (
    extract_manifest,
    prepare_dockerfile,
    prepare_run,
)

from gearificator.runtime.base import get_interface

def test_ants(tmpdir):
    from nipype.interfaces.ants.registration import ANTS, Registration
    from pprint import pprint
    import json
    #pprint(extract_manifest(ANTS))
    manifest = extract_manifest(
        ANTS,
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
        author="The Machine",
        description="Registration using ANTS from ANTs",
        label="Some label",
        license="Some license",
        maintainer="You?",
        name="nipype-ants-ANTS",
        source="TODO",
        url="TODO automagically based on nipype docs",
        version="0.0.automagicbasedongitifnotdefined"
    )
    #manifest = extract_manifest(Registration)
    manifest_fname = str(tmpdir.join('manifest.json'))
    with open(manifest_fname, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(manifest_fname)

    interface = get_interface(manifest_fname)
    assert interface is ANTS