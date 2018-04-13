# Generator of Flywheel Gears 


![gearificator logo](doc/images/gearificator-logo.png)
[![Build Status](https://travis-ci.org/yarikoptic/gearificator.svg?branch=master)](https://travis-ci.org/yarikoptic/gearificator)
[![codecov.io](https://codecov.io/github/yarikoptic/gearificator/coverage.svg?branch=master)](https://codecov.io/github/yarikoptic/gearificator?branch=master)

Currently intends to provide gearification of some interfaces and
pipelines provided by Nipype 

Q&D HOWTO ATM
-------------

     git clone git://github.com/yarikoptic/gearificated-nipype
     gearificator spec process --run-tests gear --gear build gearificated-nipype

which should produce identical (to what already there) results (you could use
`git -C gearificated-nipype status` to check).  Also the outputs of the test runs
will be placed under `gearificated-nipype/tests-run`

`spec process` has a number of useful option such as --regex to limit to
which gears to generate

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
