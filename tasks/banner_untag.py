# -*- coding: utf-8  -*-
#
# Copyright (C) 2017 Ben Kurtovic <ben.kurtovic@gmail.com>
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

import time

from earwigbot.tasks import Task

class BannerUntag(Task):
    """A task to undo mistaken tagging edits made by wikiproject_tagger."""
    name = "banner_untag"
    number = 14

    def run(self, **kwargs):
        self.site = self.bot.wiki.get_site()
        self.summary = kwargs["summary"]
        self.throttle = int(kwargs.get("throttle", 0))

        rev_file = kwargs["rev-file"]
        done_file = kwargs["done-file"]
        error_file = kwargs["error-file"]

        with open(done_file) as donefp:
            done = [int(line) for line in donefp.read().splitlines()]

        with open(rev_file) as fp:
            data = [[int(x) for x in line.split("\t")]
                    for line in fp.read().splitlines()]
            data = [item for item in data if item[0] not in done]

        with open(error_file, "a") as errfp:
            with open(done_file, "a") as donefp:
                self._process_data(data, errfp, donefp)

    def _process_data(self, data, errfile, donefile):
        chunksize = 50
        for chunkidx in range((len(data) + chunksize - 1) / chunksize):
            chunk = data[chunkidx*chunksize:(chunkidx+1)*chunksize]
            if self.shutoff_enabled():
                return
            self._process_chunk(chunk, errfile, donefile)

    def _process_chunk(self, chunk, errfile, donefile):
        pageids_to_revids = dict(chunk)
        res = self.site.api_query(
            action="query", prop="revisions", rvprop="ids",
            pageids="|".join(str(item[0]) for item in chunk), formatversion=2)

        stage2 = []
        for pagedata in res["query"]["pages"]:
            pageid = pagedata["pageid"]
            title = pagedata["title"]
            revid = pagedata["revisions"][0]["revid"]
            parentid = pagedata["revisions"][0]["parentid"]
            if pageids_to_revids[pageid] == revid:
                stage2.append(str(parentid))
            else:
                self.logger.info(u"Skipping [[%s]], not latest edit" % title)
                donefile.write("%d\n" % pageid)
                errfile.write(u"%s\n" % title)

        if not stage2:
            return

        res2 = self.site.api_query(
            action="query", prop="revisions", rvprop="content",
            revids="|".join(stage2), formatversion=2)

        for pagedata in res2["query"]["pages"]:
            if pagedata["revisions"][0]["contentmodel"] != "wikitext":
                continue
            pageid = pagedata["pageid"]
            title = pagedata["title"]
            content = pagedata["revisions"][0]["content"]

            self.logger.debug(u"Reverting one edit on [[%s]]" % title)
            page = self.site.get_page(title)
            page.edit(content, self.make_summary(self.summary), minor=True)

            donefile.write("%d\n" % pageid)
            if self.throttle:
                time.sleep(self.throttle)
