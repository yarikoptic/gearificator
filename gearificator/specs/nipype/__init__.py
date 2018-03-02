
# Should we just list where we want to dig for interfaces
# and provide adjustments for different levels? e.g.

from nipype.interfaces.base import BaseInterface

# may be we would like helpers for explicit semantic?
# may be not -- should generally be incremental for lists.
# We could demarkate as
#def _add(v2):
#    return lambda v1: v1+v2


def robust_issubclass(C, A):
    try:
        return issubclass(C, A)
    except Exception:
        # doesn't like comparing different types
        return False


spec = {
    # params to pass into create_gear
    # TODO: this should be common to all, move out and inherit
    ## manifest_fields
    "%manifest": {
        "author": "Yaroslav O. Halchenko",
        "license": "BSD-3-Clause",
        "maintainer": "Yaroslav O. Halchenko <debian@onerussian.com>",
        "source": "https://github.com/yarikoptic/gearificator",
        # not supported yet, we might want to add custom. prefix or smth like
        # that
        "category": "analysis"
    },
    "%params": {
        "base_image": "neurodebian:stable",
    },
    ## other options to `create_gear`
    # "%params": []
    ## options for traversal
    # "%recurse": False,  # either to recurse into submodules to find new interfaces
    # "%exclude": None,
    # "%include": None, # callable to decide if attribute is what we need
    # "%exclude": None, # callable to run after exclude to decide possibly to exclude some items
    # point to what sub-items (refining/inheriting down)
    "nipype.interfaces": {
        # What classes to react to. might want a callable
        "%include": lambda x: robust_issubclass(x, BaseInterface),
        "%params": {
            "deb_packages": ["python-nipype"],
        },

        "ants.registration": {
            "%params": {
                # None as the first to say that we need to override
                "deb_packages": ["ants"],
            },
            "ANTS": {
                "%params": {
                    "defaults": dict(
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
                }
            }
        },

        "fsl": {
            "%manifest": {
                "license": "Other"
            },
            "%params": {
                # None as the first to say that we need to override
                "deb_packages": ["fsl-core"],
                # "pip_packages": []
                "source_files": ["/etc/fsl/fsl.sh"],
                "defaults": {
                    "output_type": "NIFTI_GZ",
                },
            },
            "preprocess": {
                "%recurse": True,
                # "%exclude": None,
                # "items": {}
                "BET": {
                    "%manifest": {
                        # Just an example for override
                        "label": "FSL BET (Brain Extraction Tool)"
                    }
                },
                # we could add fancy path selectors we could do smth like
                # "{}.%manifest.label": {
                #    "BET": "FSL BET ....",
                #    "FLIRT": " ....
                # },
            },
        },

        "dcm2nii": {
            "%recurse": True,
            "%params": {
                # None as the first to say that we need to override
                "deb_packages": ["mricron", "dcm2niix"],
            },
        },
    },
}
