# -*- coding: utf-8  -*-
#
# Copyright (C) 2016 Ben Kurtovic <ben.kurtovic@gmail.com>
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

from collections import namedtuple
from datetime import datetime
from difflib import ndiff
from Queue import Queue
import re
from threading import Thread

from earwigbot.commands import Command
from earwigbot.exceptions import APIError
from earwigbot.irc import RC
from earwigbot.wiki import constants

_Diff = namedtuple("_Diff", ["added", "removed"])

class RCMonitor(Command):
    """Monitors the recent changes feed for certain edits and reports them to a
    dedicated channel."""
    name = "rc_monitor"
    commands = ["rc_monitor", "rcm"]
    hooks = ["msg", "rc"]

    def setup(self):
        try:
            self._channel = self.config.commands[self.name]["channel"]
        except KeyError:
            self._channel = None
            log = ('Cannot use without a report channel set as '
                   'config.commands["{0}"]["channel"]')
            self.logger.warn(log.format(self.name))

        self._stats = {
            "start": datetime.utcnow(),
            "edits": 0,
            "hits": 0,
            "max_backlog": 0
        }
        self._levels = {}
        self._issues = {}
        self._descriptions = {}
        self._redirects = {}
        self._queue = Queue()

        self._thread = Thread(target=self._callback, name="rc_monitor")
        self._thread.daemon = True
        self._thread.running = True
        self._prepare_reports()
        self._thread.start()

    def check(self, data):
        if not self._channel:
            return
        return isinstance(data, RC) or (
            data.is_command and data.command in self.commands)

    def process(self, data):
        if isinstance(data, RC):
            newlen = self._queue.qsize() + 1
            self._queue.put(data)
            if newlen > self._stats["max_backlog"]:
                self._stats["max_backlog"] = newlen
            return

        if not self.config.irc["permissions"].is_admin(data):
            self.reply(data, "You must be a bot admin to use this command.")
            return

        since = self._stats["start"].strftime("%H:%M:%S, %d %B %Y")
        seconds = (datetime.utcnow() - self._stats["start"]).total_seconds()
        rate = self._stats["edits"] / seconds
        msg = ("\x02{edits:,}\x0F edits checked since {since} "
               "(\x02{rate:.2f}\x0F edits/sec); \x02{hits:,}\x0F hits; "
               "\x02{qsize:,}\x0F-edit backlog (\x02{max_backlog:,}\x0F max).")
        self.reply(data, msg.format(
            since=since, rate=rate, qsize=self._queue.qsize(), **self._stats))

    def unload(self):
        self._thread.running = False
        self._queue.put(None)

    def _prepare_reports(self):
        """Set up internal tables for storing report information."""
        routine = 1
        alert = 2
        urgent = 3

        self._levels = {
            routine: "routine",
            alert: "alert",
            urgent: "URGENT"
        }
        self._issues = {
            "g10": alert
        }
        self._descriptions = {
            "g10": "CSD G10 nomination"
        }

    def _get_diff(self, oldrev, newrev):
        """Return the difference between two revisions.

        A diff is a 2-tuple: (list of lines added, list of lines removed).
        """
        site = self.bot.wiki.get_site()
        try:
            result = site.api_query(
                action="query", prop="revisions", rvprop="ids|content",
                rvslots="main",
                revids=(oldrev + "|" + newrev) if oldrev else newrev)
        except APIError:
            return None

        try:
            pages = result["query"]["pages"].values()
        except IndexError:
            return None
        if len(pages) != 1:
            return None
        revs = pages[0]["revisions"]

        if not oldrev:
            try:
                text = revs[0]["slots"]["main"]["*"]
            except (IndexError, KeyError):
                return None
            return _Diff(text.splitlines(), [])

        try:
            oldtext = [rv["slots"]["main"]["*"] for rv in revs
                       if rv["revid"] == int(oldrev)][0]
            newtext = [rv["slots"]["main"]["*"] for rv in revs
                       if rv["revid"] == int(newrev)][0]
        except (IndexError, KeyError):
            return None

        lines = list(ndiff(oldtext.splitlines(), newtext.splitlines()))
        added = [line[2:] for line in lines if line[:2] == "+ "]
        removed = [line[2:] for line in lines if line[:2] == "- "]
        return _Diff(added, removed)

    def _fetch_redirects(self, template):
        """Return a list of valid names for a given template."""
        site = self.bot.wiki.get_site()
        try:
            result = site.api_query(
                action="query", list="backlinks", blfilterredir="redirects",
                blnamespace=constants.NS_TEMPLATE, bllimit=50,
                bltitle="Template:" + template)
        except APIError:
            return []

        redirs = {link["title"].split(":", 1)[1].lower()
                  for link in result["query"]["backlinks"]}
        redirs.add(template)
        return redirs

    def _fast_template_search(self, template):
        """Return a compiled regular expression for matching templates."""
        if template not in self._redirects:
            redirects = self._fetch_redirects(template)
            if not redirects:
                return None
            self._redirects[template] = redirects

        search = "|".join(r"(template:)?" + re.escape(tmpl).replace(r"\ ", r"[ _]")
                          for tmpl in self._redirects[template])
        return re.compile(r"\{\{\s*(" + search + r")\s*(\||\}\})", re.U|re.I)

    def _evaluate_csd(self, diff):
        """Evaluate a diff for CSD tagging."""
        regex = self._fast_template_search("db-g10")
        if not regex:
            return []

        if any(regex.search(line) for line in diff.added):
            return ["g10"]
        return []

    def _evaluate(self, event):
        """Return heuristic information about the given RC event."""
        oldrev = re.search(r"(?:\?|&)oldid=(.*?)(?:&|$)", event.url)
        newrev = re.search(r"(?:\?|&)diff=(.*?)(?:&|$)", event.url)
        if not oldrev:
            return []
        if newrev:
            diff = self._get_diff(oldrev.group(1), newrev.group(1))
        else:
            diff = self._get_diff(None, oldrev.group(1))
        if not diff:
            return []

        issues = []
        issues.extend(self._evaluate_csd(diff))
        issues.sort(key=lambda issue: self._issues[issue], reverse=True)
        return issues

    def _format(self, rc, report):
        """Format a RC event for the report channel."""
        level = self._levels[max(self._issues[issue] for issue in report)]
        descr = ", ".join(self._descriptions[issue] for issue in report)
        notify = " ".join("!rcm-" + issue for issue in report)
        cmnt = rc.comment if len(rc.comment) <= 50 else rc.comment[:47] + "..."

        msg = ("[\x02{level}\x0F] ({descr}) [\x02{notify}\x0F]\x0306 * "
               "\x0314[[\x0307{title}\x0314]]\x0306 * \x0303{user}\x0306 * "
               "\x0302{url}\x0306 * \x0310{comment}")
        return msg.format(
            level=level, descr=descr, notify=notify, title=rc.page,
            user=rc.user, url=rc.url, comment=cmnt)

    def _handle_event(self, event):
        """Process a recent change event."""
        if not event.is_edit or "B" in event.flags:
            return
        report = self._evaluate(event)
        self._stats["edits"] += 1
        if report:
            self.say(self._channel, self._format(event, report))
            self._stats["hits"] += 1

    def _callback(self):
        """Internal callback for the RC monitor thread."""
        while self._thread.running:
            event = self._queue.get()
            if not self._thread.running:
                break
            self._handle_event(event)
