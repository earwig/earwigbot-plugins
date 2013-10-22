# -*- coding: utf-8  -*-
#
# Copyright (C) 2009-2013 Ben Kurtovic <ben.kurtovic@gmail.com>
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

from datetime import datetime, timedelta

from earwigbot.tasks import Task

class AFCDailyCats(Task):
    """A task to create daily categories for [[WP:AFC]]."""
    name = "afc_dailycats"
    number = 3

    def setup(self):
        cfg = self.config.tasks.get(self.name, {})
        self.prefix = cfg.get("prefix", "Category:AfC submissions by date/")
        self.content = cfg.get("content", "{{AFC submission category header}}")
        default_summary = "Creating {0} category page for [[WP:AFC|Articles for creation]]."
        self.summary = self.make_summary(cfg.get("summary", default_summary))

    def run(self, **kwargs):
        if self.shutoff_enabled():
            return
        self.site = self.bot.wiki.get_site()
        self.make_cats()
        self.make_cats(1)
        self.make_cats(2)
        self.make_cats(3)

    def make_cats(self, days=0):
        dt = datetime.now() + timedelta(days)
        self.make_cat(dt.strftime("%d %B %Y"), "daily")
        if dt.day == 1:
            self.make_cat(dt.strftime("%B %Y"), "monthly")
            if dt.month == 1:
                self.make_cat(dt.strftime("%Y"), "yearly")

    def make_cat(self, suffix, word):
        page = self.site.get_page(self.prefix + suffix)
        if page.exists == page.PAGE_MISSING:
            page.edit(self.content, self.summary.format(word))
            self.logger.info(u"Creating [[{0}]]".format(page.title))
        else:
            self.logger.debug(u"Skipping [[{0}]], exists".format(page.title))
