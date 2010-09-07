#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
import vobject
import urllib
from DAV.errors import DAV_NotFound, DAV_Forbidden
from trytond.model import ModelView, ModelSQL
from trytond.tools import reduce_ids
from trytond.cache import Cache
from trytond.transaction import Transaction

CALDAV_NS = 'urn:ietf:params:xml:ns:caldav'


class Collection(ModelSQL, ModelView):

    _name = "webdav.collection"

    def calendar(self, uri, ics=False):
        '''
        Return the calendar id in the uri or False

        :param uri: the uri
        :return: calendar id
            or False if there is no calendar
        '''
        calendar_obj = self.pool.get('calendar.calendar')

        if uri and uri.startswith('Calendars/'):
            calendar, uri = (uri[10:].split('/', 1) + [None])[0:2]
            if ics:
                if calendar.endswith('.ics'):
                    calendar = calendar[:-4]
                else:
                    return False
            return calendar_obj.get_name(calendar)
        return False

    @Cache('webdav_collection.event')
    def event(self, uri, calendar_id=False):
        '''
        Return the event id in the uri or False

        :param uri: the uri
        :param calendar_id: the calendar id
        :return: event id
            or False if there is no event
        '''
        event_obj = self.pool.get('calendar.event')

        if uri and uri.startswith('Calendars/'):
            calendar, event_uri = (uri[10:].split('/', 1) + [None])[0:2]
            if not calendar_id:
                calendar_id = self.calendar(uri)
                if not calendar_id:
                    return False
            event_ids = event_obj.search([
                ('calendar', '=', calendar_id),
                ('uuid', '=', event_uri[:-4]),
                ('parent', '=', False),
                ], limit=1)
            if event_ids:
                return event_ids[0]
        return False

    def _caldav_filter_domain_calendar(self, filter):
        '''
        Return a domain for caldav filter on calendar

        :param filter: the DOM Element of filter
        :return: a list for domain
        '''
        if not filter:
            return []
        if filter.localName == 'principal-property-search':
            return [('id', '=', 0)]
        return [('id', '=', 0)]

    def _caldav_filter_domain_event(self, filter):
        '''
        Return a domain for caldav filter on event

        :param filter: the DOM Element of filter
        :return: a list for domain
        '''
        res = []
        if not filter:
            return []
        if filter.localName == 'principal-property-search':
            return [('id', '=', 0)]
        elif filter.localName == 'calendar-query':
            calendar_filter = None
            for e in filter.childNodes:
                if e.nodeType == e.TEXT_NODE:
                    continue
                if e.localName == 'filter':
                    calendar_filter = e
                    break
            if calendar_filter is None:
                return []
            for vcalendar_filter in calendar_filter.childNodes:
                if vcalendar_filter.nodeType == vcalendar_filter.TEXT_NODE:
                    continue
                if vcalendar_filter.getAttribute('name') != 'VCALENDAR':
                    return [('id', '=', 0)]
                vevent_filter = None
                for vevent_filter in vcalendar_filter.childNodes:
                    if vevent_filter.nodeType == vevent_filter.TEXT_NODE:
                        vevent_filter = None
                        continue
                    if vevent_filter.localName == 'comp-filter':
                        if vevent_filter.getAttribute('name') != 'VEVENT':
                            vevent_filter = None
                            continue
                        break
                if vevent_filter is None:
                    return [('id', '=', 0)]
                break
            return []
        elif filter.localName == 'calendar-multiget':
            ids = []
            for e in filter.childNodes:
                if e.nodeType == e.TEXT_NODE:
                    continue
                if e.localName == 'href':
                    if not e.firstChild:
                        continue
                    uri = e.firstChild.data
                    dbname, uri = (uri.lstrip('/').split('/', 1) + [None])[0:2]
                    if not dbname:
                        continue
                    dbname == urllib.unquote_plus(dbname)
                    if dbname != Transaction().cursor.database_name:
                        continue
                    if uri:
                        uri = urllib.unquote_plus(uri)
                    event_id = self.event(uri)
                    if event_id:
                        ids.append(event_id)
            return [('id', 'in', ids)]
        return res

    def get_childs(self, uri, filter=None, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        event_obj = self.pool.get('calendar.event')

        if uri in ('Calendars', 'Calendars/'):
            domain = self._caldav_filter_domain_calendar(filter)
            domain = [['OR', ('owner', '=', Transaction().user), ('read_users', '=', Transaction().user)],
                    domain]
            calendar_ids = calendar_obj.search(domain)
            calendars = calendar_obj.browse(calendar_ids)
            if cache is not None:
                cache.setdefault('_calendar', {})
                cache['_calendar'].setdefault(calendar_obj._name, {})
                for calendar_id in calendar_ids:
                    cache['_calendar'][calendar_obj._name][calendar_id] = {}
            return [x.name for x in calendars] + \
                    [x.name + '.ics' for x in calendars]
        if uri and uri.startswith('Calendars/'):
            calendar_id = self.calendar(uri)
            if  calendar_id and not (uri[10:].split('/', 1) + [None])[1]:
                domain = self._caldav_filter_domain_event(filter)
                event_ids = event_obj.search([
                    ('calendar', '=', calendar_id),
                    domain,
                    ])
                events = event_obj.browse(event_ids)
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(event_obj._name, {})
                    for event_id in event_ids:
                        cache['_calendar'][event_obj._name][event_id] = {}
                return [x.uuid + '.ics' for x in events]
            return []
        res = super(Collection, self).get_childs(uri, filter=filter,
                cache=cache)
        if not uri and not filter:
            res.append('Calendars')
        elif not uri and filter:
            if filter.localName == 'principal-property-search':
                res.append('Calendars')
        return res

    def get_resourcetype(self, uri, cache=None):
        from DAV.constants import COLLECTION, OBJECT
        if uri in ('Calendars', 'Calendars/'):
            return COLLECTION
        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return COLLECTION
            return OBJECT
        elif self.calendar(uri, ics=True):
            return OBJECT
        return super(Collection, self).get_resourcetype(uri, cache=cache)

    def get_displayname(self, uri, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        if uri in ('Calendars', 'Calendars/'):
            return 'Calendars'
        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return calendar_obj.browse(calendar_id).rec_name
            return uri.split('/')[-1]
        elif self.calendar(uri, ics=True):
            return uri.split('/')[-1]
        return super(Collection, self).get_displayname(uri, cache=cache)

    def get_contenttype(self, uri, cache=None):
        if self.event(uri) \
                or self.calendar(uri, ics=True):
            return 'text/calendar'
        return super(Collection, self).get_contenttype(uri, cache=cache)

    def get_creationdate(self, uri, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        event_obj = self.pool.get('calendar.event')

        calendar_id = self.calendar(uri)
        if not calendar_id:
            calendar_id = self.calendar(uri, ics=True)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(calendar_obj._name, {})
                    ids = cache['_calendar'][calendar_obj._name].keys()
                    if calendar_id not in ids:
                        ids.append(calendar_id)
                    elif 'creationdate' in cache['_calendar']\
                            [calendar_obj._name][calendar_id]:
                        return cache['_calendar'][calendar_obj._name]\
                                [calendar_id]['creationdate']
                else:
                    ids = [calendar_id]
                res = None
                cursor = Transaction().cursor
                for i in range(0, len(ids), cursor.IN_MAX):
                    sub_ids = ids[i:i + cursor.IN_MAX]
                    red_sql, red_ids = reduce_ids('id', sub_ids)
                    cursor.execute('SELECT id, ' \
                                'EXTRACT(epoch FROM create_date) ' \
                            'FROM "' + calendar_obj._table + '" ' \
                            'WHERE ' + red_sql, red_ids)
                    for calendar_id2, date in cursor.fetchall():
                        if calendar_id2 == calendar_id:
                            res = date
                        if cache is not None:
                            cache['_calendar'][calendar_obj._name]\
                                    .setdefault(calendar_id2, {})
                            cache['_calendar'][calendar_obj._name]\
                                    [calendar_id2]['creationdate'] = date
                if res is not None:
                    return res
            else:
                event_id = self.event(uri, calendar_id=calendar_id)
                if event_id:
                    if cache is not None:
                        cache.setdefault('_calendar', {})
                        cache['_calendar'].setdefault(event_obj._name, {})
                        ids = cache['_calendar'][event_obj._name].keys()
                        if event_id not in ids:
                            ids.append(event_id)
                        elif 'creationdate' in cache['_calendar']\
                                [event_obj._name][event_id]:
                            return cache['_calendar'][event_obj._name]\
                                    [event_id]['creationdate']
                    else:
                        ids = [event_id]
                    res = None
                    cursor = Transaction().cursor
                    for i in range(0, len(ids), cursor.IN_MAX):
                        sub_ids = ids[i:i + cursor.IN_MAX]
                        red_sql, red_ids = reduce_ids('id', sub_ids)
                        cursor.execute('SELECT id, ' \
                                'EXTRACT(epoch FROM create_date) ' \
                            'FROM "' + event_obj._table + '" ' \
                            'WHERE ' + red_sql, red_ids)
                        for event_id2, date in cursor.fetchall():
                            if event_id2 == event_id:
                                res = date
                            if cache is not None:
                                cache['_calendar'][event_obj._name]\
                                        .setdefault(event_id2, {})
                                cache['_calendar'][event_obj._name]\
                                        [event_id2]['creationdate'] = date
                    if res is not None:
                        return res
        return super(Collection, self).get_creationdate(uri, cache=cache)

    def get_lastmodified(self, uri, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        event_obj = self.pool.get('calendar.event')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(calendar_obj._name, {})
                    ids = cache['_calendar'][calendar_obj._name].keys()
                    if calendar_id not in ids:
                        ids.append(calendar_id)
                    elif 'lastmodified' in cache['_calendar']\
                            [calendar_obj._name][calendar_id]:
                        return cache['_calendar'][calendar_obj._name]\
                                [calendar_id]['lastmodified']
                else:
                    ids = [calendar_id]
                res = None
                for i in range(0, len(ids), cursor.IN_MAX):
                    sub_ids = ids[i:i + cursor.IN_MAX]
                    red_sql, red_ids = reduce_ids('id', sub_ids)
                    cursor.execute('SELECT id, ' \
                                'EXTRACT(epoch FROM ' \
                                'COALESCE(write_date, create_date)) ' \
                            'FROM "' + calendar_obj._table + '" ' \
                                'WHERE ' + red_sql, red_ids)
                    for calendar_id2, date in cursor.fetchall():
                        if calendar_id2 == calendar_id:
                            res = date
                        if cache is not None:
                            cache['_calendar'][calendar_obj._name]\
                                    .setdefault(calendar_id2, {})
                            cache['_calendar'][calendar_obj._name]\
                                    [calendar_id2]['lastmodified'] = date
                if res is not None:
                    return res
            else:
                event_id = self.event(uri, calendar_id=calendar_id)
                if event_id:
                    if cache is not None:
                        cache.setdefault('_calendar', {})
                        cache['_calendar'].setdefault(event_obj._name, {})
                        ids = cache['_calendar'][event_obj._name].keys()
                        if event_id not in ids:
                            ids.append(event_id)
                        elif 'lastmodified' in cache['_calendar']\
                                [event_obj._name][event_id]:
                            return cache['_calendar'][event_obj._name]\
                                    [event_id]['lastmodified']
                    else:
                        ids = [event_id]
                    res = None
                    cursor = Transaction().cursor
                    for i in range(0, len(ids), cursor.IN_MAX/2):
                        sub_ids = ids[i:i + cursor.IN_MAX/2]
                        red_id_sql, red_id_ids = reduce_ids('id', sub_ids)
                        red_parent_sql, red_parent_ids = reduce_ids('parent',
                                sub_ids)
                        cursor.execute('SELECT COALESCE(parent, id), ' \
                                    'MAX(EXTRACT(epoch FROM ' \
                                    'COALESCE(write_date, create_date))) ' \
                                'FROM "' + event_obj._table + '" ' \
                                'WHERE ' + red_id_sql + ' ' \
                                    'OR ' + red_parent_sql + ' ' \
                                'GROUP BY parent, id',
                                red_id_ids + red_parent_ids)
                        for event_id2, date in cursor.fetchall():
                            if event_id2 == event_id:
                                res = date
                            if cache is not None:
                                cache['_calendar'][event_obj._name]\
                                        .setdefault(event_id2, {})
                                cache['_calendar'][event_obj._name]\
                                        [event_id2]['lastmodified'] = date
                    if res is not None:
                        return res
        calendar_ics_id = self.calendar(uri, ics=True)
        if calendar_ics_id:
            if cache is not None:
                cache.setdefault('_calendar', {})
                cache['_calendar'].setdefault(calendar_obj._name, {})
                ids = cache['_calendar'][calendar_obj._name].keys()
                if calendar_ics_id not in ids:
                    ids.append(calendar_ics_id)
                elif 'lastmodified ics' in cache['_calendar']\
                        [calendar_obj._name][calendar_ics_id]:
                    return cache['_calendar'][calendar_obj._name]\
                            [calendar_ics_id]['lastmodified ics']
            else:
                ids = [calendar_ics_id]
            res = None
            cursor = Transaction().cursor
            for i in range(0, len(ids), cursor.IN_MAX):
                sub_ids = ids[i:i + cursor.IN_MAX]
                red_sql, red_ids = reduce_ids('calendar', sub_ids)
                cursor.execute('SELECT calendar, MAX(EXTRACT(epoch FROM ' \
                            'COALESCE(write_date, create_date))) ' \
                        'FROM "' + event_obj._table + '" ' \
                        'WHERE ' + red_sql + ' ' \
                        'GROUP BY calendar', red_ids)
                for calendar_id2, date in cursor.fetchall():
                    if calendar_id2 == calendar_ics_id:
                        res = date
                    if cache is not None:
                        cache['_calendar'][calendar_obj._name]\
                                .setdefault(calendar_id2, {})
                        cache['_calendar'][calendar_obj._name]\
                                [calendar_id2]['lastmodified ics'] = date
            if res is not None:
                return res
        return super(Collection, self).get_lastmodified(uri, cache=cache)

    def get_data(self, uri, cache=None):
        event_obj = self.pool.get('calendar.event')
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_NotFound
            event_id = self.event(uri, calendar_id=calendar_id)
            if not event_id:
                raise DAV_NotFound
            ical = event_obj.event2ical(event_id)
            return ical.serialize()
        calendar_ics_id = self.calendar(uri, ics=True)
        if calendar_ics_id:
            ical = calendar_obj.calendar2ical(calendar_ics_id)
            return ical.serialize()
        return super(Collection, self).get_data(uri, cache=cache)

    def get_calendar_description(self, uri, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(calendar_obj._name, {})
                    ids = cache['_calendar'][calendar_obj._name].keys()
                    if calendar_id not in ids:
                        ids.append(calendar_id)
                    elif 'calendar_description' in cache['_calendar']\
                            [calendar_obj._name][calendar_id]:
                        res = cache['_calendar'][calendar_obj._name]\
                                [calendar_id]['calendar_description']
                        if res is not None:
                            return res
                else:
                    ids = [calendar_id]
                res = None
                for calendar in calendar_obj.browse(ids):
                    if calendar.id == calendar_id:
                        res = calendar.description
                    if cache is not None:
                        cache['_calendar'][calendar_obj._name]\
                                .setdefault(calendar.id, {})
                        cache['_calendar'][calendar_obj._name]\
                                [calendar.id]['calendar_description'] = \
                                calendar.description
                if res is not None:
                    return res
        raise DAV_NotFound

    def get_calendar_data(self, uri, cache=None):
        return self.get_data(uri, cache=cache).decode('utf-8')

    def get_calendar_home_set(self, uri, cache=None):
        return '/Calendars'

    def get_calendar_user_address_set(self, uri, cache=None):
        user_obj = self.pool.get('res.user')
        user = user_obj.browse(Transaction().user)
        if user.email:
            return user.email
        raise DAV_NotFound

    def get_schedule_inbox_URL(self, uri, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_ids = calendar_obj.search([
            ('owner', '=', user),
            ], limit=1)
        if not calendar_ids:
            # Sunbird failed with no value
            return '/Calendars'
        calendar = calendar_obj.browse(calendar_ids[0])
        return '/Calendars/' + calendar.name

    def get_schedule_outbox_URL(self, uri, cache=None):
        return self.get_schedule_inbox_URL(uri, cache=cache)

    def put(self, uri, data, content_type, cache=None):
        event_obj = self.pool.get('calendar.event')
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_Forbidden
            event_id = self.event(uri, calendar_id=calendar_id)
            if not event_id:
                ical = vobject.readOne(data)
                values = event_obj.ical2values(None, ical, calendar_id)
                event_id = event_obj.create(values)
                event = event_obj.browse(event_id)
                calendar = calendar_obj.browse(calendar_id)
                return (Transaction().cursor.database_name + '/Calendars/' +
                        calendar.name + '/' + event.uuid + '.ics')
            else:
                ical = vobject.readOne(data)
                values = event_obj.ical2values(event_id, ical, calendar_id)
                event_obj.write(event_id, values)
                return
        calendar_ics_id = self.calendar(uri, ics=True)
        if calendar_ics_id:
            raise DAV_Forbidden
        return super(Collection, self).put(uri, data, content_type)

    def mkcol(self, uri, cache=None):
        if uri and uri.startswith('Calendars/'):
            raise DAV_Forbidden
        return super(Collection, self).mkcol(uri, cache=cache)

    def rmcol(self, uri, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                try:
                    calendar_obj.delete(calendar_id)
                except Exception:
                    raise DAV_Forbidden
                return 200
            raise DAV_Forbidden
        return super(Collection, self).rmcol(uri, cache=cache)

    def rm(self, uri, cache=None):
        event_obj = self.pool.get('calendar.event')

        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return 403
            event_id = self.event(uri, calendar_id=calendar_id)
            if event_id:
                try:
                    event_obj.delete(event_id)
                except Exception:
                    return 403
                return 200
            return 404
        calendar_ics_id = self.calendar(uri, ics=True)
        if calendar_ics_id:
            return 403
        return super(Collection, self).rm(uri, cache=cache)

    def exists(self, uri, cache=None):
        if uri in ('Calendars', 'Calendars/'):
            return 1
        calendar_id = self.calendar(uri)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return 1
            if self.event(uri, calendar_id=calendar_id):
                return 1
        calendar_ics_id = self.calendar(uri, ics=True)
        if calendar_ics_id:
            return 1
        return super(Collection, self).exists(uri, cache=cache)

    def current_user_privilege_set(self, uri, cache=None):
        '''
        Return the privileges of the current user for uri
        Privileges ares: create, read, write, delete

        :param uri: the uri
        :param cache: the cache
        :return: a list of privileges
        '''
        calendar_obj = self.pool.get('calendar.calendar')

        if uri in ('Calendars', 'Calendars/'):
            return ['create', 'read', 'write', 'delete']
        if uri and uri.startswith('Calendars/'):
            calendar_id = self.calendar(uri)
            if calendar_id:
                calendar = calendar_obj.browse(calendar_id)
                if user == calendar.owner.id:
                    return ['create', 'read', 'write', 'delete']
                res = []
                if user in (x.id for x in calendar.read_users):
                    res.append('read')
                if user in (x.id for x in calendar.write_users):
                    res.extend(['read', 'write', 'delete'])
                return res
            return []
        return super(Collection, self).current_user_privilege_set(uri,
                cache=cache)

Collection()
