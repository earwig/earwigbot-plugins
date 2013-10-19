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

from datetime import datetime

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
        self.aliases = {
            "submission": ["AFC submission"],
            "talk": ["WikiProject Articles for creation"]
        }

    def run(self, **kwargs):
        try:
            self.statistics = self.bot.tasks.get("afc_statistics")
        except KeyError:
            err = "Requires afc_statistics task (from earwigbot_plugins)"
            self.logger.error(err)
            return

        self.site = self.bot.wiki.get_site()
        category = self.site.get_category(self.category)
        logmsg = u"Undated category [[{0}]] has {1} members"
        self.logger.info(logmsg.format(category.title, category.size))
        if category.size:
            self.build_aliases()
            counter = 0
            for page in category:
                if not counter % 10:
                    if self.shutoff_enabled():
                        return
                self.process_page(page)
                counter += 1

    def build_aliases(self):
        """Build template name aliases for the AFC templates."""
        for key in self.aliases:
            base = self.aliases[key][0]
            aliases = [base, "Template:" + base]
            result = self.site.api_query(
                action="query", list="backlinks", bllimit=50,
                blfilterredir="redirects", bltitle=aliases[1])
            for data in result["query"]["backlinks"]:
                redir = self.site.get_page(data["title"])
                aliases.append(redir.title)
                if redir.namespace == NS_TEMPLATE:
                    aliases.append(redir.title.split(":", 1)[1])
            self.aliases[key] = aliases

    def process_page(self, page):
        """Date the necessary templates inside a page object."""
        if not page.check_exclusion():
            msg = u"Skipping [[{0}]]; bot excluded from editing"
            self.logger.info(msg.format(page.title))
            return

        is_sub = page.namespace in self.namespaces["submission"]
        is_talk = page.namespace in self.namespaces["talk"]
        if is_sub:
            aliases = self.aliases["submission"]
            timestamps = {}
        elif is_talk:
            aliases = self.aliases["talk"]
            timestamp, reviewer = self.get_talkdata(page)
            if not timestamp:
                return
        else:
            msg = u"[[{0}]] is undated, but in a namespace I don't know how to process"
            self.logger.warn(msg.format(page.title))
            return

        code = mwparserfromhell.parse(page.get())
        changes = 0
        for template in code.filter_templates():
            has_ts = template.has("ts", ignore_empty=True)
            has_reviewer = template.has("reviewer", ignore_empty=True)
            if template.name.matches(aliases) and not has_ts:
                if is_sub:
                    status = self.get_status(template)
                    if status in timestamps:
                        timestamp = timestamps[status]
                    else:
                        timestamp = self.get_timestamp(page, status)
                        timestamps[status] = timestamp
                    if not timestamp:
                        continue
                template.add("ts", timestamp)
                if is_talk and not has_reviewer:
                    template.add("reviewer", reviewer)
                changes += 1

        if changes:
            msg = u"Dating [[{0}]]: {1}x {2}"
            self.logger.info(msg.format(page.title, changes, aliases[0]))
            page.edit(unicode(code), self.summary)
        else:
            msg = u"[[{0}]] is undated, but I can't figure out what to replace"
            self.logger.warn(msg.format(page.title))

    def get_status(self, template):
        """Get the status code that corresponds to a given template."""
        valid = ["P", "R", "T", "D"]
        if template.has(1):
            status = template.get(1).value.strip().upper()
            if status in valid:
                return status
        return "P"

    def get_timestamp(self, page, chart):
        """Get the timestamp associated with a particular submission."""
        log = u"[[{0}]]: Getting timestamp for state {1}"
        self.logger.debug(log.format(page.title, chart))
        search = self.statistics.search_history
        user, ts, revid = search(page.pageid, chart, chart, [])
        if not ts:
            log = u"Couldn't find timestamp in [[{0}]] with state {1}"
            self.logger.warn(log.format(page.title, chart))
            return None
        return ts.strftime("%Y%m%d%H%M%S")

    def get_talkdata(self, page):
        """Get the timestamp and reviewer associated with a talkpage.

        This is the mover for a normal article submission, and the uploader for
        a file page.
        """
        subject = page.toggle_talk()
        if subject.namespace == NS_FILE:
            return self.get_filedata(subject)
        self.logger.debug(u"[[{0}]]: Getting talkdata".format(page.title))
        chart = self.statistics.CHART_ACCEPT
        user, ts, revid = self.statistics.get_special(subject.pageid, chart)
        if not ts:
            log = u"Couldn't get talkdata for [[{0}]]"
            self.logger.warn(log.format(page.title))
            return None, None
        return ts.strftime("%Y%m%d%H%M%S"), user

    def get_filedata(self, page):
        """Get the timestamp and reviewer associated with a file talkpage."""
        self.logger.debug(u"[[{0}]]: Getting filedata".format(page.title))
        result = self.site.api_query(action="query", prop="imageinfo",
                                     titles=page.title)
        data = result["query"]["pages"].values()[0]
        if "imageinfo" not in data:
            log = u"Couldn't get filedata for [[{0}]]"
            self.logger.warn(log.format(page.title))
            return None, None
        info = data["imageinfo"][0]
        ts = datetime.strptime(info["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
        return ts.strftime("%Y%m%d%H%M%S"), info["user"]
