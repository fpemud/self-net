#!/bin/bash

FILES="./selfnetd ./selfnetctl"
FILES="${FILES} $(find ./lib -name '*.py' | tr '\n' ' ')"
FILES="${FILES} $(find ./libexec -name '*.py' | tr '\n' ' ')"
FILES="${FILES} $(find ./modules -name '*.py' | tr '\n' ' ')"

autopep8 -ia --ignore=E501,E265,W191 ${FILES}
