#!/usr/bin/env python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import shutil
import unittest

curDir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(curDir, "../lib"))

import testsuit_sn_util


def suite():
    suite = unittest.TestSuite()
    suite.addTest(testsuit_sn_util.Test_getUidGidMinMaxInfo())
    suite.addTest(testsuit_sn_util.Test_getNormalUserList())
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest='suite')
