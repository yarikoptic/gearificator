from ..nipype import extract


def test_ants():
    from nipype.interfaces.ants.registration import ANTS
    from pprint import pprint
    import json
    #pprint(extract(ANTS))
    print(json.dumps(extract(ANTS), indent=2))