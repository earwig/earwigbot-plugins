# Copyright (C) 2009-2014 Ben Kurtovic <ben.kurtovic@gmail.com>
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

from earwigbot import wiki
from earwigbot.commands import Command


class AfCReport(Command):
    """Get information about an AfC submission by name."""

    name = "report"

    def process(self, data):
        self.site = self.bot.wiki.get_site()
        self.data = data

        try:
            self.statistics = self.bot.tasks.get("afc_statistics")
        except KeyError:
            e = "Cannot run command: requires afc_statistics task (from earwigbot_plugins)"
            self.logger.error(e)
            msg = "command requires afc_statistics task (from earwigbot_plugins)"
            self.reply(data, msg)
            return

        if not data.args:
            msg = "What submission do you want me to give information about?"
            self.reply(data, msg)
            return

        title = (
            " ".join(data.args)
            .replace("http://en.wikipedia.org/wiki/", "")
            .replace("http://enwp.org/", "")
            .strip()
        )
        titles = [
            title,
            "Draft:" + title,
            "Wikipedia:Articles for creation/" + title,
            "Wikipedia talk:Articles for creation/" + title,
        ]
        for attempt in titles:
            page = self.site.get_page(attempt, follow_redirects=False)
            if page.exists == page.PAGE_EXISTS:
                return self.report(page)

        self.reply(data, f"Submission \x0302{title}\x0f not found.")

    def report(self, page):
        url = page.url.encode("utf8")
        url = url.replace("en.wikipedia.org/wiki", "enwp.org")
        status = self.get_status(page)
        user = page.get_creator()
        user_name = user.name
        user_url = user.get_talkpage().url.encode("utf8")

        msg1 = "AfC submission report for \x0302{0}\x0f ({1}):"
        msg2 = "Status: \x0303{0}\x0f"
        msg3 = "Submitted by \x0302{0}\x0f ({1})"
        if status == "accepted":
            msg3 = "Reviewed by \x0302{0}\x0f ({1})"

        self.reply(self.data, msg1.format(page.title.encode("utf8"), url))
        self.say(self.data.chan, msg2.format(status))
        self.say(self.data.chan, msg3.format(user_name, user_url))

    def get_status(self, page):
        if page.is_redirect:
            target = page.get_redirect_target()
            if self.site.get_page(target).namespace == wiki.NS_MAIN:
                return "accepted"
            return "redirect"

        statuses = self.statistics.get_statuses(page.get())
        if "R" in statuses:
            return "being reviewed"
        elif "H" in statuses:
            return "pending draft"
        elif "P" in statuses:
            return "pending submission"
        elif "T" in statuses:
            return "unsubmitted draft"
        elif "D" in statuses:
            return "declined"
        return "unkown"
