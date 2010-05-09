# -*- coding: utf-8 -*-
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name' : 'Calendar',
    'name_de_DE' : 'Kalender',
    'name_es_CO' : 'Calendario',
    'name_es_ES' : 'Calendario',
    'name_fr_FR' : 'Calendrier',
    'version' : '1.6.1',
    'author' : 'B2CK',
    'email': 'info@b2ck.com',
    'website': 'http://www.tryton.org/',
    'description': 'Add CalDAV support',
    'description_de_DE' : 'Fügt Unterstützung für CalDAV hinzu',
    'description_es_CO' : 'Añade soporte para CalDAV',
    'description_es_ES' : 'Añade soporte para CalDAV',
    'description_fr_FR': 'Ajoute le support CalDAV',
    'depends' : [
        'ir',
        'res',
        'webdav',
    ],
    'xml' : [
        'calendar.xml',
    ],
    'translation': [
        'de_DE.csv',
        'es_CO.csv',
        'es_ES.csv',
        'fr_FR.csv',
    ],
}
