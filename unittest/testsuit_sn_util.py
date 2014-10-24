#!/usr/bin/env python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import unittest
from sn_util import SnUtil


class Test_getUidGidMinMaxInfo(unittest.TestCase):

    def runTest(self):
        SnUtil.getUidGidMinMaxInfo()


class Test_getNormalUserList(unittest.TestCase):

    def runTest(self):
        SnUtil.getNormalUserList()
