# -*- coding: utf-8  -*-
#
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

from datetime import datetime
import re
from os.path import expanduser
from threading import Lock
from time import sleep

import mwparserfromhell
import oursql

from earwigbot import exceptions
from earwigbot import wiki
from earwigbot.tasks import Task

class AFCStatistics(Task):
    """A task to generate statistics for WikiProject Articles for Creation.

    Statistics are stored in a MySQL database ("u_earwig_afc_statistics")
    accessed with oursql. Statistics are synchronied with the live database
    every four minutes and saved once an hour, on the hour, to self.pagename.
    In the live bot, this is "Template:AFC statistics".
    """
    name = "afc_statistics"
    number = 2

    # Chart status number constants:
    CHART_NONE = 0
    CHART_PEND = 1
    CHART_REVIEW = 3
    CHART_ACCEPT = 4
    CHART_DECLINE = 5
    CHART_MISPLACE = 6

    def setup(self):
        self.cfg = cfg = self.config.tasks.get(self.name, {})
        self.site = self.bot.wiki.get_site()
        self.revision_cache = {}

        # Set some wiki-related attributes:
        self.pagename = cfg.get("page", "Template:AFC statistics")
        self.pending_cat = cfg.get("pending", "Pending AfC submissions")
        self.ignore_list = cfg.get("ignoreList", [])
        default_summary = "Updating statistics for [[WP:WPAFC|WikiProject Articles for creation]]."
        self.summary = self.make_summary(cfg.get("summary", default_summary))

        # Templates used in chart generation:
        templates = cfg.get("templates", {})
        self.tl_header = templates.get("header", "AFC statistics/header")
        self.tl_row = templates.get("row", "#invoke:AfC|row")
        self.tl_footer = templates.get("footer", "AFC statistics/footer")

        # Connection data for our SQL database:
        kwargs = cfg.get("sql", {})
        kwargs["read_default_file"] = expanduser("~/.my.cnf")
        self.conn_data = kwargs
        self.db_access_lock = Lock()

    def run(self, **kwargs):
        """Entry point for a task event.

        Depending on the kwargs passed, we will either synchronize our local
        statistics database with the site (self.sync()) or save it to the wiki
        (self.save()). We will additionally create an SQL connection with our
        local database.
        """
        action = kwargs.get("action")
        if not self.db_access_lock.acquire(False):  # Non-blocking
            if action == "sync":
                self.logger.info("A sync is already ongoing; aborting")
                return
            self.logger.info("Waiting for database access lock")
            self.db_access_lock.acquire()

        try:
            self.site = self.bot.wiki.get_site()
            self.conn = oursql.connect(**self.conn_data)
            self.revision_cache = {}
            try:
                if action == "save":
                    self.save(kwargs)
                elif action == "sync":
                    self.sync(kwargs)
            finally:
                self.conn.close()
        finally:
            self.db_access_lock.release()

    #################### CHART BUILDING AND SAVING METHODS ####################

    def save(self, kwargs):
        """Save our local statistics to the wiki.

        After checking for emergency shutoff, the statistics chart is compiled,
        and then saved to self.pagename using self.summary iff it has changed
        since last save.
        """
        self.logger.info("Saving chart")
        if kwargs.get("fromIRC"):
            summary = self.summary + " (!earwigbot)"
        else:
            if self.shutoff_enabled():
                return
            summary = self.summary

        statistics = self._compile_charts()

        page = self.site.get_page(self.pagename)
        text = page.get()
        newtext = re.sub(u"<!-- stat begin -->(.*?)<!-- stat end -->",
                         "<!-- stat begin -->\n" + statistics + "\n<!-- stat end -->",
                         text, flags=re.DOTALL)
        if newtext == text:
            self.logger.info("Chart unchanged; not saving")
            return  # Don't edit the page if we're not adding anything

        newtext = re.sub("<!-- sig begin -->(.*?)<!-- sig end -->",
                         "<!-- sig begin -->~~~ at ~~~~~<!-- sig end -->",
                         newtext)
        page.edit(newtext, summary, minor=True, bot=True)
        self.logger.info(u"Chart saved to [[{0}]]".format(page.title))

    def _compile_charts(self):
        """Compile and return all statistics information from our local db."""
        stats = ""
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT * FROM chart")
            for chart in cursor:
                stats += self._compile_chart(chart) + "\n"
        return stats[:-1]  # Drop the last newline

    def _compile_chart(self, chart_info):
        """Compile and return a single statistics chart."""
        chart_id, chart_title, special_title = chart_info

        chart = self.tl_header + "|" + chart_title
        if special_title:
            chart += "|" + special_title
        chart = "{{" + chart + "}}"

        query = "SELECT * FROM page JOIN row ON page_id = row_id WHERE row_chart = ?"
        with self.conn.cursor(oursql.DictCursor) as cursor:
            cursor.execute(query, (chart_id,))
            for page in cursor.fetchall():
                chart += "\n" + self._compile_chart_row(page)

        chart += "\n{{" + self.tl_footer + "}}"
        return chart

    def _compile_chart_row(self, page):
        """Compile and return a single chart row.

        'page' is a dict of page information, taken as a row from the page
        table, where keys are column names and values are their cell contents.
        """
        row = u"{0}|s={page_status}|t={page_title}|z={page_size}|"
        if page["page_special_oldid"]:
            row += "sr={page_special_user}|sd={page_special_time}|si={page_special_oldid}|"
        row += "mr={page_modify_user}|md={page_modify_time}|mi={page_modify_oldid}"

        page["page_special_time"] = self._fmt_time(page["page_special_time"])
        page["page_modify_time"] = self._fmt_time(page["page_modify_time"])

        if page["page_notes"]:
            row += "|n=1{page_notes}"

        return "{{" + row.format(self.tl_row, **page) + "}}"

    def _fmt_time(self, date):
        """Format a datetime into the standard MediaWiki timestamp format."""
        return date.strftime("%H:%M, %d %b %Y")

    ######################## PRIMARY SYNC ENTRY POINTS ########################

    def sync(self, kwargs):
        """Synchronize our local statistics database with the site.

        Syncing involves, in order, updating tracked submissions that have
        been changed since last sync (self._update_tracked()), adding pending
        submissions that are not tracked (self._add_untracked()), and removing
        old submissions from the database (self._delete_old()).

        The sync will be canceled if SQL replication lag is greater than 600
        seconds, because this will lead to potential problems and outdated
        data, not to mention putting demand on an already overloaded server.
        Giving sync the kwarg "ignore_replag" will go around this restriction.
        """
        self.logger.info("Starting sync")

        replag = self.site.get_replag()
        self.logger.debug("Server replag is {0}".format(replag))
        if replag > 600 and not kwargs.get("ignore_replag"):
            msg = "Sync canceled as replag ({0} secs) is greater than ten minutes"
            self.logger.warn(msg.format(replag))
            return

        with self.conn.cursor() as cursor:
            self._update_tracked(cursor)
            self._add_untracked(cursor)
            self._update_stale(cursor)
            self._delete_old(cursor)

        self.logger.info("Sync completed")

    def _update_tracked(self, cursor):
        """Update tracked submissions that have been changed since last sync.

        This is done by iterating through every page in our database and
        comparing our stored latest revision ID with the actual latest revision
        ID from an SQL query. If they differ, we will update our information
        about the page (self._update_page()).

        If the page does not exist, we will remove it from our database with
        self._untrack_page().
        """
        self.logger.debug("Updating tracked submissions")
        query = """SELECT s.page_id, s.page_title, s.page_modify_oldid,
                          r.page_latest, r.page_title, r.page_namespace
                   FROM page AS s
                   LEFT JOIN {0}_p.page AS r ON s.page_id = r.page_id
                   WHERE s.page_modify_oldid != r.page_latest
                   OR r.page_id IS NULL"""
        cursor.execute(query.format(self.site.name))

        for pageid, title, oldid, real_oldid, real_title, real_ns in cursor:
            if not real_oldid:
                self._untrack_page(cursor, pageid)
                continue
            msg = u"Updating page [[{0}]] (id: {1}) @ {2}"
            self.logger.debug(msg.format(title, pageid, oldid))
            msg = u"  {0}: oldid: {1} -> {2}"
            self.logger.debug(msg.format(pageid, oldid, real_oldid))
            real_title = real_title.decode("utf8").replace("_", " ")
            ns = self.site.namespace_id_to_name(real_ns)
            if ns:
                real_title = u":".join((ns, real_title))
            try:
                self._update_page(cursor, pageid, real_title)
            except Exception:
                e = u"Error updating page [[{0}]] (id: {1})"
                self.logger.exception(e.format(real_title, pageid))

    def _add_untracked(self, cursor):
        """Add pending submissions that are not yet tracked.

        This is done by compiling a list of all currently tracked submissions
        and iterating through all members of self.pending_cat via SQL. If a
        page in the pending category is not tracked and is not in
        self.ignore_list, we will track it with self._track_page().
        """
        self.logger.debug("Adding untracked pending submissions")
        query = """SELECT r.page_id, r.page_title, r.page_namespace
                   FROM {0}_p.page AS r
                   INNER JOIN {0}_p.categorylinks AS c ON r.page_id = c.cl_from
                   LEFT JOIN page AS s ON r.page_id = s.page_id
                   WHERE s.page_id IS NULL AND c.cl_to = ?"""
        cursor.execute(query.format(self.site.name),
                       (self.pending_cat.replace(" ", "_"),))

        for pageid, title, ns in cursor:
            title = title.decode("utf8").replace("_", " ")
            ns_name = self.site.namespace_id_to_name(ns)
            if ns_name:
                title = u":".join((ns_name, title))
            if title in self.ignore_list or ns == wiki.NS_CATEGORY:
                continue
            msg = u"Tracking page [[{0}]] (id: {1})".format(title, pageid)
            self.logger.debug(msg)
            try:
                self._track_page(cursor, pageid, title)
            except Exception:
                e = u"Error tracking page [[{0}]] (id: {1})"
                self.logger.exception(e.format(title, pageid))

    def _update_stale(self, cursor):
        """Update submissions that haven't been updated in a long time.

        This is intended to update notes that change without typical update
        triggers, like when submitters are blocked. It also resolves conflicts
        when pages are tracked during high replag, potentially causing data to
        be inaccurate (like a missed decline). It updates no more than the ten
        stalest pages that haven't been updated in two days.
        """
        self.logger.debug("Updating stale submissions")
        query = """SELECT page_id, page_title, page_modify_oldid
                   FROM page JOIN updatelog ON page_id = update_id
                   WHERE ADDTIME(update_time, '48:00:00') < NOW()
                   ORDER BY update_time ASC LIMIT 10"""
        cursor.execute(query)

        for pageid, title, oldid in cursor:
            msg = u"Updating page [[{0}]] (id: {1}) @ {2}"
            self.logger.debug(msg.format(title, pageid, oldid))
            try:
                self._update_page(cursor, pageid, title)
            except Exception:
                e = u"Error updating page [[{0}]] (id: {1})"
                self.logger.exception(e.format(title, pageid))

    def _delete_old(self, cursor):
        """Remove old submissions from the database.

        "Old" is defined as a submission that has been declined or accepted
        more than 36 hours ago. Pending submissions cannot be "old".
        """
        self.logger.debug("Removing old submissions from chart")
        query = """DELETE FROM page, row, updatelog USING page JOIN row
                   ON page_id = row_id JOIN updatelog ON page_id = update_id
                   WHERE row_chart IN (?, ?)
                   AND ADDTIME(page_special_time, '36:00:00') < NOW()"""
        cursor.execute(query, (self.CHART_ACCEPT, self.CHART_DECLINE))

    ######################## PRIMARY PAGE ENTRY POINTS ########################

    def _untrack_page(self, cursor, pageid):
        """Remove a page, given by ID, from our database."""
        self.logger.debug("Untracking page (id: {0})".format(pageid))
        query = """DELETE FROM page, row, updatelog USING page JOIN row
                   ON page_id = row_id JOIN updatelog ON page_id = update_id
                   WHERE page_id = ?"""
        cursor.execute(query, (pageid,))

    def _track_page(self, cursor, pageid, title):
        """Update hook for when page is not in our database.

        A variety of SQL queries are used to gather information about the page,
        which is then saved to our database.
        """
        content = self._get_content(pageid)
        if content is None:
            msg = u"Could not get page content for [[{0}]]".format(title)
            self.logger.error(msg)
            return

        namespace = self.site.get_page(title).namespace
        status, chart = self._get_status_and_chart(content, namespace)
        if chart == self.CHART_NONE:
            msg = u"Could not find a status for [[{0}]]".format(title)
            self.logger.warn(msg)
            return

        m_user, m_time, m_id = self._get_modify(pageid)
        s_user, s_time, s_id = self._get_special(pageid, content, chart)
        notes = self._get_notes(chart, content, m_time, s_user)

        query1 = "INSERT INTO row VALUES (?, ?)"
        query2 = "INSERT INTO page VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        query3 = "INSERT INTO updatelog VALUES (?, ?)"
        cursor.execute(query1, (pageid, chart))
        cursor.execute(query2, (pageid, status, title, len(content), notes,
                                m_user, m_time, m_id, s_user, s_time, s_id))
        cursor.execute(query3, (pageid, datetime.utcnow()))

    def _update_page(self, cursor, pageid, title):
        """Update hook for when page is already in our database.

        A variety of SQL queries are used to gather information about the page,
        which is compared against our stored information. Differing information
        is then updated.
        """
        content = self._get_content(pageid)
        if content is None:
            msg = u"Could not get page content for [[{0}]]".format(title)
            self.logger.error(msg)
            return

        namespace = self.site.get_page(title).namespace
        status, chart = self._get_status_and_chart(content, namespace)
        if chart == self.CHART_NONE:
            self._untrack_page(cursor, pageid)
            return

        query = "SELECT * FROM page JOIN row ON page_id = row_id WHERE page_id = ?"
        with self.conn.cursor(oursql.DictCursor) as dict_cursor:
            dict_cursor.execute(query, (pageid,))
            result = dict_cursor.fetchall()[0]

        m_user, m_time, m_id = self._get_modify(pageid)

        if title != result["page_title"]:
            self._update_page_title(cursor, result, pageid, title)

        if m_id != result["page_modify_oldid"]:
            self._update_page_modify(cursor, result, pageid, len(content),
                                     m_user, m_time, m_id)

        if status != result["page_status"]:
            special = self._update_page_status(cursor, result, pageid, content,
                                               status, chart)
            s_user = special[0]
        else:
            s_user = result["page_special_user"]

        notes = self._get_notes(chart, content, m_time, s_user)
        if notes != result["page_notes"]:
            self._update_page_notes(cursor, result, pageid, notes)

        query = "UPDATE updatelog SET update_time = ? WHERE update_id = ?"
        cursor.execute(query, (datetime.utcnow(), pageid))

    ###################### PAGE ATTRIBUTE UPDATE METHODS ######################

    def _update_page_title(self, cursor, result, pageid, title):
        """Update the title of a page in our database."""
        query = "UPDATE page SET page_title = ? WHERE page_id = ?"
        cursor.execute(query, (title, pageid))

        msg = u"  {0}: title: {1} -> {2}"
        self.logger.debug(msg.format(pageid, result["page_title"], title))

    def _update_page_modify(self, cursor, result, pageid, size, m_user, m_time, m_id):
        """Update the last modified information of a page in our database."""
        query = """UPDATE page SET page_size = ?, page_modify_user = ?,
                   page_modify_time = ?, page_modify_oldid = ?
                   WHERE page_id = ?"""
        cursor.execute(query, (size, m_user, m_time, m_id, pageid))

        msg = u"  {0}: modify: {1} / {2} / {3} -> {4} / {5} / {6}"
        msg = msg.format(pageid, result["page_modify_user"],
                         result["page_modify_time"],
                         result["page_modify_oldid"], m_user, m_time, m_id)
        self.logger.debug(msg)

    def _update_page_status(self, cursor, result, pageid, content, status, chart):
        """Update the status and "specialed" information of a page."""
        query1 = """UPDATE page JOIN row ON page_id = row_id
                   SET page_status = ?, row_chart = ? WHERE page_id = ?"""
        query2 = """UPDATE page SET page_special_user = ?,
                   page_special_time = ?, page_special_oldid = ?
                   WHERE page_id = ?"""
        cursor.execute(query1, (status, chart, pageid))

        msg = "  {0}: status: {1} ({2}) -> {3} ({4})"
        self.logger.debug(msg.format(pageid, result["page_status"],
                                     result["row_chart"], status, chart))

        s_user, s_time, s_id = self._get_special(pageid, content, chart)
        if s_id != result["page_special_oldid"]:
            cursor.execute(query2, (s_user, s_time, s_id, pageid))
            msg = u"  {0}: special: {1} / {2} / {3} -> {4} / {5} / {6}"
            msg = msg.format(pageid, result["page_special_user"],
                             result["page_special_time"],
                             result["page_special_oldid"], s_user, s_time, s_id)
            self.logger.debug(msg)

        return s_user, s_time, s_id

    def _update_page_notes(self, cursor, result, pageid, notes):
        """Update the notes (or warnings) of a page in our database."""
        query = "UPDATE page SET page_notes = ? WHERE page_id = ?"
        cursor.execute(query, (notes, pageid))
        msg = "  {0}: notes: {1} -> {2}"
        self.logger.debug(msg.format(pageid, result["page_notes"], notes))

    ###################### DATA RETRIEVAL HELPER METHODS ######################

    def _get_content(self, pageid):
        """Get the current content of a page by ID from the API.

        The page's current revision ID is retrieved from SQL, and then
        an API query is made to get its content. This is the only API query
        used in the task's code.
        """
        query = "SELECT page_latest FROM page WHERE page_id = ?"
        result = self.site.sql_query(query, (pageid,))
        try:
            revid = int(list(result)[0][0])
        except IndexError:
            return None
        return self._get_revision_content(revid)

    def _get_revision_content(self, revid, tries=1):
        """Get the content of a revision by ID from the API."""
        if revid in self.revision_cache:
            return self.revision_cache[revid]
        res = self.site.api_query(action="query", prop="revisions",
                                  revids=revid, rvprop="content")
        try:
            content = res["query"]["pages"].values()[0]["revisions"][0]["*"]
        except KeyError:
            if tries == 0:
                raise
            sleep(5)
            return self._get_revision_content(revid, tries=tries - 1)
        self.revision_cache[revid] = content
        return content

    def _get_status_and_chart(self, content, namespace):
        """Determine the status and chart number of an AFC submission.

        The methodology used here is the same one I've been using for years
        (see also commands.afc_report), but with the new draft system taken
        into account. The order here is important: if there is more than one
        {{AFC submission}} template on a page, we need to know which one to
        use (revision history search to find the most recent isn't a viable
        idea :P).
        """
        statuses = self.get_statuses(content)
        if namespace == wiki.NS_MAIN:
            if statuses:
                return None, self.CHART_MISPLACE
            return "a", self.CHART_ACCEPT
        elif "R" in statuses:
            return "r", self.CHART_REVIEW
        elif "P" in statuses:
            return "p", self.CHART_PEND
        elif "T" in statuses:
            return None, self.CHART_NONE
        elif "D" in statuses:
            return "d", self.CHART_DECLINE
        return None, self.CHART_NONE

    def get_statuses(self, content):
        """Return a list of all AFC submission statuses in a page's text."""
        valid = ["P", "R", "T", "D"]
        aliases = {
            "submit": "P",
            "afc submission/submit": "P",
            "afc submission/reviewing": "R",
            "afc submission/pending": "P",
            "afc submission/draft": "T",
            "afc submission/declined": "D"
        }
        statuses = []
        code = mwparserfromhell.parse(content)
        for template in code.filter_templates():
            name = template.name.strip().lower()
            if name == "afc submission":
                if template.has(1, ignore_empty=True):
                    status = template.get(1).value.strip().upper()
                    statuses.append(status if status in valid else "P")
                else:
                    statuses.append("P")
            elif name in aliases:
                statuses.append(aliases[name])
        return statuses

    def _get_modify(self, pageid):
        """Return information about a page's last edit ("modification").

        This consists of the most recent editor, modification time, and the
        lastest revision ID.
        """
        query = """SELECT rev_user_text, rev_timestamp, rev_id FROM revision
                   JOIN page ON rev_id = page_latest WHERE page_id = ?"""
        result = self.site.sql_query(query, (pageid,))
        m_user, m_time, m_id = list(result)[0]
        timestamp = datetime.strptime(m_time, "%Y%m%d%H%M%S")
        return m_user.decode("utf8"), timestamp, m_id

    def _get_special(self, pageid, content, chart):
        """Return information about a page's "special" edit.

        I tend to use the term "special" as a verb a lot, which is bound to
        cause confusion. It is merely a short way of saying "the edit in which
        a declined submission was declined, an accepted submission was
        accepted, a submission in review was set as such, a pending submission
        was submitted, and a "misplaced" submission was created."

        This "information" consists of the special edit's editor, its time, and
        its revision ID. If the page's status is not something that involves
        "special"-ing, we will return None for all three. The same will be
        returned if we cannot determine when the page was "special"-ed.
        """
        charts = {
            self.CHART_NONE: (lambda pageid, content: None, None, None),
            self.CHART_MISPLACE: self.get_create,
            self.CHART_ACCEPT: self.get_accepted,
            self.CHART_REVIEW: self.get_reviewing,
            self.CHART_PEND: self.get_pending,
            self.CHART_DECLINE: self.get_decline
        }
        return charts[chart](pageid, content)

    def get_create(self, pageid, content=None):
        """Return (creator, create_ts, create_revid) for the given page."""
        query = """SELECT rev_user_text, rev_timestamp, rev_id
                   FROM revision WHERE rev_id =
                   (SELECT MIN(rev_id) FROM revision WHERE rev_page = ?)"""
        result = self.site.sql_query(query, (pageid,))
        c_user, c_time, c_id = list(result)[0]
        timestamp = datetime.strptime(c_time, "%Y%m%d%H%M%S")
        return c_user.decode("utf8"), timestamp, c_id

    def get_accepted(self, pageid, content=None):
        """Return (acceptor, accept_ts, accept_revid) for the given page."""
        query = """SELECT rev_user_text, rev_timestamp, rev_id FROM revision
                   WHERE rev_comment LIKE "% moved page [[%]] to [[%]]%"
                   AND rev_page = ? ORDER BY rev_timestamp DESC LIMIT 1"""
        result = self.site.sql_query(query, (pageid,))
        try:
            a_user, a_time, a_id = list(result)[0]
        except IndexError:
            return None, None, None
        timestamp = datetime.strptime(a_time, "%Y%m%d%H%M%S")
        return a_user.decode("utf8"), timestamp, a_id

    def get_reviewing(self, pageid, content=None):
        """Return (reviewer, review_ts, review_revid) for the given page."""
        return self._search_history(pageid, self.CHART_REVIEW, ["R"], [])

    def get_pending(self, pageid, content):
        """Return (submitter, submit_ts, submit_revid) for the given page."""
        res = self._get_status_helper(pageid, content, ("P", ""), ("u", "ts"))
        return res or self._search_history(pageid, self.CHART_PEND, ["P"], [])

    def get_decline(self, pageid, content):
        """Return (decliner, decline_ts, decline_revid) for the given page."""
        params = ("decliner", "declinets")
        res = self._get_status_helper(pageid, content, ("D"), params)
        return res or self._search_history(
            pageid, self.CHART_DECLINE, ["D"], ["R", "P", "T"])

    def _get_status_helper(self, pageid, content, statuses, params):
        """Helper function for get_pending() and get_decline()."""
        submits = []
        code = mwparserfromhell.parse(content)
        for tmpl in code.filter_templates():
            status = tmpl.get(1).value.strip().upper() if tmpl.has(1) else "P"
            if tmpl.name.strip().lower() == "afc submission":
                if all([tmpl.has(par, ignore_empty=True) for par in params]):
                    if status in statuses:
                        data = [unicode(tmpl.get(par).value) for par in params]
                        submits.append(data)
        if not submits:
            return None
        user, stamp = max(submits, key=lambda pair: pair[1])

        query = """SELECT rev_id FROM revision WHERE rev_page = ?
                   AND rev_user_text = ? AND ABS(rev_timestamp - ?) <= 60
                   ORDER BY ABS(rev_timestamp - ?) ASC LIMIT 1"""
        result = self.site.sql_query(query, (pageid, user, stamp, stamp))
        try:
            dtime = datetime.strptime(stamp, "%Y%m%d%H%M%S")
            return user, dtime, list(result)[0][0]
        except (ValueError, IndexError):
            return None

    def _search_history(self, pageid, chart, search_with, search_without):
        """Search through a page's history to find when a status was set.

        Linear search backwards in time for the edit right after the most
        recent edit that fails the (pseudocode) test:

        ``status_set(any(search_with)) && !status_set(any(search_without))``
        """
        query = """SELECT rev_user_text, rev_timestamp, rev_id
                   FROM revision WHERE rev_page = ? ORDER BY rev_id DESC"""
        result = self.site.sql_query(query, (pageid,))

        counter = 0
        last = (None, None, None)
        for user, ts, revid in result:
            counter += 1
            if counter > 50:
                msg = "Exceeded 50 content lookups while searching history of page (id: {0}, chart: {1})"
                self.logger.warn(msg.format(pageid, chart))
                return None, None, None
            try:
                content = self._get_revision_content(revid)
            except exceptions.APIError:
                msg = "API error interrupted SQL query in _search_history() for page (id: {0}, chart: {1})"
                self.logger.exception(msg.format(pageid, chart))
                return None, None, None
            statuses = self.get_statuses(content)
            req = search_with and not any([s in statuses for s in search_with])
            if any([s in statuses for s in search_without]) or req:
                return last
            timestamp = datetime.strptime(ts, "%Y%m%d%H%M%S")
            last = (user.decode("utf8"), timestamp, revid)

        return last

    def _get_notes(self, chart, content, m_time, s_user):
        """Return any special notes or warnings about this page.

        copyvio:    submission is a suspected copyright violation
        unsourced:  submission lacks references completely
        no-inline:  submission has no inline citations
        short:      submission is less than a kilobyte in length
        resubmit:   submission was resubmitted after a previous decline
        old:        submission has not been touched in > 4 days
        blocked:    submitter is currently blocked
        """
        notes = ""

        ignored_charts = [self.CHART_NONE, self.CHART_ACCEPT, self.CHART_DECLINE]
        if chart in ignored_charts:
            return notes

        copyvios = self.config.tasks.get("afc_copyvios", {})
        regex = r"\{\{s*" + copyvios.get("template", "AfC suspected copyvio")
        if re.search(regex, content):
            notes += "|nc=1"  # Submission is a suspected copyvio

        if not re.search(r"\<ref\s*(.*?)\>(.*?)\</ref\>", content, re.I|re.S):
            regex = r"(https?:)|\[//(?!{0})([^ \]\t\n\r\f\v]+?)"
            sitedomain = re.escape(self.site.domain)
            if re.search(regex.format(sitedomain), content, re.I | re.S):
                notes += "|ni=1"  # Submission has no inline citations
            else:
                notes += "|nu=1"  # Submission is completely unsourced

        if len(content) < 1000:
            notes += "|ns=1"  # Submission is short

        statuses = self.get_statuses(content)
        if "D" in statuses and chart != self.CHART_MISPLACE:
            notes += "|nr=1"  # Submission was resubmitted

        time_since_modify = (datetime.utcnow() - m_time).total_seconds()
        max_time = 4 * 24 * 60 * 60
        if time_since_modify > max_time:
            notes += "|no=1"  # Submission hasn't been touched in over 4 days

        if chart == self.CHART_PEND and s_user:
            submitter = self.site.get_user(s_user)
            try:
                if submitter.blockinfo:
                    notes += "|nb=1"  # Submitter is blocked
            except exceptions.UserNotFoundError:  # Likely an IP
                pass

        return notes
