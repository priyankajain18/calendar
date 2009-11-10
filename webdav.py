#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelView, ModelSQL
from trytond.tools import Cache, reduce_ids
from DAV.errors import DAV_NotFound, DAV_Forbidden
import vobject
import urllib

CALDAV_NS = 'urn:ietf:params:xml:ns:caldav'


class Collection(ModelSQL, ModelView):

    _name = "webdav.collection"

    def calendar(self, cursor, user, uri, ics=False, context=None):
        '''
        Return the calendar id in the uri or False

        :param cursor: the database cursor
        :param user: the user id
        :param uri: the uri
        :param context: the context
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
            return calendar_obj.get_name(cursor, user, calendar, context=context)
        return False

    def event(self, cursor, user, uri, calendar_id=False, context=None):
        '''
        Return the event id in the uri or False

        :param cursor: the database cursor
        :param user: the user id
        :param uri: the uri
        :param calendar_id: the calendar id
        :param context: the context
        :return: event id
            or False if there is no event
        '''
        event_obj = self.pool.get('calendar.event')

        if uri and uri.startswith('Calendars/'):
            calendar, event_uri = (uri[10:].split('/', 1) + [None])[0:2]
            if not calendar_id:
                calendar_id = self.calendar(cursor, user, uri, context=context)
                if not calendar_id:
                    return False
            event_ids = event_obj.search(cursor, user, [
                ('calendar', '=', calendar_id),
                ('uuid', '=', event_uri[:-4]),
                ('parent', '=', False),
                ], limit=1, context=context)
            if event_ids:
                return event_ids[0]
        return False

    event = Cache('webdav_collection.event')(event)

    def _caldav_filter_domain_calendar(self, cursor, user, filter, context=None):
        '''
        Return a domain for caldav filter on calendar

        :param cursor: the database cursor
        :param user: the user id
        :param filter: the DOM Element of filter
        :param context: the context
        :return: a list for domain
        '''
        if not filter:
            return []
        if filter.localName == 'principal-property-search':
            return [('id', '=', 0)]
        return [('id', '=', 0)]

    def _caldav_filter_domain_event(self, cursor, user, filter, context=None):
        '''
        Return a domain for caldav filter on event

        :param cursor: the database cursor
        :param user: the user id
        :param filter: the DOM Element of filter
        :param context: the context
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
                    if dbname != cursor.database_name:
                        continue
                    if uri:
                        uri = urllib.unquote_plus(uri)
                    event_id = self.event(cursor, user, uri, context=context)
                    if event_id:
                        ids.append(event_id)
            return [('id', 'in', ids)]
        return res

    def get_childs(self, cursor, user, uri, filter=None, context=None,
            cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        event_obj = self.pool.get('calendar.event')

        if uri in ('Calendars', 'Calendars/'):
            domain = self._caldav_filter_domain_calendar(cursor, user,
                    filter, context=context)
            domain = [['OR', ('owner', '=', user), ('read_users', '=', user)],
                    domain]
            calendar_ids = calendar_obj.search(cursor, user, domain,
                    context=context)
            calendars = calendar_obj.browse(cursor, user, calendar_ids,
                    context=context)
            if cache is not None:
                cache.setdefault('_calendar', {})
                cache['_calendar'].setdefault(calendar_obj._name, {})
                for calendar_id in calendar_ids:
                    cache['_calendar'][calendar_obj._name][calendar_id] = {}
            return [x.name for x in calendars] + \
                    [x.name + '.ics' for x in calendars]
        if uri and uri.startswith('Calendars/'):
            calendar_id = self.calendar(cursor, user, uri, context=context)
            if  calendar_id and not (uri[10:].split('/', 1) + [None])[1]:
                domain = self._caldav_filter_domain_event(cursor, user, filter,
                        context=context)
                event_ids = event_obj.search(cursor, user, [
                    ('calendar', '=', calendar_id),
                    domain,
                    ], context=context)
                events = event_obj.browse(cursor, user, event_ids,
                        context=context)
                if cache is not None:
                    cache.setdefault('_calendar', {})
                    cache['_calendar'].setdefault(event_obj._name, {})
                    for event_id in event_ids:
                        cache['_calendar'][event_obj._name][event_id] = {}
                return [x.uuid + '.ics' for x in events]
            return []
        res = super(Collection, self).get_childs(cursor, user, uri,
                filter=filter, context=context, cache=cache)
        if not uri and not filter:
            res.append('Calendars')
        elif not uri and filter:
            if filter.localName == 'principal-property-search':
                res.append('Calendars')
        return res

    def get_resourcetype(self, cursor, user, uri, context=None, cache=None):
        from DAV.constants import COLLECTION, OBJECT
        if uri in ('Calendars', 'Calendars/'):
            return COLLECTION
        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return COLLECTION
            return OBJECT
        elif self.calendar(cursor, user, uri, ics=True, context=context):
            return OBJECT
        return super(Collection, self).get_resourcetype(cursor, user, uri,
                context=context, cache=cache)

    def get_contenttype(self, cursor, user, uri, context=None, cache=None):
        if self.event(cursor, user, uri, context=context) \
                or self.calendar(cursor, user, uri, ics=True, context=context):
            return 'text/calendar'
        return super(Collection, self).get_contenttype(cursor, user, uri,
                context=context, cache=cache)

    def get_creationdate(self, cursor, user, uri, context=None, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        event_obj = self.pool.get('calendar.event')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if not calendar_id:
            calendar_id = self.calendar(cursor, user, uri, ics=True,
                    context=context)
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
                event_id = self.event(cursor, user, uri, calendar_id=calendar_id,
                        context=context)
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
        return super(Collection, self).get_creationdate(cursor, user, uri,
                context=context, cache=cache)

    def get_lastmodified(self, cursor, user, uri, context=None, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        event_obj = self.pool.get('calendar.event')

        calendar_id = self.calendar(cursor, user, uri, context=context)
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
                event_id = self.event(cursor, user, uri, calendar_id=calendar_id,
                        context=context)
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
        calendar_ics_id = self.calendar(cursor, user, uri, ics=True,
                context=context)
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
        return super(Collection, self).get_lastmodified(cursor, user, uri,
                context=context, cache=cache)

    def get_data(self, cursor, user, uri, context=None, cache=None):
        event_obj = self.pool.get('calendar.event')
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_NotFound
            event_id = self.event(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            if not event_id:
                raise DAV_NotFound
            ical = event_obj.event2ical(cursor, user, event_id, context=context)
            return ical.serialize()
        calendar_ics_id = self.calendar(cursor, user, uri, ics=True,
                context=context)
        if calendar_ics_id:
            ical = calendar_obj.calendar2ical(cursor, user, calendar_ics_id,
                    context=context)
            return ical.serialize()
        return super(Collection, self).get_data(cursor, user, uri,
                context=context, cache=cache)

    def get_calendar_description(self, cursor, user, uri, context=None,
            cache=None):
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(cursor, user, uri, context=context)
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
                for calendar in calendar_obj.browse(cursor, user, ids,
                        context=context):
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

    def get_calendar_data(self, cursor, user, uri, context=None, cache=None):
        return self.get_data(cursor, user, uri, context=context, cache=cache)\
                .decode('utf-8')

    def get_calendar_home_set(self, cursor, user, uri, context=None,
            cache=None):
        return '/Calendars'

    def get_calendar_user_address_set(self, cursor, user_id, uri, context=None,
            cache=None):
        user_obj = self.pool.get('res.user')
        user = user_obj.browse(cursor, user_id, user_id, context=context)
        if user.email:
            return user.email
        raise DAV_NotFound

    def get_schedule_inbox_URL(self, cursor, user, uri, context=None,
            cache=None):
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_ids = calendar_obj.search(cursor, user, [
            ('owner', '=', user),
            ], limit=1, context=context)
        if not calendar_ids:
            # Sunbird failed with no value
            return '/Calendars'
        calendar = calendar_obj.browse(cursor, user, calendar_ids[0],
                context=context)
        return '/Calendars/' + calendar.name

    def get_schedule_outbox_URL(self, cursor, user, uri, context=None,
            cache=None):
        return self.get_schedule_inbox_URL(cursor, user, uri, context=context,
                cache=cache)

    def put(self, cursor, user, uri, data, content_type, context=None,
            cache=None):
        event_obj = self.pool.get('calendar.event')
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                raise DAV_Forbidden
            event_id = self.event(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            if not event_id:
                ical = vobject.readOne(data)
                values = event_obj.ical2values(cursor, user, None, ical,
                        calendar_id, context=context)
                event_id = event_obj.create(cursor, user, values,
                        context=context)
                event = event_obj.browse(cursor, user, event_id,
                        context=context)
                calendar = calendar_obj.browse(cursor, user, calendar_id,
                        context=context)
                return cursor.database_name + '/Calendars/' + calendar.name + \
                        '/' + event.uuid + '.ics'
            else:
                ical = vobject.readOne(data)
                values = event_obj.ical2values(cursor, user, event_id, ical,
                        calendar_id, context=context)
                event_obj.write(cursor, user, event_id, values,
                        context=context)
                return
        calendar_ics_id = self.calendar(cursor, user, uri, ics=True,
                context=context)
        if calendar_ics_id:
            raise DAV_Forbidden
        return super(Collection, self).put(cursor, user, uri, data,
                content_type, context=context)

    def mkcol(self, cursor, user, uri, context=None, cache=None):
        if uri and uri.startswith('Calendars/'):
            raise DAV_Forbidden
        return super(Collection, self).mkcol(cursor, user, uri, context=context,
                cache=cache)

    def rmcol(self, cursor, user, uri, context=None, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                try:
                    calendar_obj.delete(cursor, user, calendar_id,
                            context=context)
                except:
                    raise DAV_Forbidden
                return 200
            raise DAV_Forbidden
        return super(Collection, self).rmcol(cursor, user, uri, context=context,
                cache=cache)

    def rm(self, cursor, user, uri, context=None, cache=None):
        event_obj = self.pool.get('calendar.event')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return 403
            event_id = self.event(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            if event_id:
                try:
                    event_obj.delete(cursor, user, event_id, context=context)
                except:
                    return 403
                return 200
            return 404
        calendar_ics_id = self.calendar(cursor, user, uri, ics=True,
                context=context)
        if calendar_ics_id:
            return 403
        return super(Collection, self).rm(cursor, user, uri, context=context,
                cache=cache)

    def exists(self, cursor, user, uri, context=None, cache=None):
        if uri in ('Calendars', 'Calendars/'):
            return 1
        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                return 1
            if self.event(cursor, user, uri, calendar_id=calendar_id,
                    context=context):
                return 1
        calendar_ics_id = self.calendar(cursor, user, uri, ics=True,
                context=context)
        if calendar_ics_id:
            return 1
        return super(Collection, self).exists(cursor, user, uri, context=context,
                cache=cache)

    def current_user_privilege_set(self, cursor, user, uri, context=None,
            cache=None):
        '''
        Return the privileges of the current user for uri
        Privileges ares: create, read, write, delete

        :param cursor: the database cursor
        :param user: the user id
        :param uri: the uri
        :param context: the context
        :param cache: the cache
        :return: a list of privileges
        '''
        calendar_obj = self.pool.get('calendar.calendar')

        if uri in ('Calendars', 'Calendars/'):
            return ['create', 'read', 'write', 'delete']
        if uri and uri.startswith('Calendars/'):
            calendar_id = self.calendar(cursor, user, uri, context=context)
            if calendar_id:
                calendar = calendar_obj.browse(cursor, user, calendar_id,
                        context=context)
                if user == calendar.owner.id:
                    return ['create', 'read', 'write', 'delete']
                res = []
                if user in (x.id for x in calendar.read_users):
                    res.append('read')
                if user in (x.id for x in calendar.write_users):
                    res.extend(['read', 'write', 'delete'])
                return res
            return []
        return super(Collection, self).current_user_privilege_set(cursor, user,
                uri, context=context, cache=cache)

Collection()
