#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
from gi.repository import GLib
sys.path.append('../src')
from sn_param import SnParam
from sn_manager_config import SnConfigManager

param = SnParam()
cm = SnConfigManager(param)

