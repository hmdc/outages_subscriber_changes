from distutils.core import setup

setup(author='Bradley Frank',
      author_email='bfrank@hmdc.harvard.edu',
      data_files=[
           ('/etc/cron.weekly', ['cron/HMDC_findOutagesListChanges'])],
      description='Find changes in subscriber emails and notifies HMDC.',
      license='GPLv2',
      name='OutagesSubscriberChanges',
      requires=[
           'cookielib',
           'getopt',
           'os',
           're',
           'smtplib',
           'string',
           'sys',
           'urllib',
           'urllib2'],
      scripts=['scripts/find_subscriber_changes.py', 'scripts/query_ldap_accounts.sh'],
      url='https://github.com/hmdc/outages-subscriber-changes',
      version='1.5',
)
