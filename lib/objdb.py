#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import pickle


class objdb:
	
    def __init__(self, filename):
        self.filename = filename
        self.newfilename = filename + ".new"

        if os.path.exists(self.filename):
            if os.stat(self.filename).st_size > 0:
                with open(self.filename, "rb") as f:
                    self.obj = pickle.load(f)
            else:
                self.obj = None
        else:
            with open(self.filename, "wb"):
                pass
            self.obj = None
            
        assert not os.path.exists(self.newfilename)

    def get_object(self):
        return self.obj

    def set_object(self, obj):
        self.obj = obj

    def persist(self):
        with open(self.newfilename, "wb") as f:
            pickle.dump(self.obj, f)
        os.rename(self.newfilename, self.filename)