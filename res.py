#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
import copy
from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Bool, Eval


class User(ModelSQL, ModelView):
    _name = 'res.user'

    calendars = fields.One2Many('calendar.calendar', 'owner', 'Calendars')

    def __init__(self):
        super(User, self).__init__()
        self.email = copy.copy(self.email)
        self.email.states = copy.copy(self.email.states)
        self.email.depends = copy.copy(self.email.depends)
        required = Bool(Eval('calendars'))
        if not self.email.states.get('required'):
            self.email.states['required'] = required
        else:
            self.email.states['required'] = (
                self.email.states['required'] | required)
        if 'calendars' not in self.email.depends:
            self.email.depends.append('calendars')

User()
