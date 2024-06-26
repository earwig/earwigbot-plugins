# Copyright (C) 2009-2015 Ben Kurtovic <ben.kurtovic@gmail.com>
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
from earwigbot.wiki.constants import (
    NS_CATEGORY,
    NS_CATEGORY_TALK,
    NS_FILE,
    NS_FILE_TALK,
    NS_HELP_TALK,
    NS_PROJECT,
    NS_PROJECT_TALK,
    NS_TALK,
    NS_TEMPLATE,
    NS_TEMPLATE_TALK,
    NS_USER,
)

NS_DRAFT = 118


class AfCUndated(Task):
    """A task to clear [[Category:Undated AfC submissions]]."""

    name = "afc_undated"
    number = 5

    def setup(self):
        cfg = self.config.tasks.get(self.name, {})
        self.category = cfg.get("category", "Undated AfC submissions")
        default_summary = (
            "Adding timestamp to undated [[WP:AFC|Articles for creation]] submission."
        )
        self.summary = self.make_summary(cfg.get("summary", default_summary))
        self.namespaces = {
            "submission": [NS_USER, NS_PROJECT, NS_PROJECT_TALK, NS_DRAFT],
            "talk": [
                NS_TALK,
                NS_FILE_TALK,
                NS_TEMPLATE_TALK,
                NS_HELP_TALK,
                NS_CATEGORY_TALK,
            ],
        }
        self.aliases = {
            "submission": ["AfC submission"],
            "talk": ["WikiProject Articles for creation"],
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
        logmsg = "Undated category [[{0}]] has {1} members"
        self.logger.info(logmsg.format(category.title, category.size))
        if category.size:
            self._build_aliases()
            counter = 0
            for page in category:
                if not counter % 10:
                    if self.shutoff_enabled():
                        return
                self._process_page(page)
                counter += 1

    def _build_aliases(self):
        """Build template name aliases for the AfC templates."""
        for key in self.aliases:
            base = self.aliases[key][0]
            aliases = [base, "Template:" + base]
            result = self.site.api_query(
                action="query",
                list="backlinks",
                bllimit=50,
                blfilterredir="redirects",
                bltitle=aliases[1],
            )
            for data in result["query"]["backlinks"]:
                redir = self.site.get_page(data["title"])
                aliases.append(redir.title)
                if redir.namespace == NS_TEMPLATE:
                    aliases.append(redir.title.split(":", 1)[1])
            self.aliases[key] = aliases

    def _process_page(self, page):
        """Date the necessary templates inside a page object."""
        if not page.check_exclusion():
            msg = "Skipping [[{0}]]; bot excluded from editing"
            self.logger.info(msg.format(page.title))
            return

        is_sub = page.namespace in self.namespaces["submission"]
        is_talk = page.namespace in self.namespaces["talk"]
        if is_sub:
            aliases = self.aliases["submission"]
            timestamp = self._get_timestamp(page)
        elif is_talk:
            aliases = self.aliases["talk"]
            timestamp, reviewer = self._get_talkdata(page)
        else:
            msg = "[[{0}]] is undated, but in a namespace I don't know how to process"
            self.logger.warn(msg.format(page.title))
            return
        if not timestamp:
            return

        code = mwparserfromhell.parse(page.get())
        changes = 0
        for template in code.filter_templates():
            has_ts = template.has("ts", ignore_empty=True)
            if template.name.matches(aliases) and not has_ts:
                template.add("ts", timestamp)
                has_reviewer = template.has("reviewer", ignore_empty=True)
                if is_talk and not has_reviewer:
                    template.add("reviewer", reviewer)
                changes += 1

        if changes:
            msg = "Dating [[{0}]]: {1}x {2}"
            self.logger.info(msg.format(page.title, changes, aliases[0]))
            page.edit(str(code), self.summary)
        else:
            msg = "[[{0}]] is undated, but I can't figure out what to replace"
            self.logger.warn(msg.format(page.title))

    def _get_timestamp(self, page):
        """Get the timestamp associated with a particular submission."""
        self.logger.debug(f"[[{page.title}]]: Getting timestamp")
        result = self.site.api_query(
            action="query",
            prop="revisions",
            rvprop="timestamp",
            rvlimit=1,
            rvdir="newer",
            titles=page.title,
        )
        data = result["query"]["pages"].values()[0]
        if "revisions" not in data:
            log = "Couldn't get timestamp for [[{0}]]"
            self.logger.warn(log.format(page.title))
            return None
        raw = data["revisions"][0]["timestamp"]
        ts = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
        return ts.strftime("%Y%m%d%H%M%S")

    def _get_talkdata(self, page):
        """Get the timestamp and reviewer associated with a talkpage.

        This is the mover for a normal article submission, and the uploader for
        a file page.
        """
        subject = page.toggle_talk()
        if subject.exists == subject.PAGE_MISSING:
            log = "Couldn't process [[{0}]]: subject page doesn't exist"
            self.logger.warn(log.format(page.title))
            return None, None
        if subject.namespace == NS_FILE:
            self.logger.debug(f"[[{page.title}]]: Getting filedata")
            return self._get_filedata(subject)

        self.logger.debug(f"[[{page.title}]]: Getting talkdata")
        user, ts, revid = self.statistics.get_accepted(subject.pageid)
        if not ts:
            if subject.is_redirect or subject.namespace == NS_CATEGORY:
                log = "[[{0}]]: Couldn't get talkdata; trying redir/cat data"
                self.logger.debug(log.format(page.title))
                return self._get_redirdata(subject)
            log = "Couldn't get talkdata for [[{0}]]"
            self.logger.warn(log.format(page.title))
            return None, None
        return ts.strftime("%Y%m%d%H%M%S"), user

    def _get_filedata(self, page):
        """Get the timestamp and reviewer associated with a file talkpage."""
        result = self.site.api_query(
            action="query", prop="imageinfo", titles=page.title
        )
        data = result["query"]["pages"].values()[0]
        if "imageinfo" not in data:
            log = "Couldn't get filedata for [[{0}]]"
            self.logger.warn(log.format(page.title))
            return None, None
        info = data["imageinfo"][0]
        ts = datetime.strptime(info["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
        return ts.strftime("%Y%m%d%H%M%S"), info["user"]

    def _get_redirdata(self, page):
        """Get the timestamp and reviewer for a redirect/category talkpage."""
        result = self.site.api_query(
            action="query",
            prop="revisions",
            rvprop="timestamp|user",
            rvlimit=1,
            rvdir="newer",
            titles=page.title,
        )
        if "batchcomplete" not in result:
            log = "Couldn't get redir/cat talkdata for [[{0}]]: has multiple revisions"
            self.logger.warn(log.format(page.title))
            return None, None
        rev = result["query"]["pages"].values()[0]["revisions"][0]
        ts = datetime.strptime(rev["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
        return ts.strftime("%Y%m%d%H%M%S"), rev["user"]
