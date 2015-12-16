# -*- coding: utf-8  -*-
#
# Copyright (C) 2015 Ben Kurtovic <ben.kurtovic@gmail.com>
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

from __future__ import unicode_literals
from time import sleep

from earwigbot.tasks import Task
from earwigbot.wiki import constants

import mwparserfromhell

class InfoboxStation(Task):
    """
    A task to replace ``{{Infobox China station}}`` and
    ``{{Infobox Japan station}}`` with ``{{Infobox station}}``.
    """
    name = "infobox_station"
    number = 20

    def setup(self):
        self.site = self.bot.wiki.get_site()
        self._targets = {
            "China": (
                ["Infobox China station", "Infobox china station"],
                "Infobox China station/sandbox",
                "Infobox China station/sandbox/cats",
                "Wikipedia:Templates for discussion/Log/2015 February 8#Template:Infobox China station"
            ),
            "Japan": (
                ["Infobox Japan station", "Infobox japan station"],
                "Infobox Japan station/sandbox",
                "Infobox Japan station/sandbox/cats",
                "Wikipedia:Templates for discussion/Log/2015 May 9#Template:Infobox Japan station"
            ),
        }
        self._replacement = "{{Infobox station}}"
        self._sleep_time = 6
        self.summary = self.make_summary(
            "Replacing {source} with {dest} per [[{discussion}|TfD]].")

    def run(self, **kwargs):
        limit = int(kwargs.get("limit"), 0)
        for name, args in self._targets.items():
            if self.shutoff_enabled():
                return
            self._replace(name, args, limit)

    def _replace(self, name, args, limit=0):
        """
        Replace a template in all pages that transclude it.
        """
        self.logger.info("Replacing {0} infobox template".format(name))

        count = 0
        for title in self._get_transclusions(args[0][0]):
            if limit > 0 and count >= limit:
                logmsg = "Reached limit of {0} edits for {1} infoboxes"
                self.logger.info(logmsg.format(limit, name))
                return
            count += 1
            if count % 5 == 0 and self.shutoff_enabled():
                return
            page = self.site.get_page(title)
            self._process_page(page, args)

        self.logger.info("All {0} infoboxes updated".format(name))

    def _process_page(self, page, args):
        """
        Process a single page to replace a template.
        """
        self.logger.debug("Processing [[{0}]]".format(page.title))
        if not page.check_exclusion():
            self.logger.warn("Bot excluded from [[{0}]]".format(page.title))
            return

        code = mwparserfromhell.parse(page.get(), skip_style_tags=True)
        for tmpl in code.filter_templates():
            if tmpl.name.matches(args[0]):
                tmpl.name = "subst:" + args[2]
                cats = self._get_cats(page, unicode(tmpl))
                tmpl.name = "subst:" + args[1]
                self._add_cats(code, cats)

        if code == page.get():
            msg = "Couldn't figure out what to edit in [[{0}]]"
            self.logger.warn(msg.format(page.title))
            return

        summary = self.summary.format(
            source="{{" + args[0][0] + "}}", dest=self._replacement,
            discussion=args[3])
        page.edit(unicode(code), summary, minor=True)
        sleep(self._sleep_time)

    def _add_cats(self, code, cats):
        """Add category data (*cats*) to wikicode."""
        current_cats = code.filter_wikilinks(
            matches=lambda link: link.title.lower().startswith("category:"))
        norm = lambda cat: cat.title.lower()[len("category:"):].strip()

        catlist = [unicode(cat) for cat in cats if not any(
            norm(cur) == norm(cat) for cur in current_cats)]
        if not catlist:
            return
        text = "\n".join(catlist)

        if current_cats:
            code.insert_before(current_cats[0], text + "\n")
            return

        for tmpl in code.filter_templates():
            if tmpl.name.lower().endswith("stub"):
                prev = code.get(code.index(tmpl) - 1)
                if prev.endswith("\n\n"):
                    code.replace(prev, prev[:-1])
                code.insert_before(tmpl, text + "\n\n")

    def _get_cats(self, page, tmpl):
        """
        Return the categories that should be added to the page.
        """
        result = self.site.api_query(action="parse", title=page.title,
                                     prop="text", onlypst=1, text=tmpl)
        text = result["parse"]["text"]["*"]
        return mwparserfromhell.parse(text).filter_wikilinks()

    def _get_transclusions(self, tmpl):
        """
        Return a list of mainspace translusions of the given template.
        """
        query = """SELECT page_title
        FROM templatelinks
        LEFT JOIN page ON tl_from = page_id
        WHERE tl_namespace = ? AND tl_title = ? AND tl_from_namespace = ?"""

        results = self.site.sql_query(query, (
            constants.NS_TEMPLATE, tmpl.replace(" ", "_"), constants.NS_MAIN))
        return [title.decode("utf8").replace("_", " ") for (title,) in results]
