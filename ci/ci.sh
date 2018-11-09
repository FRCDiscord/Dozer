#!/bin/sh
pylint dozer > ./ci/cilog.txt
cat ./ci/cilog.txt
python3 ./ci/ci.py

