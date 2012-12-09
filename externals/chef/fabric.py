from scalarizr.externals.chef import Search
from scalarizr.externals.chef.api import ChefAPI, autoconfigure
from scalarizr.externals.chef.exceptions import ChefError

class Roledef(object):
    def __init__(self, name, api, hostname_attr):
        self.name = name
        self.api = api
	self.hostname_attr = hostname_attr
	
    
    def __call__(self):

        for row in Search('node', 'roles:'+self.name, api=self.api):
            yield row.object.attributes.get_dotted(self.hostname_attr)


def chef_roledefs(api=None, hostname_attr = 'fqdn'):
    """Build a Fabric roledef dictionary from a Chef server.

    Example:

        from fabric.api import env, run, roles
        from scalarizr.externals.chef.fabric import chef_roledefs

        env.roledefs = chef_roledefs()

        @roles('web_app')
        def mytask():
            run('uptime')
            
    hostname_attr is the attribute in the chef node that holds the real hostname.
    to refer to a nested attribute, separate the levels with '.'.
    for example 'ec2.public_hostname'
    """
    api = api or ChefAPI.get_global() or autoconfigure()
    if not api:
        raise ChefError('Unable to load Chef API configuration')
    roledefs = {}
    for row in Search('role', api=api):
        name = row['name']
        roledefs[name] =  Roledef(name, api, hostname_attr)
    return roledefs
