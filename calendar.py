#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelSQL, ModelView, fields
from trytond.tools import Cache, reduce_ids
from trytond.backend import TableHandler
import uuid
import vobject
import dateutil.tz
tzlocal = dateutil.tz.tzlocal()
tzutc = dateutil.tz.tzutc()
import pytz
import datetime
import xml.dom.minidom
domimpl = xml.dom.minidom.getDOMImplementation()


class Calendar(ModelSQL, ModelView):
    "Calendar"
    _description = __doc__
    _name = 'calendar.calendar'

    name = fields.Char('Name', required=True, select=1)
    description = fields.Text('Description')
    owner = fields.Many2One('res.user', 'Owner', select=1,
            domain=[('email', '!=', False)],
            help='The user must have an email')
    read_users = fields.Many2Many('calendar.calendar-read-res.user',
            'calendar', 'user', 'Read Users')
    write_users = fields.Many2Many('calendar.calendar-write-res.user',
            'calendar', 'user', 'Write Users')

    def __init__(self):
        super(Calendar, self).__init__()
        self._sql_constraints = [
            ('name_uniq', 'UNIQUE(name)',
                'The name of calendar must be unique!'),
            ('owner_uniq', 'UNIQUE(owner)',
                'A user can have only one calendar!'),
        ]
        self._order.insert(0, ('name', 'ASC'))
        self._constraints += [
            ('check_name', 'Calendar name can not end with .ics'),
        ]

    def create(self, cursor, user, vals, context=None):
        res = super(Calendar, self).create(cursor, user, vals, context=context)
        # Restart the cache for get_name
        self.get_name(cursor.dbname)
        return res

    def write(self, cursor, user, ids, vals, context=None):
        res = super(Calendar, self).write(cursor, user, ids, vals,
                context=context)
        # Restart the cache for get_name
        self.get_name(cursor.dbname)
        return res

    def delete(self, cursor, user, ids, context=None):
        res = super(Calendar, self).delete(cursor, user, ids, context=context)
        # Restart the cache for calendar
        self.get_name(cursor.dbname)
        return res

    def check_name(self, cursor, user, ids):
        '''
        Check the name doesn't end with .ics
        '''
        for calendar in self.browse(cursor, user, ids):
            if calendar.name.endswith('.ics'):
                return False
        return True

    def get_name(self, cursor, user, name, context=None):
        '''
        Return the calendar id of the name

        :param cursor: the database cursor
        :param user: the user id
        :param name: the calendar name
        :param context: the context
        :return: the calendar.calendar id or False
        '''
        calendar_ids = self.search(cursor, user, [
            ('name', '=', name),
            ], limit=1, context=context)
        if calendar_ids:
            return calendar_ids[0]
        return False

    get_name = Cache('calendar_calendar.get_name')(get_name)

    def calendar2ical(self, cursor, user, calendar_id, context=None):
        '''
        Return an iCalendar object for the given calendar_id containing
        all the vevent objects

        :param cursor: the database cursor
        :param user: the user id
        :param calendar_id: an id of calendar.calendar
        :param context: the context
        :return: an iCalendar
        '''
        event_obj = self.pool.get('calendar.event')

        ical = vobject.iCalendar()
        ical.vevent_list = []
        event_ids = event_obj.search(cursor, user, [
            ('calendar', '=', calendar_id),
            ('parent', '=', False),
            ], context=context)
        for event in event_obj.browse(cursor, user, event_ids,
                context=context):
            ical2 = event_obj.event2ical(cursor, user, event.id,
                    context=context)
            ical.vevent_list.extend(ical2.vevent_list)
        return ical

    def _fbtype(self, cursor, user, event, context=None):
        '''
        Return the freebusy type for give transparent and status

        :param cursor: the database cursor
        :param user: the user id
        :param event: a BrowseRecord of calendar.event
        :param context: the context
        :return: a freebusy type ('FREE', 'BUSY', 'BUSY-TENTATIVE')
        '''
        if event.transp == 'opaque':
            if not event.status or event.status == 'confirmed':
                fbtype = 'BUSY'
            elif event.status == 'cancelled':
                fbtype = 'FREE'
            elif event.status == 'tentative':
                fbtype = 'BUSY-TENTATIVE'
            else:
                fbtype = 'BUSY'
        else:
            fbtype = 'FREE'
        return fbtype

    def freebusy(self, cursor, user, calendar_id, dtstart, dtend, context=None):
        '''
        Return an iCalendar object for the given calendar_id with the
        vfreebusy objects between the two dates

        :param cursor: the database cursor
        :param user: the user id
        :param calendar_id: an id of calendar.calendar
        :param dtstart: a date or datetime
        :param dtend: a date of datetime
        :param context: the context
        :return: an iCalendar
        '''
        event_obj = self.pool.get('calendar.event')

        ical = vobject.iCalendar()
        ical.add('method').value = 'REPLY'
        ical.add('vfreebusy')
        if not isinstance(dtstart, datetime.datetime):
            ical.vfreebusy.add('dtstart').value = dtstart
            dtstart = datetime.datetime.combine(dtstart, datetime.time())\
                    .replace(tzinfo=tzlocal)
        else:
            ical.vfreebusy.add('dtstart').value = dtstart.astimezone(tzutc)
        if not isinstance(dtend, datetime.datetime):
            ical.vfreebusy.add('dtend').value = dtend
            dtend = datetime.datetime.combine(dtend, datetime.time.max)\
                    .replace(tzinfo=tzlocal)
        else:
            ical.vfreebusy.add('dtend').value = dtend.astimezone(tzutc)

        event_ids = event_obj.search(cursor, 0, [
            ['OR',
                [('dtstart', '<=', dtstart),
                    ('dtend', '>=', dtstart)],
                [('dtstart', '<=', dtend),
                    ('dtend', '>=', dtend)],
                [('dtstart', '>=', dtstart),
                    ('dtend', '<=', dtend)],
                [('dtstart', '>=', dtstart),
                    ('dtstart', '<=', dtend),
                    ('dtend', '=', False)]],
            ('parent', '=', False),
            ('rdates', '=', False),
            ('rrules', '=', False),
            ('exdates', '=', False),
            ('exrules', '=', False),
            ('occurences', '=', False),
            ('calendar', '=', calendar_id),
            ], context=context)

        for event in event_obj.browse(cursor, 0, event_ids, context=context):
            # Don't group freebusy as sunbird doesn't handle it
            freebusy = ical.vfreebusy.add('freebusy')
            freebusy.fbtype_param = self._fbtype(cursor, user, event,
                    context=context)
            if event.dtstart.replace(tzinfo=tzlocal) >= dtstart:
                freebusy_dtstart = event.dtstart.replace(tzinfo=tzlocal)
            else:
                freebusy_dtstart = dtstart
            if event.dtend.replace(tzinfo=tzlocal) <= dtend:
                freebusy_dtend = event.dtend.replace(tzinfo=tzlocal)
            else:
                freebusy_dtend = dtend
            freebusy.value = [(
                freebusy_dtstart.astimezone(tzutc),
                freebusy_dtend.astimezone(tzutc))]

        event_ids = event_obj.search(cursor, 0, [
            ('parent', '=', False),
            ('dtstart', '<=', dtend),
            ['OR',
                ('rdates', '!=', False),
                ('rrules', '!=', False),
                ('exdates', '!=', False),
                ('exrules', '!=', False),
                ('occurences', '!=', False),
            ],
            ('calendar', '=', calendar_id),
            ], context=context)
        for event in event_obj.browse(cursor, 0, event_ids, context=context):
            event_ical = event_obj.event2ical(cursor, user, event,
                    context=context)
            if event_ical.vevent.rruleset:
                between_dtstart, between_dtend = dtstart, dtend
                if event.all_day:
                    between_dtstart = dtstart.replace(tzinfo=None)
                    between_dtend = dtend.replace(tzinfo=None)
                for freebusy_dtstart in event_ical.vevent.rruleset:
                    if freebusy_dtstart.replace(tzinfo=tzlocal) > dtend:
                        break
                    if not event.dtend:
                        freebusy_dtend = freebusy_dtstart
                    else:
                        freebusy_dtend = event.dtend.replace(tzinfo=tzlocal)\
                                - event.dtstart.replace(tzinfo=tzlocal) \
                                + freebusy_dtstart
                    if not ((freebusy_dtstart.replace(tzinfo=tzlocal) <= dtstart
                        and freebusy_dtend.replace(tzinfo=tzlocal) >= dtstart)
                        or (freebusy_dtstart.replace(tzinfo=tzlocal) <= dtend
                        and freebusy_dtend.replace(tzinfo=tzlocal) >= dtend)
                        or (freebusy_dtstart.replace(tzinfo=tzlocal) >= dtstart
                        and freebusy_dtend.replace(tzinfo=tzlocal) <= dtend)):
                        continue
                    freebusy_fbtype = self._fbtype(cursor, user, event,
                            context=context)
                    all_day = event.all_day
                    for occurence in event.occurences:
                        if occurence.recurrence.replace(tzinfo=tzlocal) == \
                                freebusy_dtstart.replace(tzinfo=tzlocal):
                            freebusy_dtstart = occurence.dtstart.replace(tzinfo=tzlocal)
                            if occurence.dtend:
                                freebusy_dtend = occurence.dtend\
                                        .replace(tzinfo=tzlocal)
                            else:
                                freebusy_dtend = freebusy_dtstart
                            all_day = occurence.all_day
                            freebusy_fbtype = self._fbtype(cursor, user,
                                    occurence, context=context)
                            break
                    freebusy = ical.vfreebusy.add('freebusy')
                    freebusy.fbtype_param = freebusy_fbtype
                    if freebusy_dtstart.replace(tzinfo=tzlocal) <= dtstart:
                        freebusy_dtstart = dtstart
                    if freebusy_dtend.replace(tzinfo=tzlocal) >= dtend:
                        freebusy_dtend = dtend
                    if all_day:
                        freebusy.value = [(
                            freebusy_dtstart.replace(tzinfo=tzlocal)\
                                    .astimezone(tzutc),
                            freebusy_dtend.replace(tzinfo=tzlocal)\
                                    .astimezone(tzutc))]
                    else:
                        freebusy.value = [(
                            freebusy_dtstart.astimezone(tzutc),
                            freebusy_dtend.astimezone(tzutc))]
        return ical

    def post(self, cursor, user, uri, data, context=None):
        '''
        Handle post of vfreebusy request

        :param cursor: the database cursor
        :param user: the user id
        :param uri: the posted uri
        :param data: the posted data
        :param context: the context
        :return: the xml with schedule-response
        '''
        collection_obj = self.pool.get('webdav.collection')

        calendar_id = collection_obj.calendar(cursor, user, uri,
                context=context)
        if not calendar_id:
            raise DAV_Forbidden
        calendar = self.browse(cursor, user, calendar_id,
                context=context)
        if calendar.owner.id != user:
            raise DAV_Forbidden
        ical = vobject.readOne(data)
        if ical.method.value == 'REQUEST' \
                and hasattr(ical, 'vfreebusy'):
            doc = domimpl.createDocument(None, 'schedule-response', None)
            sr = doc.documentElement
            sr.setAttribute('xmlns:D', 'DAV:')
            sr.setAttribute('xmlns:C', 'urn:ietf:params:xml:ns:caldav')
            sr.tagName = 'C:schedule-response'

            if not isinstance(ical.vfreebusy.dtstart.value, datetime.datetime):
                dtstart = ical.vfreebusy.dtstart.value
            else:
                if ical.vfreebusy.dtstart.value.tzinfo:
                    dtstart = ical.vfreebusy.dtstart.value.astimezone(tzlocal)
                else:
                    dtstart = ical.vfreebusy.dtstart.value
            if not isinstance(ical.vfreebusy.dtend.value, datetime.datetime):
                dtend = ical.vfreebusy.dtend.value
            else:
                if ical.vfreebusy.dtend.value.tzinfo:
                    dtend = ical.vfreebusy.dtend.value.astimezone(tzlocal)
                else:
                    dtend = ical.vfreebusy.dtend.value
            for attendee in ical.vfreebusy.attendee_list:
                resp = doc.createElement('C:response')
                sr.appendChild(resp)
                recipient = doc.createElement('C:recipient')
                href = doc.createElement('D:href')
                huri = doc.createTextNode(attendee.value)
                href.appendChild(huri)
                recipient.appendChild(href)
                resp.appendChild(recipient)

                vfreebusy = None
                email = attendee.value
                if attendee.value.lower().startswith('mailto:'):
                    email = attendee.value[7:]
                calendar_ids = self.search(cursor, 0, [
                    ('owner.email', '=', email),
                    ], context=context)
                if calendar_ids:
                    vfreebusy = self.freebusy(cursor, user, calendar_ids[0],
                            dtstart, dtend, context=context)
                    vfreebusy.vfreebusy.add('dtstamp').value = \
                            ical.vfreebusy.dtstamp.value
                    vfreebusy.vfreebusy.add('uid').value = \
                            ical.vfreebusy.uid.value
                    vfreebusy.vfreebusy.add('organizer').value = \
                            ical.vfreebusy.organizer.value
                    vfreebusy.vfreebusy.add('attendee').value = attendee.value

                status = doc.createElement('C:request-status')
                status.appendChild(doc.createTextNode(vfreebusy and \
                        '2.0;Success' or '5.3;No scheduling support for user.'))
                resp.appendChild(status)
                if vfreebusy:
                    data = doc.createElement('C:calendar-data')
                    data.appendChild(doc.createTextNode(vfreebusy.serialize()))
                    resp.appendChild(data)
            return doc.toxml(encoding='utf-8')
        raise DAV_Forbidden

Calendar()


class ReadUser(ModelSQL):
    'Calendar - read - User'
    _description = __doc__
    _name = 'calendar.calendar-read-res.user'

    calendar = fields.Many2One('calendar.calendar', 'Calendar',
            ondelete='CASCADE', required=True, select=1)
    user = fields.Many2One('res.user', 'User', ondelete='CASCADE',
            required=True, select=1)

ReadUser()


class WriteUser(ModelSQL):
    'Calendar - write - User'
    _description = __doc__
    _name = 'calendar.calendar-write-res.user'

    calendar = fields.Many2One('calendar.calendar', 'Calendar',
            ondelete='CASCADE', required=True, select=1)
    user = fields.Many2One('res.user', 'User', ondelete='CASCADE',
            required=True, select=1)

WriteUser()


class Category(ModelSQL, ModelView):
    "Category"
    _description = __doc__
    _name = 'calendar.category'

    name = fields.Char('Name', required=True, select=1)

    def __init__(self):
        super(Category, self).__init__()
        self._sql_constraints = [
            ('name_uniq', 'UNIQUE(name)',
                'The name of calendar category must be unique!'),
        ]
        self._order.insert(0, ('name', 'ASC'))

Category()


class Location(ModelSQL, ModelView):
    "Location"
    _description = __doc__
    _name = 'calendar.location'

    name = fields.Char('Name', required=True, select=1)

    def __init__(self):
        super(Location, self).__init__()
        self._sql_constraints = [
            ('name_uniq', 'UNIQUE(name)',
                'The name of calendar location must be unique!'),
        ]
        self._order.insert(0, ('name', 'ASC'))

Location()


class Event(ModelSQL, ModelView):
    "Event"
    _description = __doc__
    _name = 'calendar.event'
    _rec_name = 'uuid'

    uuid = fields.Char('UUID', required=True,
            help='Universally Unique Identifier', select=1)
    calendar = fields.Many2One('calendar.calendar', 'Calendar',
            required=True, select=1, ondelete="CASCADE")
    summary = fields.Char('Summary')
    sequence = fields.Integer('Sequence')
    description = fields.Text('Description')
    all_day = fields.Boolean('All Day')
    dtstart = fields.DateTime('Start Date', required=True, select=1)
    dtend = fields.DateTime('End Date', select=1)
    timezone = fields.Selection('timezones', 'Timezone')
    categories = fields.Many2Many('calendar.event-calendar.category',
            'event', 'category', 'Categories')
    classification = fields.Selection([
        ('public', 'Public'),
        ('private', 'Private'),
        ('confidential', 'Confidential'),
        ], 'Classification', required=True)
    location = fields.Many2One('calendar.location', 'Location')
    status = fields.Selection([
        ('', ''),
        ('tentative', 'Tentative'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ], 'Status')
    organizer = fields.Char('Organizer', states={
        'required': "bool(attendees) and not bool(parent)",
        }, depends=['attendees', 'parent'])
    attendees = fields.One2Many('calendar.event.attendee', 'event',
            'Attendees')
    transp = fields.Selection([
        ('opaque', 'Opaque'),
        ('transparent', 'Transparent'),
        ], 'Time Transparency', required=True)
    alarms = fields.One2Many('calendar.event.alarm', 'event', 'Alarms')
    rdates = fields.One2Many('calendar.event.rdate', 'event', 'Recurrence Dates',
            states={
                'invisible': "bool(parent)",
            }, depends=['parent'])
    rrules = fields.One2Many('calendar.event.rrule', 'event', 'Recurrence Rules',
            states={
                'invisible': "bool(parent)",
            }, depends=['parent'])
    exdates = fields.One2Many('calendar.event.exdate', 'event', 'Exception Dates',
            states={
                'invisible': "bool(parent)",
            }, depends=['parent'])
    exrules = fields.One2Many('calendar.event.exrule', 'event', 'Exception Rules',
            states={
                'invisible': "bool(parent)",
            }, depends=['parent'])
    occurences = fields.One2Many('calendar.event', 'parent', 'Occurences',
            domain=["('uuid', '=', uuid)",
                "('calendar', '=', calendar)"],
            states={
                'invisible': "bool(parent)",
            }, depends=['uuid', 'calendar', 'parent'])
    parent = fields.Many2One('calendar.event', 'Parent',
            domain=["('uuid', '=', uuid)",
                "('parent', '=', False)",
                "('calendar', '=', calendar)"],
            ondelete='CASCADE', depends=['uuid', 'calendar'])
    recurrence = fields.DateTime('Recurrence', select=1, states={
                'invisible': "not bool(globals().get('_parent_parent'))",
                'required': "bool(globals().get('_parent_parent'))",
                }, depends=['parent'])
    calendar_owner = fields.Function('get_calendar_field',
            type='many2one', relation='res.user', string='Owner',
            fnct_search='search_calendar_field')
    calendar_read_users = fields.Function('get_calendar_field',
            type='many2many', relation='res.user', string='Read Users',
            fnct_search='search_calendar_field')
    calendar_write_users = fields.Function('get_calendar_field',
            type='many2many', relation='res.user', string='Write Users',
            fnct_search='search_calendar_field')
    classification_public = fields.Function('get_classification_public',
            type='boolean', string='Classification Public',
            fnct_search='search_classification_public')
    vevent = fields.Binary('vevent')

    def __init__(self):
        super(Event, self).__init__()
        self._sql_constraints = [
            ('uuid_recurrence_uniq', 'UNIQUE(uuid, calendar, recurrence)',
                'UUID and recurrence must be unique in a calendar!'),
        ]
        self._constraints += [
            ('check_recurrence', 'invalid_recurrence'),
        ]
        self._error_messages.update({
            'invalid_recurrence': 'Recurrence can not be recurrent!',
        })

    def default_uuid(self, cursor, user, context=None):
        return str(uuid.uuid4())

    def default_sequence(self, cursor, user, context=None):
        return 0

    def default_classification(self, cursor, user, context=None):
        return 'public'

    def default_transp(self, cursor, user, context=None):
        return 'opaque'

    def default_timezone(self, cursor, user, context=None):
        user_obj = self.pool.get('res.user')
        user_ = user_obj.browse(cursor, user, user, context=context)
        return user_.timezone

    def timezones(self, cursor, user, context=None):
        return [(x, x) for x in pytz.common_timezones] + [('', '')]

    def get_calendar_field(self, cursor, user, ids, name, arg, context=None):
        assert name in ('calendar_owner', 'calendar_read_users',
                'calendar_write_users'), 'Invalid name'
        res = {}
        for event in self.browse(cursor, user, ids, context=context):
            name = name[9:]
            if name in ('read_users', 'write_users'):
                res[event.id] = [x.id for x in event.calendar[name]]
            else:
                res[event.id] = event.calendar[name].id
        return res

    def search_calendar_field(self, cursor, user, name, args, context=None):
        args2 = []
        i = 0
        while i < len(args):
            field = args[i][0][9:]
            args2.append(tuple(['calendar.' + field] + list(args[i])[1:]))
            i += 1
        return args2

    def get_classification_public(self, cursor, user, ids, name, arg,
            context=None):
        res = {}
        for event in self.browse(cursor, user, ids, context=context):
            res[event.id] = False
            if event.classification == 'public':
                res[event.id] = True
        return res

    def search_classification_public(self, cursor, user, name, args,
            context=None):
        args2 = []
        i = 0
        while i < len(args):
            if args[i][2]:
                args2.append(('classification', '=', 'public'))
            else:
                args2.append(('classification', '!=', 'public'))
            i += 1
        return args2

    def check_recurrence(self, cursor, user, ids):
        '''
        Check the recurrence is not recurrent.
        '''
        for event in self.browse(cursor, user, ids):
            if not event.parent:
                continue
            if event.rdates \
                    or event.rrules \
                    or event.exdates \
                    or event.exrules \
                    or event.occurences:
                return False
        return True

    def create(self, cursor, user, values, context=None):
        calendar_obj = self.pool.get('calendar.calendar')
        collection_obj = self.pool.get('webdav.collection')

        res = super(Event, self).create(cursor, user, values, context=context)
        event = self.browse(cursor, user, res, context=context)
        if event.calendar.owner \
                and (event.organizer == event.calendar.owner.email \
                or (event.parent \
                and event.parent.organizer == event.parent.calendar.owner.email)):
            if event.organizer == event.calendar.owner.email:
                attendee_emails = [x.email for x in event.attendees
                        if x.status != 'declined'
                        and x.email != event.organizer]
            else:
                attendee_emails = [x.email for x in event.parent.attendees
                        if x.status != 'declined'
                        and x.email != event.parent.organizer]
            if attendee_emails:
                calendar_ids = calendar_obj.search(cursor, 0, [
                    ('owner.email', 'in', attendee_emails),
                    ], context=context)
                if not event.recurrence:
                    for calendar_id in calendar_ids:
                        new_id = self.copy(cursor, 0, event.id, default={
                            'calendar': calendar_id,
                            'occurences': False,
                            }, context=context)
                        for occurence in event.occurences:
                            self.copy(cursor, 0, occurence.id, default={
                                'calendar': calendar_id,
                                'parent': new_id,
                                }, context=context)
                else:
                    parent_ids = self.search(cursor, 0, [
                        ('uuid', '=', event.uuid),
                        ('calendar.owner.email', 'in', attendee_emails),
                        ('id', '!=', event.id),
                        ('recurrence', '=', False),
                        ], context=context)
                    for parent in self.browse(cursor, 0, parent_ids,
                            context=context):
                        self.copy(cursor, 0, event.id, default={
                            'calendar': parent.calendar.id,
                            'parent': parent.id,
                            }, context=context)
        # Restart the cache for event
        collection_obj.event(cursor.dbname)
        return res

    def _event2update(self, cursor, user, event, context=None):
        rdate_obj = self.pool.get('calendar.event.rdate')
        exdate_obj = self.pool.get('calendar.event.exdate')
        rrule_obj = self.pool.get('calendar.event.rrule')
        exrule_obj = self.pool.get('calendar.event.exrule')

        res = {}
        res['summary'] = event.summary
        res['description'] = event.description
        res['all_day'] = event.all_day
        res['dtstart'] = event.dtstart
        res['dtend'] = event.dtend
        res['location'] = event.location.id
        res['status'] = event.status
        res['organizer'] = event.organizer
        res['rdates'] = [('delete_all',)]
        for rdate in event.rdates:
            vals = rdate_obj._date2update(cursor, user, rdate, context=context)
            res['rdates'].append(('create', vals))
        res['exdates'] = [('delete_all',)]
        for exdate in event.exdates:
            vals = exdate_obj._date2update(cursor, user, exdate, context=context)
            res['exdates'].append(('create', vals))
        res['rrules'] = [('delete_all',)]
        for rrule in event.rrules:
            vals = rrule_obj._rule2update(cursor, user, rrule, context=context)
            res['rrules'].append(('create', vals))
        res['exrules'] = [('delete_all',)]
        for exrule in event.exrules:
            vals = exrule_obj._rule2update(cursor, user, exrule, context=context)
            res['exrules'].append(('create', vals))
        return res

    def write(self, cursor, user, ids, values, context=None):
        calendar_obj = self.pool.get('calendar.calendar')
        collection_obj = self.pool.get('webdav.collection')

        values = values.copy()
        if 'sequence' in values:
            del values['sequence']

        res = super(Event, self).write(cursor, user, ids, values,
                context=context)

        if isinstance(ids, (int, long)):
            ids = [ids]

        for i in range(0, len(ids), cursor.IN_MAX):
            sub_ids = ids[i:i + cursor.IN_MAX]
            red_sql, red_ids = reduce_ids('id', sub_ids)
            cursor.execute('UPDATE "' + self._table + '" ' \
                    'SET sequence = sequence + 1 ' \
                    'WHERE ' + red_sql, red_ids)

        for event in self.browse(cursor, user, ids, context=context):
            if event.calendar.owner \
                    and (event.organizer == event.calendar.owner.email \
                    or (event.parent \
                    and event.parent.organizer == event.calendar.owner.email)):
                if event.organizer == event.calendar.owner.email:
                    attendee_emails = [x.email for x in event.attendees
                            if x.status != 'declined'
                            and x.email != event.organizer]
                else:
                    attendee_emails = [x.email for x in event.parent.attendees
                            if x.status != 'declined'
                            and x.email != event.parent.organizer]
                if attendee_emails:
                    event_ids = self.search(cursor, 0, [
                        ('uuid', '=', event.uuid),
                        ('calendar.owner.email', 'in', attendee_emails),
                        ('id', '!=', event.id),
                        ('recurrence', '=', event.recurrence or False),
                        ], context=context)
                    for event2 in self.browse(cursor, user, event_ids,
                            context=context):
                        if event2.calendar.owner.email in attendee_emails:
                            attendee_emails.remove(event2.calendar.owner.email)
                    self.write(cursor, 0, event_ids, self._event2update(
                        cursor, user, event, context=context), context=context)
                if attendee_emails:
                    calendar_ids = calendar_obj.search(cursor, 0, [
                        ('owner.email', 'in', attendee_emails),
                        ], context=context)
                    if not event.recurrence:
                        for calendar_id in calendar_ids:
                            new_id = self.copy(cursor, 0, event.id, default={
                                'calendar': calendar_id,
                                'occurences': False,
                                }, context=context)
                            for occurence in event.occurences:
                                self.copy(cursor, 0, occurence.id, default={
                                    'calendar': calendar_id,
                                    'parent': new_id,
                                    }, context=context)
                    else:
                        parent_ids = self.search(cursor, 0, [
                            ('uuid', '=', event.uuid),
                            ('calendar.owner.email', 'in', attendee_emails),
                            ('id', '!=', event.id),
                            ('recurrence', '=', False),
                            ], context=context)
                        for parent in self.browse(cursor, 0, parent_ids,
                                context=context):
                            self.copy(cursor, 0, event.id, default={
                                'calendar': parent.calendar.id,
                                'parent': parent.id,
                                }, context=context)
        # Restart the cache for event
        collection_obj.event(cursor.dbname)
        return res

    def delete(self, cursor, user, ids, context=None):
        attendee_obj = self.pool.get('calendar.event.attendee')
        collection_obj = self.pool.get('webdav.collection')

        if isinstance(ids, (int, long)):
            ids = [ids]
        for event in self.browse(cursor, user, ids, context=context):
            if event.calendar.owner \
                    and (event.organizer == event.calendar.owner.email \
                    or (event.parent \
                    and event.parent.organizer == event.calendar.owner.email)):
                if event.organizer == event.calendar.owner.email:
                    attendee_emails = [x.email for x in event.attendees
                            if x.email != event.organizer]
                else:
                    attendee_emails = [x.email for x in event.parent.attendees
                            if x.email != event.parent.organizer]
                if attendee_emails:
                    event_ids = self.search(cursor, 0, [
                        ('uuid', '=', event.uuid),
                        ('calendar.owner.email', 'in', attendee_emails),
                        ('id', '!=', event.id),
                        ('recurrence', '=', event.recurrence or False),
                        ], context=context)
                    self.delete(cursor, 0, event_ids, context=context)
            elif event.organizer \
                    or (event.parent and event.parent.organizer):
                if event.organizer:
                    organizer = event.organizer
                else:
                    organizer = event.parent.organizer
                event_ids = self.search(cursor, 0, [
                    ('uuid', '=', event.uuid),
                    ('calendar.owner.email', '=', organizer),
                    ('id', '!=', event.id),
                    ('recurrence', '=', event.recurrence or False),
                    ], context=context, limit=1)
                if event_ids:
                    event2 = self.browse(cursor, 0, event_ids[0],
                            context=context)
                    for attendee in event2.attendees:
                        if attendee.email == event.calendar.owner.email:
                            attendee_obj.write(cursor, 0, attendee.id, {
                                'status': 'declined',
                                }, context=context)
        res = super(Event, self).delete(cursor, user, ids, context=context)
        # Restart the cache for event
        collection_obj.event(cursor.dbname)
        return res

    def ical2values(self, cursor, user, event_id, ical, calendar_id,
            vevent=None, context=None):
        '''
        Convert iCalendar to values for create or write

        :param cursor: the database cursor
        :param user: the user id
        :param event_id: the event id for write or None for create
        :param ical: a ical instance of vobject
        :param calendar_id: the calendar id of the event
        :param vevent: the vevent of the ical to use if None use the first one
        :param context: the context
        :return: a dictionary with values
        '''
        category_obj = self.pool.get('calendar.category')
        location_obj = self.pool.get('calendar.location')
        user_obj = self.pool.get('res.user')
        alarm_obj = self.pool.get('calendar.event.alarm')
        attendee_obj = self.pool.get('calendar.event.attendee')
        rdate_obj = self.pool.get('calendar.event.rdate')
        exdate_obj = self.pool.get('calendar.event.exdate')
        rrule_obj = self.pool.get('calendar.event.rrule')
        exrule_obj = self.pool.get('calendar.event.exrule')

        if context is None:
            context = {}

        vevents = []
        if not vevent:
            vevent = ical.vevent

            for i in ical.getChildren():
                if i.name == 'VEVENT' \
                        and i != vevent:
                    vevents.append(i)

        event = None
        if event_id:
            event = self.browse(cursor, user, event_id, context=context)

        res = {}
        if not event:
            if hasattr(vevent, 'uid'):
                res['uuid'] = vevent.uid.value
            else:
                res['uuid'] = str(uuid.uuid4())
        if hasattr(vevent, 'summary'):
            res['summary'] = vevent.summary.value
        else:
            res['summary'] = False
        if hasattr(vevent, 'description'):
            res['description'] = vevent.description.value
        else:
            res['description'] = False
        if not isinstance(vevent.dtstart.value, datetime.datetime):
            res['all_day'] = True
            res['dtstart'] = datetime.datetime.combine(vevent.dtstart.value,
                    datetime.time())
        else:
            res['all_day'] = False
            if vevent.dtstart.value.tzinfo:
                res['dtstart'] = vevent.dtstart.value.astimezone(tzlocal)
            else:
                res['dtstart'] = vevent.dtstart.value
        if hasattr(vevent, 'dtend'):
            if not isinstance(vevent.dtend.value, datetime.datetime):
                res['dtend'] = datetime.datetime.combine(vevent.dtend.value,
                        datetime.time())
            else:
                if vevent.dtend.value.tzinfo:
                    res['dtend'] = vevent.dtend.value.astimezone(tzlocal)
                else:
                    res['dtend'] = vevent.dtend.value
        elif hasattr(vevent, 'duration') and hasattr(vevent, 'dtstart'):
            res['dtend'] = vevent.dtstart.value + vevent.duration.value
        else:
            res['dtend'] = False
        if hasattr(vevent, 'recurrence-id'):
            if not isinstance(vevent.recurrence_id.value, datetime.datetime):
                res['recurrence'] = datetime.datetime.combine(
                        vevent.recurrence_id.value, datetime.time())
            else:
                if vevent.recurrence_id.value.tzinfo:
                    res['recurrence'] = \
                            vevent.recurrence_id.value.astimezone(tzlocal)
                else:
                    res['recurrence'] = vevent.recurrence_id.value
        else:
            res['recurrence'] = False
        if hasattr(vevent, 'status'):
            res['status'] = vevent.status.value.lower()
        else:
            res['status'] = ''
        if hasattr(vevent, 'categories'):
            ctx = context.copy()
            ctx['active_test'] = False
            category_ids = category_obj.search(cursor, user, [
                ('name', 'in', [x for x in vevent.categories.value]),
                ], context=context)
            categories = category_obj.browse(cursor, user, category_ids,
                    context=context)
            category_names2ids = {}
            for category in categories:
                category_names2ids[category.name] = category.id
            for category in vevent.categories.value:
                if category not in category_names2ids:
                    category_ids.append(category_obj.create(cursor, user, {
                        'name': category,
                        }, context=context))
            res['categories'] = [('set', category_ids)]
        else:
            res['categories'] = [('unlink_all',)]
        if hasattr(vevent, 'class'):
            if getattr(vevent, 'class').value.lower() in \
                    dict(self.classification.selection):
                res['classification'] = getattr(vevent, 'class').value.lower()
            else:
                res['classification'] = 'public'
        else:
            res['classification'] = 'public'
        if hasattr(vevent, 'location'):
            ctx = context.copy()
            ctx['active_test'] = False
            location_ids = location_obj.search(cursor, user, [
                ('name', '=', vevent.location.value),
                ], limit=1, context=ctx)
            if not location_ids:
                location_id = location_obj.create(cursor, user, {
                    'name': vevent.location.value,
                    }, context=context)
            else:
                location_id = location_ids[0]
            res['location'] = location_id
        else:
            res['location'] = False

        res['calendar'] = calendar_id

        if hasattr(vevent, 'transp'):
            res['transp'] = vevent.transp.value.lower()
        else:
            res['transp'] = 'opaque'

        if hasattr(vevent, 'organizer'):
            if vevent.organizer.value.lower().startswith('mailto:'):
                res['organizer'] = vevent.organizer.value[7:]
            else:
                res['organizer'] = vevent.organizer.value
        else:
            res['organizer'] = False

        attendees_todel = {}
        if event:
            for attendee in event.attendees:
                attendees_todel[attendee.email] = attendee.id
        res['attendees'] = []
        if hasattr(vevent, 'attendee'):
            while vevent.attendee_list:
                attendee = vevent.attendee_list.pop()
                vals = attendee_obj.attendee2values(cursor, user, attendee,
                        context=context)
                if vals['email'] in attendees_todel:
                    res['attendees'].append(('write',
                        attendees_todel[vals['email']], vals))
                    del attendees_todel[vals['email']]
                else:
                    res['attendees'].append(('create', vals))
        res['attendees'].append(('delete', attendees_todel.values()))

        res['rdates'] = []
        if event:
            res['rdates'].append(('delete', [x.id for x in event.rdates]))
        if hasattr(vevent, 'rdate'):
            while vevent.rdate_list:
                rdate = vevent.rdate_list.pop()
                for date in rdate.value:
                    vals = rdate_obj.date2values(cursor, user, date,
                            context=context)
                    res['rdates'].append(('create', vals))

        res['exdates'] = []
        if event:
            res['exdates'].append(('delete', [x.id for x in event.exdates]))
        if hasattr(vevent, 'exdate'):
            while vevent.exdate_list:
                exdate = vevent.exdate_list.pop()
                for date in exdate.value:
                    vals = exdate_obj.date2values(cursor, user, date,
                            context=context)
                    res['exdates'].append(('create', vals))

        res['rrules'] = []
        if event:
            res['rrules'].append(('delete', [x.id for x in event.rrules]))
        if hasattr(vevent, 'rrule'):
            while vevent.rrule_list:
                rrule = vevent.rrule_list.pop()
                vals = rrule_obj.rule2values(cursor, user, rrule,
                        context=context)
                res['rrules'].append(('create', vals))

        res['exrules'] = []
        if event:
            res['exrules'].append(('delete', [x.id for x in event.exrules]))
        if hasattr(vevent, 'exrule'):
            while vevent.exrule_list:
                exrule = vevent.exrule_list.pop()
                vals = exrule_obj.rule2values(cursor, user, exrule,
                        context=context)
                res['exrules'].append(('create', vals))

        if event:
            res.setdefault('alarms', [])
            res['alarms'].append(('delete', [x.id for x in event.alarms]))
        if hasattr(vevent, 'valarm'):
            res.setdefault('alarms', [])
            while vevent.valarm_list:
                valarm = vevent.valarm_list.pop()
                vals = alarm_obj.valarm2values(cursor, user, valarm,
                        context=context)
                res['alarms'].append(('create', vals))

        if hasattr(ical, 'vtimezone'):
            if ical.vtimezone.tzid.value in pytz.common_timezones:
                res['timezone'] = ical.vtimezone.tzid.value
            else:
                for timezone in pytz.common_timezones:
                    if ical.vtimezone.tzid.value.endswith(timezone):
                        res['timezone'] = timezone

        res['vevent'] = vevent.serialize()

        occurences_todel = []
        if event:
            occurences_todel = [x.id for x in event.occurences]
        for vevent in vevents:
            event_id = None
            if event:
                for occurence in event.occurences:
                    if occurence.recurrence.replace(tzinfo=tzlocal) \
                            == vevent.recurrence_id.value:
                        event_id = occurence.id
                        occurences_todel.remove(occurence.id)
            vals = self.ical2values(cursor, user, event_id, ical,
                    calendar_id, vevent=vevent, context=context)
            if event:
                vals['uuid'] = event.uuid
            else:
                vals['uuid'] = res['uuid']
            res.setdefault('occurences', [])
            if event_id:
                res['occurences'].append(('write', event_id, vals))
            else:
                res['occurences'].append(('create', vals))
        if occurences_todel:
            res.setdefault('occurences', [])
            res['occurences'].append(('delete', occurences_todel))
        return res

    def event2ical(self, cursor, user, event, context=None):
        '''
        Return an iCalendar instance of vobject for event

        :param cursor: the database cursor
        :param user: the user id
        :param event: a BrowseRecord of calendar.event
            or a calendar.event id
        :param calendar: a BrowseRecord of calendar.calendar
            or a calendar.calendar id
        :param context: the context
        :return: an iCalendar instance of vobject
        '''
        user_obj = self.pool.get('res.user')
        alarm_obj = self.pool.get('calendar.event.alarm')
        attendee_obj = self.pool.get('calendar.event.attendee')
        rdate_obj = self.pool.get('calendar.event.rdate')
        exdate_obj = self.pool.get('calendar.event.exdate')
        rrule_obj = self.pool.get('calendar.event.rrule')
        exrule_obj = self.pool.get('calendar.event.exrule')

        if isinstance(event, (int, long)):
            event = self.browse(cursor, user, event, context=context)

        user_ = user_obj.browse(cursor, user, user, context=context)
        if event.timezone:
            tzevent = pytz.timezone(event.timezone)
        elif user_.timezone:
                tzevent = pytz.timezone(user_.timezone)
        else:
            tzevent = tzlocal

        ical = vobject.iCalendar()
        vevent = ical.add('vevent')
        if event.vevent:
            ical.vevent = vobject.readOne(event.vevent)
            vevent = ical.vevent
            ical.vevent.transformToNative()
        if event.summary:
            if not hasattr(vevent, 'summary'):
                vevent.add('summary')
            vevent.summary.value = event.summary
        elif hasattr(vevent, 'summary'):
            del vevent.summary
        if event.description:
            if not hasattr(vevent, 'description'):
                vevent.add('description')
            vevent.description.value = event.description
        elif hasattr(vevent, 'description'):
            del vevent.description
        if not hasattr(vevent, 'dtstart'):
            vevent.add('dtstart')
        if event.all_day:
            vevent.dtstart.value = event.dtstart.date()
        else:
            vevent.dtstart.value = event.dtstart.replace(tzinfo=tzlocal)\
                    .astimezone(tzevent)
        if event.dtend:
            if not hasattr(vevent, 'dtend'):
                vevent.add('dtend')
            if event.all_day:
                vevent.dtend.value = event.dtend.date()
            else:
                vevent.dtend.value = event.dtend.replace(tzinfo=tzlocal)\
                        .astimezone(tzevent)
        elif hasattr(vevent, 'dtend'):
            del vevent.dtend
        if not hasattr(vevent, 'created'):
            vevent.add('created')
        vevent.created.value = event.create_date.replace(tzinfo=tzlocal)
        if not hasattr(vevent, 'dtstamp'):
            vevent.add('dtstamp')
        date = event.write_date or event.create_date
        vevent.dtstamp.value = date.replace(tzinfo=tzlocal)
        if not hasattr(vevent, 'last-modified'):
            vevent.add('last-modified')
        vevent.last_modified.value = date.replace(tzinfo=tzlocal)
        if event.recurrence and event.parent:
            if not hasattr(vevent, 'recurrence-id'):
                vevent.add('recurrence-id')
            if event.all_day:
                vevent.recurrence_id.value = event.recurrence.date()
            else:
                vevent.recurrence_id.value = event.recurrence\
                        .replace(tzinfo=tzlocal).astimezone(tzevent)
        elif hasattr(vevent, 'recurrence-id'):
            del vevent.recurrence_id
        if event.status:
            if not hasattr(vevent, 'status'):
                vevent.add('status')
            vevent.status.value = event.status.upper()
        elif hasattr(vevent, 'status'):
            del vevent.status
        if not hasattr(vevent, 'uid'):
            vevent.add('uid')
        vevent.uid.value = event.uuid
        if not hasattr(vevent, 'sequence'):
            vevent.add('sequence')
        vevent.sequence.value = str(event.sequence) or '0'
        if event.categories:
            if not hasattr(vevent, 'categories'):
                vevent.add('categories')
            vevent.categories.value = [x.name for x in event.categories]
        elif hasattr(vevent, 'categories'):
            del vevent.categories
        if not hasattr(vevent, 'class'):
            vevent.add('class')
            getattr(vevent, 'class').value = event.classification.upper()
        elif getattr(vevent, 'class').value.lower() in \
                dict(self.classification.selection):
            getattr(vevent, 'class').value = event.classification.upper()
        if event.location:
            if not hasattr(vevent, 'location'):
                vevent.add('location')
            vevent.location.value = event.location.name
        elif hasattr(vevent, 'location'):
            del vevent.location

        if event.organizer:
            if not hasattr(vevent, 'organizer'):
                vevent.add('organizer')
            vevent.organizer.value = 'MAILTO:' + event.organizer
        elif hasattr(vevent, 'organizer'):
            del vevent.organizer

        vevent.attendee_list = []
        for attendee in event.attendees:
            vevent.attendee_list.append(attendee_obj.attendee2attendee(
                cursor, user, attendee, context=context))

        if event.rdates:
            vevent.add('rdate')
            vevent.rdate.value = []
            for rdate in event.rdates:
                vevent.rdate.value.append(rdate_obj.date2date(cursor, user,
                    rdate, context=context))

        if event.exdates:
            vevent.add('exdate')
            vevent.exdate.value = []
            for exdate in event.exdates:
                vevent.exdate.value.append(exdate_obj.date2date(cursor, user,
                    exdate, context=context))

        if event.rrules:
            for rrule in event.rrules:
                vevent.add('rrule').value = rrule_obj.rule2rule(cursor, user,
                        rrule, context=context)

        if event.exrules:
            for exrule in event.exrules:
                vevent.add('exrule').value = exrule_obj.rule2rule(cursor, user,
                        exrule, context=context)

        vevent.valarm_list = []
        for alarm in event.alarms:
            valarm = alarm_obj.alarm2valarm(cursor, user, alarm,
                    context=context)
            if valarm:
                vevent.valarm_list.append(valarm)

        for occurence in event.occurences:
            oical = self.event2ical(cursor, user, occurence, context=context)
            ical.vevent_list.append(oical.vevent)
        return ical

Event()


class EventCategory(ModelSQL):
    'Event - Category'
    _description = __doc__
    _name = 'calendar.event-calendar.category'

    event = fields.Many2One('calendar.event', 'Event', ondelete='CASCADE',
            required=True, select=1)
    category = fields.Many2One('calendar.category', 'Category',
            ondelete='CASCADE', required=True, select=1)

EventCategory()


class Alarm(ModelSQL):
    'Alarm'
    _description = __doc__
    _name = 'calendar.alarm'

    valarm = fields.Binary('valarm')

    def valarm2values(self, cursor, user, valarm, context=None):
        '''
        Convert a valarm object into values for create or write

        :param cursor: the database cursor
        :param user: the user id
        :param valarm: the valarm object
        :param context: the context
        :return: a dictionary with values
        '''
        res = {}
        res['valarm'] = valarm.serialize()
        return res

    def alarm2valarm(self, cursor, user, alarm, context=None):
        '''
        Return a valarm instance of vobject for alarm

        :param cursor: the database cursor
        :param user: the user id
        :param alarm: a BrowseRecord of calendar.event.alarm
        :param context: the context
        :return: a valarm instance of vobject
        '''
        valarm = None
        if alarm.valarm:
            valarm = vobject.readOne(alarm.valarm)
        return valarm

Alarm()


class EventAlarm(ModelSQL):
    'Alarm'
    _description = __doc__
    _name = 'calendar.event.alarm'
    _inherits = {'calendar.alarm': 'calendar_alarm'}

    calendar_alarm = fields.Many2One('calendar.alarm', 'Calendar Alarm',
            required=True, ondelete='CASCADE', select=1)
    event = fields.Many2One('calendar.event', 'Event', ondelete='CASCADE',
            required=True, select=1)

    def create(self, cursor, user, values, context=None):
        event_obj = self.pool.get('calendar.event')
        if values.get('event'):
            # Update write_date of event
            event_obj.write(cursor, user, values['event'], {}, context=context)
        return super(EventAlarm, self).create(cursor, user, values, context=context)

    def write(self, cursor, user, ids, values, context=None):
        event_obj = self.pool.get('calendar.event')
        if isinstance(ids, (int, long)):
            ids = [ids]
        event_ids = [x.event.id for x in self.browse(cursor, user, ids,
            context=context)]
        if values.get('event'):
            event_ids.append(values['event'])
        if event_ids:
            # Update write_date of event
            event_obj.write(cursor, user, event_ids, {}, context=context)
        return super(EventAlarm, self).write(cursor, user, ids, values,
                context=context)

    def delete(self, cursor, user, ids, context=None):
        event_obj = self.pool.get('calendar.event')
        alarm_obj = self.pool.get('calendar.alarm')
        if isinstance(ids, (int, long)):
            ids = [ids]
        event_alarms = self.browse(cursor, user, ids, context=context)
        alarm_ids = [a.calendar_alarm.id for a in event_alarms]
        event_ids = [x.event.id for x in event_alarms]
        if event_ids:
            # Update write_date of event
            event_obj.write(cursor, user, event_ids, {}, context=context)
        res = super(EventAlarm, self).delete(cursor, user, ids, context=context)
        if alarm_ids:
            alarm_obj.delete(cursor, user, alarm_ids, context=context)
        return res

    def valarm2values(self, cursor, user, alarm, context=None):
        alarm_obj = self.pool.get('calendar.alarm')
        return alarm_obj.valarm2values(cursor, user, alarm, context=context)

    def alarm2valarm(self, cursor, user, alarm, context=None):
        alarm_obj = self.pool.get('calendar.alarm')
        return alarm_obj.alarm2valarm(cursor, user, alarm, context=context)

EventAlarm()


class Attendee(ModelSQL, ModelView):
    'Attendee'
    _description = __doc__
    _name = 'calendar.attendee'

    email = fields.Char('Email', required=True, states={
        'readonly': 'active_id > 0',
        })
    status = fields.Selection([
        ('', ''),
        ('needs-action', 'Needs Action'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('tentative', 'Tentative'),
        ('delegated', 'Delegated'),
        ], 'Participation Status')
    attendee = fields.Binary('attendee')

    def default_status(self, cursor, user, context=None):
        return ''

    def _attendee2update(self, cursor, user, attendee, context=None):
        res = {}
        res['status'] = attendee.status
        return res

    def attendee2values(self, cursor, user, attendee, context=None):
        '''
        Convert a attendee object into values for create or write

        :param cursor: the database cursor
        :param user: the user id
        :param attendee: the attendee object
        :param context: the context
        :return: a dictionary with values
        '''
        res = {}
        if attendee.value.lower().startswith('mailto:'):
            res['email'] = attendee.value[7:]
        else:
            res['email'] = attendee.value
        res['status'] = ''
        if hasattr(attendee, 'partstat_param'):
            if attendee.partstat_param.lower() in dict(self.status.selection):
                res['status'] = attendee.partstat_param.lower()
        res['attendee'] = attendee.serialize()
        return res

    def attendee2attendee(self, cursor, user, attendee, context=None):
        '''
        Return a attendee instance of vobject for attendee

        :param cursor: the database cursor
        :param user: the user id
        :param attendee: a BrowseRecord of calendar.event.attendee
        :param context: the context
        :return: a attendee instance of vobject
        '''
        res = None
        if attendee.attendee:
            res = vobject.base.textLineToContentLine(
                    attendee.attendee.replace('\r\n ', ''))
        else:
            res = vobject.base.ContentLine('ATTENDEE', [], '')

        if attendee.status:
            if hasattr(res, 'partstat_param'):
                if res.partstat_param.lower() in dict(self.status.selection):
                    res.partstat_param = attendee.status.upper()
            else:
                res.partstat_param = attendee.status.upper()
        elif hasattr(res, 'partstat_param'):
            if res.partstat_param.lower() in dict(self.status.selection):
                del res.partstat_param

        res.value = 'MAILTO:' + attendee.email
        return res

Attendee()


class EventAttendee(ModelSQL, ModelView):
    'Attendee'
    _description = __doc__
    _name = 'calendar.event.attendee'
    _inherits = {'calendar.attendee': 'calendar_attendee'}

    calendar_attendee = fields.Many2One('calendar.attendee',
            'Calendar Attendee', required=True, ondelete='CASCADE', select=1)
    event = fields.Many2One('calendar.event', 'Event', ondelete='CASCADE',
            required=True, select=1)

    def create(self, cursor, user, values, context=None):
        event_obj = self.pool.get('calendar.event')
        if values.get('event'):
            # Update write_date of event
            event_obj.write(cursor, user, values['event'], {}, context=context)
        res = super(EventAttendee, self).create(cursor, user, values,
                context=context)
        attendee = self.browse(cursor, user, res, context=context)
        event = attendee.event
        if event.calendar.owner \
                and (event.organizer == event.calendar.owner.email \
                or (event.parent \
                and event.parent.organizer == event.parent.calendar.owner.email)):
            if event.organizer == event.calendar.owner.email:
                attendee_emails = [x.email for x in event.attendees
                        if x.email != event.organizer]
            else:
                attendee_emails = [x.email for x in event.parent.attendees
                        if x.email != event.parent.organizer]
            if attendee_emails:
                event_ids = event_obj.search(cursor, 0, [
                    ('uuid', '=', event.uuid),
                    ('calendar.owner.email', 'in', attendee_emails),
                    ('id', '!=', event.id),
                    ('recurrence', '=', event.recurrence or False),
                    ], context=context)
                for event_id in event_ids:
                    self.copy(cursor, 0, res, default={
                        'event': event_id,
                        }, context=context)
        return res

    def write(self, cursor, user, ids, values, context=None):
        event_obj = self.pool.get('calendar.event')
        if isinstance(ids, (int, long)):
            ids = [ids]
        event_ids = [x.event.id for x in self.browse(cursor, user, ids,
            context=context)]
        if values.get('event'):
            event_ids.append(values['event'])
        if event_ids:
            # Update write_date of event
            event_obj.write(cursor, user, event_ids, {}, context=context)

        if 'email' in values:
            values = values.copy()
            del values['email']

        res = super(EventAttendee, self).write(cursor, user, ids, values,
                context=context)
        attendees = self.browse(cursor, user, ids, context=context)
        for attendee in attendees:
            event = attendee.event
            if event.calendar.owner \
                    and (event.organizer == event.calendar.owner.email \
                    or (event.parent \
                    and event.parent.organizer == event.calendar.owner.email)):
                if event.organizer == event.calendar.owner.email:
                    attendee_emails = [x.email for x in event.attendees
                            if x.email != event.organizer]
                else:
                    attendee_emails = [x.email for x in event.parent.attendees
                            if x.email != event.parent.organizer]
                if attendee_emails:
                    attendee_ids = self.search(cursor, 0, [
                        ('event.uuid', '=', event.uuid),
                        ('event.calendar.owner.email', 'in', attendee_emails),
                        ('id', '!=', attendee.id),
                        ('event.recurrence', '=', event.recurrence or False),
                        ('email', '=', attendee.email),
                        ], context=context)
                    self.write(cursor, 0, attendee_ids, self._attendee2update(
                        cursor, user, attendee, context=context), context=context)
        return res

    def delete(self, cursor, user, ids, context=None):
        event_obj = self.pool.get('calendar.event')
        attendee_obj = self.pool.get('calendar.attendee')

        if isinstance(ids, (int, long)):
            ids = [ids]
        event_attendees = self.browse(cursor, user, ids, context=context)
        calendar_attendee_ids = [a.calendar_attendee.id \
                for a in event_attendees]
        event_ids = [x.event.id for x in event_attendees]
        if event_ids:
            # Update write_date of event
            event_obj.write(cursor, user, event_ids, {}, context=context)

        for attendee in self.browse(cursor, user, ids, context=context):
            event = attendee.event
            if event.calendar.owner \
                    and (event.organizer == event.calendar.owner.email \
                    or (event.parent \
                    and event.parent.organizer == event.calendar.owner.email)):
                if event.organizer == event.calendar.owner.email:
                    attendee_emails = [x.email for x in event.attendees
                            if x.email != event.organizer]
                else:
                    attendee_emails = [x.email for x in event.parent.attendees
                            if x.email != event.parent.organizer]
                if attendee_emails:
                    attendee_ids = self.search(cursor, 0, [
                        ('event.uuid', '=', event.uuid),
                        ('event.calendar.owner.email', 'in', attendee_emails),
                        ('id', '!=', attendee.id),
                        ('event.recurrence', '=', event.recurrence or False),
                        ('email', '=', attendee.email),
                        ], context=context)
                    self.delete(cursor, 0, attendee_ids, context=context)
            elif event.calendar.owner \
                    and ((event.organizer \
                    or (event.parent and event.parent.organizer)) \
                    and attendee.email == event.calendar.owner.email):
                if event.organizer:
                    organizer = event.organizer
                else:
                    organizer = event.parent.organizer
                attendee_ids = self.search(cursor, 0, [
                    ('event.uuid', '=', event.uuid),
                    ('event.calendar.owner.email', '=', organizer),
                    ('id', '!=', attendee.id),
                    ('event.recurrence', '=', event.recurrence or False),
                    ('email', '=', attendee.email),
                    ], context=context)
                if attendee_ids:
                    self.write(cursor, 0, attendee_ids, {
                        'status': 'declined',
                        }, context=context)
        res = super(EventAttendee, self).delete(cursor, user, ids, context=context)
        if calendar_attendee_ids:
            attendee_obj.delete(cursor, user, calendar_attendee_ids,
                    context=context)
        return res

    def copy(self, cursor, user, ids, default=None, context=None):
        attendee_obj = self.pool.get('calendar.attendee')

        int_id = False
        if isinstance(ids, (int, long)):
            int_id = True
            ids = [ids]
        if default is None:
            default = {}
        default = default.copy()
        new_ids = []
        for attendee in self.browse(cursor, user, ids, context=context):
            default['calendar_attendee'] = attendee_obj.copy(cursor, user,
                    attendee.calendar_attendee.id, context=context)
            new_id = super(EventAttendee, self).copy(cursor, user, attendee.id,
                    default=default, context=context)
            new_ids.append(new_id)
        if int_id:
            return new_ids[0]
        return new_ids

    def _attendee2update(self, cursor, user, attendee, context=None):
        attendee_obj = self.pool.get('calendar.attendee')
        return attendee_obj._attendee2update(cursor, user, attendee,
                context=context)

    def attendee2values(self, cursor, user, attendee, context=None):
        attendee_obj = self.pool.get('calendar.attendee')
        return attendee_obj.attendee2values(cursor, user, attendee,
                context=context)

    def attendee2attendee(self, cursor, user, attendee, context=None):
        attendee_obj = self.pool.get('calendar.attendee')
        return attendee_obj.attendee2attendee(cursor, user, attendee,
                context=context)

EventAttendee()


class RDate(ModelSQL, ModelView):
    'Recurrence Date'
    _description = __doc__
    _name = 'calendar.rdate'
    _rec_name = 'datetime'

    date = fields.Boolean('Is Date', help='Ignore time of field "Date", ' \
            'but handle as date only.')
    datetime = fields.DateTime('Date', required=True)

    def _date2update(self, cursor, user, date, context=None):
        res = {}
        res['date'] = date.date
        res['datetime'] = date.datetime
        return res

    def date2values(self, cursor, user, date, context=None):
        '''
        Convert a date object into values for create or write

        :param cursor: the database cursor
        :param user: the user id
        :param date: the date object
        :param context: the context
        :return: a dictionary with values
        '''
        res = {}
        if not isinstance(date, datetime.datetime):
            res['date'] = True
            res['datetime'] = datetime.datetime.combine(date,
                    datetime.time())
        else:
            res['date'] = False
            if date.tzinfo:
                res['datetime'] = date.astimezone(tzlocal)
            else:
                res['datetime'] = date
        return res

    def date2date(self, cursor, user, date, context=None):
        '''
        Return a datetime for date

        :param cursor: the database cursor
        :param user: the user id
        :param date: a BrowseRecord of calendar.rdate or
            calendar.exdate
        :param context: the context
        :return: a datetime
        '''
        if date.date:
            res = date.datetime.date()
        else:
            # Convert to UTC as sunbird doesn't handle tzid
            res = date.datetime.replace(tzinfo=tzlocal).astimezone(tzutc)
        return res

RDate()


class EventRDate(ModelSQL, ModelView):
    'Recurrence Date'
    _description = __doc__
    _name = 'calendar.event.rdate'
    _inherits = {'calendar.rdate': 'calendar_rdate'}
    _rec_name = 'datetime'

    calendar_rdate = fields.Many2One('calendar.rdate', 'Calendar RDate',
            required=True, ondelete='CASCADE', select=1)
    event = fields.Many2One('calendar.event', 'Event', ondelete='CASCADE',
            select=1, required=True)

    def create(self, cursor, user, values, context=None):
        event_obj = self.pool.get('calendar.event')
        if values.get('event'):
            # Update write_date of event
            event_obj.write(cursor, user, values['event'], {}, context=context)
        return super(EventRDate, self).create(cursor, user, values,
                context=context)

    def write(self, cursor, user, ids, values, context=None):
        event_obj = self.pool.get('calendar.event')
        if isinstance(ids, (int, long)):
            ids = [ids]
        event_ids = [x.event.id for x in self.browse(cursor, user, ids,
            context=context)]
        if values.get('event'):
            event_ids.append(values['event'])
        if event_ids:
            # Update write_date of event
            event_obj.write(cursor, user, event_ids, {}, context=context)
        return super(EventRDate, self).write(cursor, user, ids, values,
                context=context)

    def delete(self, cursor, user, ids, context=None):
        event_obj = self.pool.get('calendar.event')
        rdate_obj = self.pool.get('calendar.rdate')
        if isinstance(ids, (int, long)):
            ids = [ids]
        event_rdates = self.browse(cursor, user, ids, context=context)
        rdate_ids = [a.calendar_rdate.id for a in event_rdates]
        event_ids = [x.event.id for x in event_rdates]
        if event_ids:
            # Update write_date of event
            event_obj.write(cursor, user, event_ids, {}, context=context)
        res = super(EventRDate, self).delete(cursor, user, ids, context=context)
        if rdate_ids:
            rdate_obj.delete(cursor, user, rdate_ids, context=context)
        return res

    def _date2update(self, cursor, user, date, context=None):
        date_obj = self.pool.get('calendar.rdate')
        return date_obj._date2update(cursor, user, date, context=context)

    def date2values(self, cursor, user, date, context=None):
        date_obj = self.pool.get('calendar.rdate')
        return date_obj.date2values(cursor, user, date, context=context)

    def date2date(self, cursor, user, date, context=None):
        date_obj = self.pool.get('calendar.rdate')
        return date_obj.date2date(cursor, user, date, context=context)

EventRDate()


class EventExDate(EventRDate):
    'Exception Date'
    _description = __doc__
    _name = 'calendar.event.exdate'

EventExDate()


class RRule(ModelSQL, ModelView):
    'Recurrence Rule'
    _description = __doc__
    _name = 'calendar.rrule'
    _rec_name = 'freq'

    freq = fields.Selection([
        ('secondly', 'Secondly'),
        ('minutely', 'Minutely'),
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ], 'Frequency', required=True)
    until_date = fields.Boolean('Is Date', help='Ignore time of field ' \
            '"Until Date", but handle as date only.')
    until = fields.DateTime('Until Date')
    count = fields.Integer('Count')
    interval = fields.Integer('Interval')
    bysecond = fields.Char('By Second')
    byminute = fields.Char('By Minute')
    byhour = fields.Char('By Hour')
    byday = fields.Char('By Day')
    bymonthday = fields.Char('By Month Day')
    byyearday = fields.Char('By Year Day')
    byweekno = fields.Char('By Week Number')
    bymonth = fields.Char('By Month')
    bysetpos = fields.Char('By Position')
    wkst = fields.Selection([
        ('su', 'Sunday'),
        ('mo', 'Monday'),
        ('tu', 'Tuesday'),
        ('we', 'Wednesday'),
        ('th', 'Thursday'),
        ('fr', 'Friday'),
        ('sa', 'Saturday'),
        ], 'Week Day', sort=False)

    def __init__(self):
        super(RRule, self).__init__()
        self._sql_constraints += [
            ('until_count_only_one',
                'CHECK(until IS NULL OR count IS NULL OR count = 0)',
                'Only one of "until" and "count" can be set!'),
        ]
        self._constraints += [
            ('check_bysecond', 'invalid_bysecond'),
            ('check_byminute', 'invalid_byminute'),
            ('check_byhour', 'invalid_byhour'),
            ('check_byday', 'invalid_byday'),
            ('check_bymonthday', 'invalid_bymonthday'),
            ('check_byyearday', 'invalid_byyearday'),
            ('check_byweekno', 'invalid_byweekno'),
            ('check_bymonth', 'invalid_bymonth'),
            ('check_bysetpos', 'invalid_bysetpos'),
        ]
        self._error_messages.update({
            'invalid_bysecond': 'Invalid "By Second"',
            'invalid_byminute': 'Invalid "By Minute"',
            'invalid_byhour': 'Invalid "By Hour"',
            'invalid_byday': 'Invalid "By Day"',
            'invalid_bymonthday': 'Invalid "By Month Day"',
            'invalid_byyearday': 'Invalid "By Year Day"',
            'invalid_byweekno': 'Invalid "By Week Number"',
            'invalid_bymonth': 'Invalid "By Month"',
            'invalid_bysetpos': 'Invalid "By Position"',
        })

    def init(self, cursor, module_name):
        # Migrate from 1.4: unit_count replaced by until_count_only_one
        table  = TableHandler(cursor, self, module_name)
        table.drop_constraint('until_count')
        return super(RRule, self).init(cursor, module_name)

    def check_bysecond(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.bysecond:
                continue
            for second in rule.bysecond.split(','):
                try:
                    second = int(second)
                except:
                    return False
                if not (second >= 0 and second <= 59):
                    return False
        return True

    def check_byminute(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.byminute:
                continue
            for minute in rule.byminute.split(','):
                try:
                    minute = int(minute)
                except:
                    return False
                if not (minute >= 0 and minute <= 59):
                    return False
        return True

    def check_byhour(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.byhour:
                continue
            for hour in rule.byhour.split(','):
                try:
                    hour = int(hour)
                except:
                    return False
                if not (hour >= 0 and hour <= 23):
                    return False
        return True

    def check_byday(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.byday:
                continue
            for weekdaynum in rule.byday.split(','):
                weekday = weekdaynum[-2:]
                if weekday not in ('SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'):
                    return False
                ordwk = weekday[:-2]
                if not ordwk:
                    continue
                try:
                    ordwk = int(ordwk)
                except:
                    return False
                if not (abs(ordwk) >= 1 and abs(ordwk) <= 53):
                    return False
        return True

    def check_bymonthday(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.bymonthday:
                continue
            for monthdaynum in rule.bymonthday.split(','):
                try:
                    monthdaynum = int(monthdaynum)
                except:
                    return False
                if not (abs(monthdaynum) >= 1 and abs(monthdaynum) <= 31):
                    return False
        return True

    def check_byyearday(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.byyearday:
                continue
            for yeardaynum in rule.byyearday.split(','):
                try:
                    yeardaynum = int(yeardaynum)
                except:
                    return False
                if not (abs(yeardaynum) >= 1 and abs(yeardaynum) <= 366):
                    return False
        return True

    def check_byweekno(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.byweekno:
                continue
            for weeknum in rule.byweekno.split(','):
                try:
                    weeknum = int(weeknum)
                except:
                    return False
                if not (abs(weeknum) >= 1 and abs(weeknum) <= 53):
                    return False
        return True

    def check_bymonth(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.bymonth:
                continue
            for monthnum in rule.bymonth.split(','):
                try:
                    monthnum = int(monthnum)
                except:
                    return False
                if not (monthnum >= 1 and monthnum <= 12):
                    return False
        return True

    def check_bysetpos(self, cursor, user, ids):
        for rule in self.browse(cursor, user, ids):
            if not rule.bysetpos:
                continue
            for setposday in rule.bysetpos.split(','):
                try:
                    setposday = int(setposday)
                except:
                    return False
                if not (abs(setposday) >= 1 and abs(setposday) <= 366):
                    return False
        return True

    def _rule2update(self, cursor, user, rule, context=None):
        res = {}
        for field in ('freq', 'until_date', 'until', 'count', 'interval',
                'bysecond', 'byminute', 'byhour', 'byday', 'bymonthday',
                'byyearday', 'byweekno', 'bymonth', 'bysetpos', 'wkst'):
            res[field] = rule[field]
        return res

    def rule2values(self, cursor, user, rule, context=None):
        '''
        Convert a rule object into values for create or write

        :param cursor: the database cursor
        :param user: the user id
        :param rule: teh rule object
        :param context: the context
        :return: a dictionary with values
        '''
        res = {}
        for attr in str(rule.value).replace('\\', '').split(';'):
            field, value = attr.split('=')
            field = field.lower()
            if field == 'until':
                try:
                    value = vobject.icalendar.stringToDateTime(value)
                except:
                    value = vobject.icalendar.stringToDate(value)
                if not isinstance(value, datetime.datetime):
                    res['until_date'] = True
                    res['until'] = datetime.datetime.combine(value,
                            datetime.time())
                else:
                    res['until_date'] = False
                    if value.tzinfo:
                        res['until'] = value.astimezone(tzlocal)
                    else:
                        res['until'] = value
            elif field in ('freq', 'wkst'):
                res[field] = value.lower()
            else:
                res[field] = value
        return res

    def rule2rule(self, cursor, user, rule, context=None):
        '''
        Return a rule string for rule

        :param cursor: the database cursor
        :param user: the user id
        :param rule: a BrowseRecord of calendar.rrule or
            calendar.exrule
        :param context: the context
        :return: a string
        '''
        res = 'FREQ=' + rule.freq.upper()
        if rule.until:
            res += ';UNTIL='
            if rule.until_date:
                res += vobject.icalendar.dateToString(rule.until.date())
            else:
                res += vobject.icalendar.dateTimeToString(rule.until\
                        .replace(tzinfo=tzlocal).astimezone(tzutc),
                        convertToUTC=True)
        elif rule.count:
            res += ';COUNT=' + str(rule.count)
        for field in ('freq', 'wkst'):
            if rule[field]:
                res += ';' + field.upper() + '=' + rule[field].upper()
        for field in ('interval', 'bysecond', 'byminute', 'byhour',
                'byday', 'bymonthday', 'byyearday', 'byweekno',
                'bymonth', 'bysetpos'):
            if rule[field]:
                res += ';' + field.upper() + '=' + str(rule[field])
        return res

RRule()


class EventRRule(ModelSQL, ModelView):
    'Recurrence Rule'
    _description = __doc__
    _name = 'calendar.event.rrule'
    _inherits = {'calendar.rrule': 'calendar_rrule'}
    _rec_name = 'freq'

    calendar_rrule = fields.Many2One('calendar.rrule', 'Calendar RRule',
            required=True, ondelete='CASCADE', select=1)
    event = fields.Many2One('calendar.event', 'Event', ondelete='CASCADE',
            select=1, required=True)


    def create(self, cursor, user, values, context=None):
        event_obj = self.pool.get('calendar.event')
        if values.get('event'):
            # Update write_date of event
            event_obj.write(cursor, user, values['event'], {}, context=context)
        return super(EventRRule, self).create(cursor, user, values, context=context)

    def write(self, cursor, user, ids, values, context=None):
        event_obj = self.pool.get('calendar.event')
        if isinstance(ids, (int, long)):
            ids = [ids]
        event_ids = [x.event.id for x in self.browse(cursor, user, ids,
            context=context)]
        if values.get('event'):
            event_ids.append(values['event'])
        if event_ids:
            # Update write_date of event
            event_obj.write(cursor, user, event_ids, {}, context=context)
        return super(EventRRule, self).write(cursor, user, ids, values, context=context)

    def delete(self, cursor, user, ids, context=None):
        event_obj = self.pool.get('calendar.event')
        rrule_obj = self.pool.get('calendar.rrule')
        if isinstance(ids, (int, long)):
            ids = [ids]
        event_rrules = self.browse(cursor, user, ids, context=context)
        rrule_ids = [a.calendar_rrule.id for a in event_rrules]
        event_ids = [x.event.id for x in event_rrules]
        if event_ids:
            # Update write_date of event
            event_obj.write(cursor, user, event_ids, {}, context=context)
        res = super(EventRRule, self).delete(cursor, user, ids, context=context)
        if rrule_ids:
            rrule_obj.delete(cursor, user, rrule_ids, context=context)
        return res

    def _rule2update(self, cursor, user, rule, context=None):
        rule_obj = self.pool.get('calendar.rrule')
        return rule_obj._rule2update(cursor, user, rule, context=context)

    def rule2values(self, cursor, user, rule, context=None):
        rule_obj = self.pool.get('calendar.rrule')
        return rule_obj.rule2values(cursor, user, rule, context=context)

    def rule2rule(self, cursor, user, rule, context=None):
        rule_obj = self.pool.get('calendar.rrule')
        return rule_obj.rule2rule(cursor, user, rule, context=context)

EventRRule()


class EventExRule(EventRRule):
    'Exception Rule'
    _description = __doc__
    _name = 'calendar.event.exrule'

EventExRule()
