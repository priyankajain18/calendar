#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
_TRYTON_RELOAD = False

from DAV import propfind
from DAV.errors import *
from DAV.utils import get_uriparentpath
from DAV.constants import DAV_VERSION_1, DAV_VERSION_2
from trytond.protocols.webdav import TrytonDAVInterface, USER_ID, CACHE, \
        DATABASE, WebDAVAuthRequestHandler
from trytond.pool import Pool
import urlparse
import urllib
from string import atoi
import xml.dom.minidom
domimpl = xml.dom.minidom.getDOMImplementation()

TrytonDAVInterface.PROPS['urn:ietf:params:xml:ns:caldav'] = (
        'calendar-description',
        'calendar-data',
        'calendar-home-set',
        'calendar-user-address-set',
        'schedule-inbox-URL',
        'schedule-outbox-URL',
    )
TrytonDAVInterface.PROPS['DAV:'] = tuple(list(TrytonDAVInterface.PROPS['DAV:']) \
        + ['principal-collection-set'])
TrytonDAVInterface.M_NS['urn:ietf:params:xml:ns:caldav'] = '_get_caldav'
DAV_VERSION_1['version'] += ',calendar-access,calendar-schedule'#,calendar-auto-schedule'
DAV_VERSION_2['version'] += ',calendar-access,calendar-schedule'#,calendar-auto-schedule'

_mk_prop_response = propfind.PROPFIND.mk_prop_response

def mk_prop_response(self, uri, good_props, bad_props, doc):
    res = _mk_prop_response(self, uri, good_props, bad_props, doc)
    parent_uri = get_uriparentpath(uri and uri.strip('/') or '')
    if not parent_uri:
        return res
    dbname, parent_uri = TrytonDAVInterface.get_dburi(parent_uri)
    if  parent_uri in ('Calendars', 'Calendars/'):
        ad = doc.createElement('calendar')
        ad.setAttribute('xmlns', 'urn:ietf:params:xml:ns:caldav')
        #Disable groupdav attribute for iPhone
        #vc = doc.createElement('vevent-collection')
        #vc.setAttribute('xmlns', 'http://groupdav.org/')
        cols = res.getElementsByTagName('D:collection')
        if cols:
            cols[0].parentNode.appendChild(ad)
            #cols[0].parentNode.appendChild(vc)
    return res

propfind.PROPFIND.mk_prop_response = mk_prop_response

def _get_caldav_calendar_description(self, uri):
    dbname, dburi = self._get_dburi(uri)
    if not dbname:
        raise DAV_NotFound
    cursor = DATABASE['cursor']
    pool = Pool(DATABASE['dbname'])
    try:
        collection_obj = pool.get('webdav.collection')
    except KeyError:
        raise DAV_NotFound
    try:
        res = collection_obj.get_calendar_description(cursor, int(USER_ID), dburi,
                cache=CACHE)
    except AttributeError:
        raise DAV_NotFound
    except (DAV_Error, DAV_NotFound, DAV_Secret, DAV_Forbidden), exception:
        self._log_exception(exception)
        raise
    except Exception, exception:
        self._log_exception(exception)
        raise DAV_Error(500)
    return res

TrytonDAVInterface._get_caldav_calendar_description = _get_caldav_calendar_description

def _get_caldav_calendar_data(self, uri):
    dbname, dburi = self._get_dburi(uri)
    if not dbname:
        raise DAV_NotFound
    cursor = DATABASE['cursor']
    pool = Pool(DATABASE['dbname'])
    try:
        collection_obj = pool.get('webdav.collection')
    except KeyError:
        raise DAV_NotFound
    try:
        res = collection_obj.get_calendar_data(cursor, int(USER_ID), dburi,
                cache=CACHE)
    except AttributeError:
        raise DAV_NotFound
    except (DAV_Error, DAV_NotFound, DAV_Secret, DAV_Forbidden), exception:
        self._log_exception(exception)
        raise
    except Exception, exception:
        self._log_exception(exception)
        raise DAV_Error(500)
    return res

TrytonDAVInterface._get_caldav_calendar_data = _get_caldav_calendar_data

def _get_caldav_calendar_home_set(self, uri):
    dbname, dburi = self._get_dburi(uri)
    if not dbname:
        raise DAV_NotFound
    cursor = DATABASE['cursor']
    pool = Pool(DATABASE['dbname'])
    try:
        collection_obj = pool.get('webdav.collection')
    except KeyError:
        raise DAV_NotFound
    try:
        res = collection_obj.get_calendar_home_set(cursor, int(USER_ID), dburi,
                cache=CACHE)
    except AttributeError:
        raise DAV_NotFound
    except (DAV_Error, DAV_NotFound, DAV_Secret, DAV_Forbidden), exception:
        self._log_exception(exception)
        raise
    except Exception, exception:
        self._log_exception(exception)
        raise DAV_Error(500)
    uparts = list(urlparse.urlsplit(uri))
    uparts[2] = urllib.quote(dbname + res)
    doc = domimpl.createDocument(None, 'href', None)
    href = doc.documentElement
    href.tagName = 'D:href'
    #iPhone doesn't handle "http" in href
    #huri = doc.createTextNode(urlparse.urlunsplit(uparts))
    huri = doc.createTextNode(urllib.quote('/' + dbname + res))
    href.appendChild(huri)
    return href

TrytonDAVInterface._get_caldav_calendar_home_set = _get_caldav_calendar_home_set

def _get_caldav_calendar_user_address_set(self, uri):
    dbname, dburi = self._get_dburi(uri)
    if not dbname:
        raise DAV_NotFound
    cursor = DATABASE['cursor']
    pool = Pool(DATABASE['dbname'])
    try:
        collection_obj = pool.get('webdav.collection')
    except KeyError:
        raise DAV_NotFound
    try:
        res = collection_obj.get_calendar_user_address_set(cursor,
                int(USER_ID), dburi, cache=CACHE)
    except AttributeError:
        raise DAV_NotFound
    except (DAV_Error, DAV_NotFound, DAV_Secret, DAV_Forbidden), exception:
        self._log_exception(exception)
        raise
    except Exception, exception:
        self._log_exception(exception)
        raise DAV_Error(500)
    doc = domimpl.createDocument(None, 'href', None)
    href = doc.documentElement
    href.tagName = 'D:href'
    huri = doc.createTextNode('MAILTO:' + res)
    href.appendChild(huri)
    return href

TrytonDAVInterface._get_caldav_calendar_user_address_set = _get_caldav_calendar_user_address_set

def _get_caldav_schedule_inbox_URL(self, uri):
    dbname, dburi = self._get_dburi(uri)
    if not dbname:
        raise DAV_NotFound
    cursor = DATABASE['cursor']
    pool = Pool(DATABASE['dbname'])
    try:
        collection_obj = pool.get('webdav.collection')
    except KeyError:
        raise DAV_NotFound
    try:
        res = collection_obj.get_schedule_inbox_URL(cursor, int(USER_ID), dburi,
                cache=CACHE)
    except AttributeError:
        raise DAV_NotFound
    except (DAV_Error, DAV_NotFound, DAV_Secret, DAV_Forbidden), exception:
        self._log_exception(exception)
        raise
    except Exception, exception:
        self._log_exception(exception)
        raise DAV_Error(500)
    uparts = list(urlparse.urlsplit(uri))
    uparts[2] = urllib.quote(dbname + res)
    doc = domimpl.createDocument(None, 'href', None)
    href = doc.documentElement
    href.tagName = 'D:href'
    huri = doc.createTextNode(urlparse.urlunsplit(uparts))
    href.appendChild(huri)
    return href

TrytonDAVInterface._get_caldav_schedule_inbox_URL = _get_caldav_schedule_inbox_URL

def _get_caldav_schedule_outbox_URL(self, uri):
    dbname, dburi = self._get_dburi(uri)
    if not dbname:
        raise DAV_NotFound
    cursor = DATABASE['cursor']
    pool = Pool(DATABASE['dbname'])
    try:
        collection_obj = pool.get('webdav.collection')
    except KeyError:
        raise DAV_NotFound
    try:
        res = collection_obj.get_schedule_outbox_URL(cursor, int(USER_ID), dburi,
                cache=CACHE)
    except AttributeError:
        raise DAV_NotFound
    except (DAV_Error, DAV_NotFound, DAV_Secret, DAV_Forbidden), exception:
        self._log_exception(exception)
        raise
    except Exception, exception:
        self._log_exception(exception)
        raise DAV_Error(500)
    uparts = list(urlparse.urlsplit(uri))
    uparts[2] = urllib.quote(dbname + res)
    doc = domimpl.createDocument(None, 'href', None)
    href = doc.documentElement
    href.tagName = 'D:href'
    huri = doc.createTextNode(urlparse.urlunsplit(uparts))
    href.appendChild(huri)
    return href

TrytonDAVInterface._get_caldav_schedule_outbox_URL = _get_caldav_schedule_outbox_URL

_prev_get_dav_principal_collection_set = hasattr(TrytonDAVInterface,
        '_get_dav_principal_collection_set') and \
                TrytonDAVInterface._get_dav_principal_collection_set or None

def _get_dav_principal_collection_set(self, uri):
    dbname, dburi = self._get_dburi(uri)
    if dburi.startswith('Calendars'):
        uparts = list(urlparse.urlsplit(uri))
        uparts[2] = urllib.quote(dbname + '/Calendars/')
        doc = domimpl.createDocument(None, 'href', None)
        href = doc.documentElement
        href.tagName = 'D:href'
        huri = doc.createTextNode(urlparse.urlunsplit(uparts))
        href.appendChild(huri)
        return href
    if _prev_get_dav_principal_collection_set:
        return _prev_get_dav_principal_collection_set(self, uri)
    raise DAV_NotFound

TrytonDAVInterface._get_dav_principal_collection_set = _get_dav_principal_collection_set

def _get_caldav_post(self, uri, body, contenttype=''):
    dbname, dburi = self._get_dburi(uri)
    if not dbname:
        raise DAV_Forbidden
    cursor = DATABASE['cursor']
    pool = Pool(DATABASE['dbname'])
    calendar_obj = pool.get('calendar.calendar')
    try:
        res = calendar_obj.post(cursor, int(USER_ID), dburi, body)
    except AttributeError:
        raise DAV_NotFound
    except (DAV_Error, DAV_NotFound, DAV_Secret, DAV_Forbidden), exception:
        self._log_exception(exception)
        raise
    except Exception, exception:
        self._log_exception(exception)
        raise DAV_Error(500)
    return res

TrytonDAVInterface._get_caldav_post = _get_caldav_post

_prev_do_POST = WebDAVAuthRequestHandler.do_POST

def do_POST(self):
    dc=self.IFACE_CLASS

    uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
    uri=urllib.unquote(uri)

    dbname, dburi = TrytonDAVInterface.get_dburi(uri)
    if dburi.startswith('Calendars'):
        # read the body
        body=None
        if self.headers.has_key("Content-Length"):
            l=self.headers['Content-Length']
            body=self.rfile.read(atoi(l))
        ct=None
        if self.headers.has_key("Content-Type"):
            ct=self.headers['Content-Type']

        headers = {}

        try:
            DATA = '%s\n' % dc._get_caldav_post(uri, body, ct)
        except DAV_Error, (ec, dd):
            return self.send_status(ec)
        self.send_body_chunks(DATA, '200', 'OK', 'OK')
        return
    return _prev_do_POST(self)

WebDAVAuthRequestHandler.do_POST = do_POST
