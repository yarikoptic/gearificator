# Generator of Flywheel Gears 


![gearificator logo](doc/images/gearificator-logo.png)

Currently intends to provide gearification of some interfaces and
pipelines provided by Nipype 

Q&D HOWTO ATM
-------------


     rm -rf /tmp/outputs; gearificator --pdb -l 20 --run-tests native --gear spec /tmp/outputs

ATM will load   gearificator/specs/nipype/__init__.py  and populate /tmp/outputs

Another useful option is --regex to limit to which gears to generate

TODOs
-----

Lots of TODOs, but primary target(s):
- nipype
  - [ ] ANTs interfaces

LICENSE
-------
Some initial code is borrowed from Gearificator
http://github.com/uwescience/gearificator
MIT licensed
