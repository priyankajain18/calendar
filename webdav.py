#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelView, ModelSQL
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
            calendar_ids = calendar_obj.search(cursor, user, [
                ('name', '=', calendar),
                ], limit=1, context=context)
            if calendar_ids:
                return calendar_ids[0]
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
            calendar_ids = calendar_obj.search(cursor, user, domain,
                    context=context)
            calendars = calendar_obj.browse(cursor, user, calendar_ids,
                    context=context)
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
            if self.event(cursor, user, uri, calendar_id=calendar_id,
                    context=context):
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
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                cursor.execute('SELECT EXTRACT(epoch FROM create_date) ' \
                        'FROM "' + calendar_obj._table + '" ' \
                            'WHERE id = %s', (calendar_id,))
                fetchone = cursor.fetchone()
                if fetchone:
                    return fetchone[0]
            else:
                event_id = self.event(cursor, user, uri, calendar_id=calendar_id,
                        context=context)
                if event_id:
                    cursor.execute('SELECT EXTRACT(epoch FROM create_date) ' \
                            'FROM "' + event_obj._table + '" ' \
                                'WHERE id = %s', (event_id,))
                    fetchone = cursor.fetchone()
                    if fetchone:
                        return fetchone[0]
        calendar_ics_id = self.calendar(cursor, user, uri, context=context)
        if calendar_ics_id:
            cursor.execute('SELECT EXTRACT(epoch FROM create_date) ' \
                    'FROM "' + calendar_obj._table + '" ' \
                        'WHERE id = %s', (calendar_ics_id,))
            fetchone = cursor.fetchone()
            if fetchone:
                return fetchone[0]
        return super(Collection, self).get_creationdate(cursor, user, uri,
                context=context, cache=cache)

    def get_lastmodified(self, cursor, user, uri, context=None, cache=None):
        calendar_obj = self.pool.get('calendar.calendar')
        event_obj = self.pool.get('calendar.event')

        calendar_id = self.calendar(cursor, user, uri, context=context)
        if calendar_id:
            if not (uri[10:].split('/', 1) + [None])[1]:
                cursor.execute('SELECT EXTRACT(epoch FROM ' \
                            'COALESCE(write_date, create_date)) ' \
                        'FROM "' + calendar_obj._table + '" ' \
                            'WHERE id = %s', (calendar_id,))
                fetchone = cursor.fetchone()
                if fetchone:
                    return fetchone[0]
            else:
                event_id = self.event(cursor, user, uri, calendar_id=calendar_id,
                        context=context)
                if event_id:
                    cursor.execute('SELECT MAX(EXTRACT(epoch FROM ' \
                                'COALESCE(write_date, create_date))) ' \
                            'FROM "' + event_obj._table + '" ' \
                                'WHERE id = %s OR parent = %s',
                                (event_id, event_id))
                    fetchone = cursor.fetchone()
                    if fetchone:
                        return fetchone[0]
        calendar_ics_id = self.calendar(cursor, user, uri, ics=True,
                context=context)
        if calendar_ics_id:
            cursor.execute('SELECT MAX(EXTRACT(epoch FROM ' \
                        'COALESCE(write_date, create_date))) ' \
                    'FROM "' + event_obj._table + '" ' \
                        'WHERE calendar = %s', (calendar_ics_id,))
            fetchone = cursor.fetchone()
            if fetchone:
                return fetchone[0]
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
                calendar = calendar_obj.browse(cursor, user, calendar_id,
                        context=context)
                return calendar.description
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
            raise DAV_NotFound
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
                raise DAV_Forbidden
            event_id = self.event(cursor, user, uri, calendar_id=calendar_id,
                    context=context)
            if event_id:
                try:
                    event_obj.delete(cursor, user, event_id, context=context)
                except:
                    raise DAV_Forbidden
                return 200
        calendar_ics_id = self.calendar(cursor, user, uri, ics=True,
                context=context)
        if calendar_ics_id:
            raise DAV_Forbidden
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
Collection()
