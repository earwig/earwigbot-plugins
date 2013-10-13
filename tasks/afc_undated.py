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
from earwigbot.wiki.constants import *

class AFCUndated(Task):
    """A task to clear [[Category:Undated AfC submissions]]."""
    name = "afc_undated"
    number = 5

    def setup(self):
        cfg = self.config.tasks.get(self.name, {})
        self.category = cfg.get("category", "Undated AfC submissions")
        default_summary = "Adding timestamp to undated [[WP:AFC|Articles for creation]] submission."
        self.summary = self.make_summary(cfg.get("summary", default_summary))
        self.namespaces = {
            "submission": [NS_USER, NS_PROJECT, NS_PROJECT_TALK],
            "talk": [NS_TALK, NS_FILE_TALK, NS_TEMPLATE_TALK, NS_HELP_TALK,
                     NS_CATEGORY_TALK]
        }
        self.aliases = {"submission": ["AFC submission"], "talk": ["WPAFC"]}

    def run(self, **kwargs):
        self.site = self.bot.wiki.get_site()
        category = self.site.get_category(self.category)
        logmsg = u"Undated category [[{0}]] has {1} members"
        self.logger.info(logmsg.format(category.title, category.size))
        if category.size:
            self.build_aliases()
            counter = 0
            for page in category:
                if counter % 10:
                    if self.shutoff_enabled():
                        return
                self.process_page(page)
                counter += 1

    def build_aliases(self):
        """Build template name aliases for the AFC templates."""
        pass

    def process_page(self, page):
        """Date the necessary templates inside a page object."""
        is_sub = page.namespace in self.namespaces["submission"]
        is_talk = page.namespace in self.namespaces["talk"]
        if is_sub:
            aliases = self.aliases["subission"]
            timestamp = self.get_timestamp(page)
        elif is_talk:
            aliases = self.aliases["talk"]
            timestamp, reviewer = self.get_talkdata(page)
        else:
            msg = u"[[{0}]] is undated, but in a namespace we don't know how to process"
            self.logger.warn(msg.format(page.title))
            return

        code = mwparserfromhell.parse(page.get())
        changes = 0
        for template in code.filter_templates():
            if template.name.matches(aliases) and not template.has("ts"):
                template.add("ts", timestamp)
                if is_talk and not template.has("reviewer"):
                    template.add("reviewer", reviewer)
                changes += 1

        if changes:
            msg = u"Dating [[{0}]]: {1}x {2}"
            self.logger.info(msg.format(page.title, changes, aliases[0]))
            page.edit(unicode(code), self.summary)
        else:
            msg = u"[[{0}]] is undated, but I can't figure out what to replace"
            self.logger.warn(msg.format(page.title))

    def get_timestamp(self, page):
        """Get the timestamp associated with a particular submission."""
        return timestamp

    def get_talkdata(self, page):
        """Get the timestamp and reviewer associated with a talkpage.

        This is the mover for a normal article submission, and the uploader for
        a file page.
        """
        return timestamp, reviewer
