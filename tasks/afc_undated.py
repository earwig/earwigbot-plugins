# -*- coding: utf-8  -*-
#
# Copyright (C) 2009-2013 Ben Kurtovic <ben.kurtovic@verizon.net>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import mwparserfromhell

from earwigbot.tasks import Task

class AFCUndated(Task):
    """A task to clear [[Category:Undated AfC submissions]]."""
    name = "afc_undated"

    def setup(self):
        cfg = self.config.tasks.get(self.name, {})
        self.category = cfg.get("category", "Undated AfC submissions")
        default_summary = "Adding timestamp to undated [[WP:AFC|Articles for creation]] submission."
        self.summary = self.make_summary(cfg.get("summary", default_summary))

    def run(self, **kwargs):
        counter = 0
        for page in cat:
            if counter % 10:
                if self.shutoff_enabled():
                    return True
            ###
            counter += 1
