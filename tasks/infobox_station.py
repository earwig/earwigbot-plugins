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
        self.summary = self.make_summary(
            "Replacing {source} with {dest} per [[{discussion}|TfD]].")

    def run(self, **kwargs):
        for name, args in self._targets.items():
            if self.shutoff_enabled():
                return
            self._replace(name, args)

    def _replace(self, name, args):
        """
        Replace a template in all pages that transclude it.
        """
        self.logger.info("Replacing {0} infobox template".format(name))

        count = 0
        for title in self._get_transclusions(args[0][0]):
            count += 1
            if count % 10 == 0 and self.shutoff_enabled():
                return
            page = self.site.get_page(title)
            self._process_page(page, args)

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
                self._add_cats(code, unicode(tmpl))
                tmpl.name = "subst:" + args[1]
                break

        if code == page.get():
            msg = "Couldn't figure out what to edit in [[{0}]]"
            self.logger.warn(msg.format(page.title))
            return

        summary = self.summary.format(
            source="{{" + args[0][0] + "}}", dest=self._replacement,
            discussion=args[3])
        page.edit(unicode(code), summary, minor=True)

    def _add_cats(self, code, cats):
        """Add category data (*cats*) to wikicode."""
        for link in code.ifilter_wikilinks():
            if link.title.lower().startswith("category:"):
                code.insert_before(link, cats + "\n")
                return

        for tmpl in code.filter_templates():
            if tmpl.name.lower().endswith("stub"):
                prev = code.get(code.index(tmpl) - 1)
                if prev.endswith("\n\n"):
                    code.replace(prev, prev[:-1])
                code.insert_before(tmpl, cats + "\n\n")

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
