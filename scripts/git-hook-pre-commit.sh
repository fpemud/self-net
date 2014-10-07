#!/bin/bash

FILES="./selfnetd ./selfnetctl $(find . -name '*.py' | tr '\n' ' ')"
ERRFLAG=0

OUTPUT=`pyflakes ${FILES} 2>&1`
if [ -n "$OUTPUT" ] ; then
    echo "pyflake errors:"
    echo "$OUTPUT"
    echo ""
    ERRFLAG=1
fi

OUTPUT=`pep8 ${FILES} | grep -Ev "E501|W191"`
if [ -n "$OUTPUT" ] ; then
    echo "pep8 errors:"
    echo "$OUTPUT"
    echo ""
    ERRFLAG=1
fi

#OUTPUT=`unittest/autotest.py 2>&1`
#if [ "$?" == 1 ] ; then
#    echo "unittest errors:"
#    echo "$OUTPUT"
#    echo ""
#    ERRFLAG=1
#fi

if [ "${ERRFLAG}" == 1 ] ; then
    exit 1
fi
