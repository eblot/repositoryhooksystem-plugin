from repository_hook_system.interface import IRepositoryHookSubscriber
from repository_hook_system.trac_commit_hook import CommitHook
from trac.config import BoolOption, Option
from trac.core import Component, implements
from trac.ticket.api import ITicketManipulator
from trac.util.translation import tag_


class TicketChangeValidator(Component):
    implements(ITicketManipulator)

    # TODO: get ldap parameters from [ldap] section
    LDAP_URL = 'ldap://ldap.example.com'
    LDAP_BASE_DN = 'dc=example,dc=com'
    LDAP_PEOPLE = 'ou=people'
    ALLOWED_USERS = ('< default >',)

    enforce_valid_ldap_user = BoolOption('ticket',
        'enforce_valid_ldap_user', False,
        """Whether to enforce reporter and owner to be valid ldap users""")
    valid_ldap_user_filter = Option('ticket', 'valid_ldap_user_filter',
        '(|(EmployeeType=employee)(EmployeeType=contractor))',
        """LDAP filter that matches valid employees""")
    forbidden_milestones_on_close = Option('ticket',
        'forbidden_milestones_on_close', 'Next',
        """A ticket cannot be closed if its milestone is in that list""")
    forbidden_components_on_close = Option('ticket',
        'forbidden_components_on_close', 'Triage, None',
        """A ticket cannot be closed if its component is in that list""")

    def __init__(self):
        super(TicketChangeValidator, self).__init__()
        self._fbden_cp_on_close = [
            c.strip() for c in self.forbidden_components_on_close.split(',')]
        self._fbden_ms_on_close = [
            m.strip() for m in self.forbidden_milestones_on_close.split(',')]

    # ITicketManipulator implementation
    def prepare_ticket(self, req, ticket, fields, actions):
        pass

    def validate_ticket(self, req, ticket):
        # check that the component and milestone are not in the forbidden list
        # when the ticket is closed
        if ticket['status'] == 'closed' and \
                not req.perm.has_permission('TICKET_ADMIN'):
            if ticket['component'] in self._fbden_cp_on_close:
                yield 'component', tag_('Fix ticket component before closing')
            if ticket['milestone'] in self._fbden_ms_on_close:
                yield 'milestone', tag_('Fix ticket milestone before closing')

        if self.enforce_valid_ldap_user:
            import ldap
            # check that the reporter and owner are valid LDAP users

            con = None
            for field in ('reporter', 'owner'):
                if field not in ticket.values:
                    continue
                user = ticket.values[field]
                if user in self.ALLOWED_USERS:
                    continue
                if not ticket.exists or field in ticket._old:
                    # case of ticket creation or modification of the user
                    # a current employee should be assigned
                    base_dn = ','.join((self.LDAP_PEOPLE, self.LDAP_BASE_DN))
                    filter_ = '(&(uid=%s)%s)' % \
                              (user, self.valid_ldap_user_filter)
                    # connect to the ldap server
                    if not con:
                        con = ldap.initialize(self.LDAP_URL)
                        con.simple_bind_s()
                    # send request
                    res = con.search_s(base_dn, ldap.SCOPE_SUBTREE,
                                       filter_, ['uid'])
                    # report issue if any
                    if not res:
                        yield (field,
                               tag_("'%s' is not a valid user" % user))
            if con:
                con.unbind()
