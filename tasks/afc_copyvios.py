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

from hashlib import sha256
from os.path import expanduser
from threading import Lock
# from urllib import quote

import mwparserfromhell
import oursql

from earwigbot.tasks import Task

class AFCCopyvios(Task):
    """A task to check newly-edited [[WP:AFC]] submissions for copyright
    violations."""
    name = "afc_copyvios"
    number = 1

    def setup(self):
        cfg = self.config.tasks.get(self.name, {})
        self.template = cfg.get("template", "AfC suspected copyvio")
        self.ignore_list = cfg.get("ignoreList", [])
        self.min_confidence = cfg.get("minConfidence", 0.5)
        self.max_queries = cfg.get("maxQueries", 10)
        self.max_time = cfg.get("maxTime", 150)
        self.cache_results = cfg.get("cacheResults", False)
        default_summary = "Tagging suspected [[WP:COPYVIO|copyright violation]] of {url}."
        self.summary = self.make_summary(cfg.get("summary", default_summary))
        default_tags = [
            "Db-g12", "Db-copyvio", "Copyvio", "Copyviocore" "Copypaste"]
        self.tags = default_tags + cfg.get("tags", [])

        # Connection data for our SQL database:
        kwargs = cfg.get("sql", {})
        kwargs["read_default_file"] = expanduser("~/.my.cnf")
        self.conn_data = kwargs
        self.db_access_lock = Lock()

    def run(self, **kwargs):
        """Entry point for the bot task.

        Takes a page title in kwargs and checks it for copyvios, adding
        {{self.template}} at the top if a copyvio has been detected. A page is
        only checked once (processed pages are stored by page_id in an SQL
        database).
        """
        if self.shutoff_enabled():
            return
        title = kwargs["page"]
        page = self.bot.wiki.get_site().get_page(title)
        with self.db_access_lock:
            self.conn = oursql.connect(**self.conn_data)
            self.process(page)

    def process(self, page):
        """Detect copyvios in 'page' and add a note if any are found."""
        title = page.title
        if title in self.ignore_list:
            msg = u"Skipping [[{0}]], in ignore list"
            self.logger.info(msg.format(title))
            return

        pageid = page.pageid
        if self.has_been_processed(pageid):
            msg = u"Skipping [[{0}]], already processed"
            self.logger.info(msg.format(title))
            return
        code = mwparserfromhell.parse(page.get())
        if not self.is_pending(code):
            msg = u"Skipping [[{0}]], not a pending submission"
            self.logger.info(msg.format(title))
            return
        tag = self.is_tagged(code)
        if tag:
            msg = u"Skipping [[{0}]], already tagged with '{1}'"
            self.logger.info(msg.format(title, tag))
            return

        self.logger.info(u"Checking [[{0}]]".format(title))
        result = page.copyvio_check(self.min_confidence, self.max_queries,
                                    self.max_time)
        url = result.url
        orig_conf = "{0}%".format(round(result.confidence * 100, 2))

        if result.violation:
            if self.handle_violation(title, page, result, url, orig_conf):
                self._trial_reporter(title, False, url, orig_conf, result.queries, result.time, msg)
                self.log_processed(pageid)
                return
        else:
            msg = u"No violations detected in [[{0}]] (best: {1} at {2} confidence)"
            self.logger.info(msg.format(title, url, orig_conf))
            self._trial_reporter(title, False, url, orig_conf, result.queries, result.time, msg)

        self.log_processed(pageid)
        if self.cache_results:
            self.cache_result(page, result)

    def handle_violation(self, title, page, result, url, orig_conf):
        """Handle a page that passed its initial copyvio check."""
        # Things can change in the minute that it takes to do a check.
        # Confirm that a violation still holds true:
        page.load()
        content = page.get()
        tag = self.is_tagged(mwparserfromhell.parse(content))
        if tag:
            msg = u"A violation was detected in [[{0}]], but it was tagged"
            msg += u" in the mean time with '{1}' (best: {2} at {3} confidence)"
            self.logger.info(msg.format(title, tag, url, orig_conf))
            return True
        confirm = page.copyvio_compare(url, self.min_confidence)
        new_conf = "{0}%".format(round(confirm.confidence * 100, 2))
        if not confirm.violation:
            msg = u"A violation was detected in [[{0}]], but couldn't be confirmed."
            msg += u" It may have just been edited (best: {1} at {2} -> {3} confidence)"
            self.logger.info(msg.format(title, url, orig_conf, new_conf))
            return True

        msg = u"Found violation: [[{0}]] -> {1} ({2} confidence)"
        self.logger.info(msg.format(title, url, new_conf))
        # safeurl = quote(url.encode("utf8"), safe="/:").decode("utf8")
        # template = u"\{\{{0}|url={1}|confidence={2}\}\}\n"
        # template = template.format(self.template, safeurl, new_conf)
        # newtext = template + content
        # if "{url}" in self.summary:
        #     page.edit(newtext, self.summary.format(url=url))
        # else:
        #     page.edit(newtext, self.summary)
        self._trial_reporter(title, True, url, new_conf, result.queries, result.time, msg)

    def _trial_reporter(self, title, violation, url, conf, queries, time, msg):
        from datetime import datetime
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        data = u"\n" + ("-" * 80) + u"\n"
        data += u"[[{0}]] at {1}\n".format(title, date)
        data += u"Violation?   {0}\n".format("***YES***" if violation else "No")
        data += u"Confidence:  {0}\n".format(conf)
        data += u"Best match:  {0}\n".format(url)
        data += u"Num queries: {0}\n".format(queries)
        data += u"Time:        {0}\n".format(time)
        data += u"Log message: {0}\n".format(msg)
        with open("/data/project/earwigbot/public_html/copyvio_bot_trial.txt", "a") as fp:
            fp.write(data.encode("utf8"))

    def is_tagged(self, code):
        """Return whether a page contains a copyvio check template."""
        for template in code.ifilter_templates():
            for tag in self.tags:
                if template.name.matches(tag):
                    return tag

    def is_pending(self, code):
        """Return whether a page is a pending AFC submission."""
        other_statuses = ["r", "t", "d"]
        tmpls = ["submit", "afc submission/submit", "afc submission/pending"]
        for template in code.ifilter_templates():
            name = template.name.strip().lower()
            if name == "afc submission":
                if not template.has(1):
                    return True
                if template.get(1).value.strip().lower() not in other_statuses:
                    return True
            elif name in tmpls:
                return True
        return False

    def has_been_processed(self, pageid):
        """Returns True if pageid was processed before, otherwise False."""
        query = "SELECT 1 FROM processed WHERE page_id = ?"
        with self.conn.cursor() as cursor:
            cursor.execute(query, (pageid,))
            results = cursor.fetchall()
            return True if results else False

    def log_processed(self, pageid):
        """Adds pageid to our database of processed pages.

        Raises an exception if the page has already been processed.
        """
        query = "INSERT INTO processed VALUES (?)"
        with self.conn.cursor() as cursor:
            cursor.execute(query, (pageid,))

    def cache_result(self, page, result):
        """Store the check's result in a cache table temporarily.

        The cache contains the page's ID, a hash of its content, the URL of the
        best match, the time of caching, and the number of queries used. It
        will replace any existing cache entries for that page.

        The cache is intended for EarwigBot's complementary Toolserver web
        interface, in which copyvio checks can be done separately from the bot.
        The cache saves time and money by saving the result of the web search
        but neither the result of the comparison nor any actual text (which
        could violate data retention policy). Cache entries are (intended to
        be) retained for three days; this task does not remove old entries
        (that is handled by the Toolserver component).

        This will only be called if ``cache_results == True`` in the task's
        config, which is ``False`` by default.
        """
        pageid = page.pageid
        hash = sha256(page.get().encode("utf8")).hexdigest()
        query1 = "SELECT 1 FROM cache WHERE cache_id = ?"
        query2 = "DELETE FROM cache WHERE cache_id = ?"
        query3 = "INSERT INTO cache VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)"
        with self.conn.cursor() as cursor:
            cursor.execute(query1, (pageid,))
            if cursor.fetchall():
                cursor.execute(query2, (pageid,))
            args = (pageid, hash, result.url, result.queries, 0)
            cursor.execute(query3, args)
