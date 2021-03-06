import re
import pymysql.cursors
from .util import setdocstring

# Thank you MySQLdb for the kind regex
restr = r"""
    \s
    values
    \s*
    (
        \(
            [^()']*
            (?:
                (?:
                        (?:\(
                            # ( - editor hightlighting helper
                            [^)]*
                        \))
                    |
                        '
                            [^\\']*
                            (?:\\.[^\\']*)*
                        '
                )
                [^()']*
            )*
        \)
    )
"""

insert_values = re.compile(restr, re.S | re.I | re.X)


def _flatten(alist):
    result = []
    map(result.extend, alist)
    return tuple(result)


class Cursor(pymysql.cursors.Cursor):

    @setdocstring(pymysql.cursors.Cursor.execute)
    def execute(self, query, args=None):
        if args is None:
            args = ()
        elif not isinstance(args, (tuple, list, dict)):
            args = (args,)

        result = 0
        result = self._query(query, args)
        self._executed = query
        return result

    @setdocstring(pymysql.cursors.Cursor.executemany)
    def executemany(self, query, args):
        if not args:
            return
        db = self._get_db()
        charset = db.charset
        if isinstance(query, unicode):
            query = query.encode(charset)

        m = insert_values.search(query)
        if not m:
            self.rowcount = sum([self.execute(query, arg) for arg in args])
            return self.rowcount

        # Speed up a bulk insert MySQLdb style
        p = m.start(1)
        e = m.end(1)
        qv = m.group(1)
        sql_params = (qv for i in range(len(args)))
        multirow_query = '\n'.join([query[:p], ','.join(sql_params), query[e:]])
        return self.execute(multirow_query, _flatten(args))

    def _query(self, query, args=()):
        conn = self._get_db()
        conn.query(query, args)
        self.rowcount = conn._result.affected_rows
        self.rownumber = 0
        self.description = conn._result.description
        self.lastrowid = conn._result.insert_id
        self._rows = conn._result.rows
        self._has_next = 0
        return self.rowcount
        

class DictCursor(Cursor):

    """A cursor which returns results as a dictionary"""

    def execute(self, query, args=None):
        result = super(DictCursor, self).execute(query, args)
        if self.description:
            self._fields = [field[0] for field in self.description]
        return result

    def fetchone(self):
        ''' Fetch the next row '''
        self._check_executed()
        if self._rows is None or self.rownumber >= len(self._rows):
            return None
        result = dict(zip(self._fields, self._rows[self.rownumber]))
        self.rownumber += 1
        return result

    def fetchmany(self, size=None):
        ''' Fetch several rows '''
        self._check_executed()
        if self._rows is None:
            return None
        end = self.rownumber + (size or self.arraysize)
        result = [dict(zip(self._fields, r))
                  for r in self._rows[self.rownumber:end]]
        self.rownumber = min(end, len(self._rows))
        return tuple(result)

    def fetchall(self):
        ''' Fetch all the rows '''
        self._check_executed()
        if self._rows is None:
            return None
        if self.rownumber:
            result = [dict(zip(self._fields, r))
                      for r in self._rows[self.rownumber:]]
        else:
            result = [dict(zip(self._fields, r)) for r in self._rows]
        self.rownumber = len(self._rows)
        return tuple(result)
