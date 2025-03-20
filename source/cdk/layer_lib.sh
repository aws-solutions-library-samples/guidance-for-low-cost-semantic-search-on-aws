#!/bin/sh
rm -rf lib
for d in src/lambda/*/ ; do
    pip3 install -r $d/requirements.txt --target=./lib/$d/python
    echo "$d"
done
