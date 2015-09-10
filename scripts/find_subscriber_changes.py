#!/usr/bin/env python

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from HTMLParser import HTMLParser
import cookielib
import getopt
import os
import re
import smtplib
import string
import sys
import urllib
import urllib2

__author__ = "Harvard-MIT Data Center DevOps"
__copyright__ = "Copyright 2015, HMDC"
__credits__ = ["Bradley Frank"]
__license__ = "GPL"
__maintainer__ = "HMDC"
__email__ = "ops@latte.harvard.edu"
__status__ = "Production"

"""
Parses and compares email addresses from enabled and disabled RCE accounts to
those subscribed to the Outages mailing list; produces a list of addresses that
should be added and removed to the mailing list.

Adapted from: http://starship.python.net/crew/jwt/mailman/#throughtheweb
See also: http://fog.ccsf.edu/~msapiro/scripts/mailman-subscribers.py
"""

# Cookie variables
policy = cookielib.DefaultCookiePolicy(rfc2965=True)
cookiejar = cookielib.CookieJar(policy)
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookiejar)).open

# List variables
list_name = "outages"
list_url = "https://lists.hmdc.harvard.edu"
with open ("/nfs/tools/extras/Outages_Mailing_List_Password", "r") as f:
    list_password = f.read().replace('\n', '')

# Parsing variables
letters = ['0']
maxchunk = 0
nomails = {}
processed_letters = []
subscribers = {}

# LDAP query results
all_active_rce_users = "/tmp/all_active_rce_users.list"
new_active_rce_users = "/tmp/new_active_rce_users.list"
disabled_rce_users = "/tmp/disabled_rce_users.list"


class MailmanHTMLParser(HTMLParser):
  """
  As the name implies, this handles parsing HTML. Hopefully this continues
  to work with no intervention needed. The script was made for Mailman 2.1.
  """

  def handle_starttag(self, tag, attrs):
    global maxchunk, letters

    if tag == 'input':
      s = False
      for a, v in attrs:
        if a == 'name' and v.endswith('_realname'):
          subemail = v[:-9]
          s = True
        elif a == 'value':
          subname = v

      if s and subemail not in subscribers:
        subscribers[subemail] = subname

      t = False
      for a, v in attrs:
        if a == 'name' and v.endswith('_nomail'):
          nmemail = v[:-7]
          t = True
        elif a == 'value':
          subnomail = v

      if t and nmemail not in nomails:
        nomails[nmemail] = subnomail

    if tag == 'a':
      for a, v in attrs:
        if a == 'href' and v.find('/mailman/admin/'):
          m = re.search(r'chunk=(?P<chunkno>\d+)', v, re.I)
          if m:
            if int(m.group('chunkno')) > maxchunk:
              maxchunk = int(m.group('chunkno'))
          m = re.search(r'letter=(?P<letter>[0-9a-z])', v, re.I)
          if m:
            letter = m.group('letter')
            if letter not in letters and letter not in processed_letters:
              letters.append(letter)


def scrape_emails(name, password, url):
  """
  Connects to Mailman and scrapes emails from each page of the
  membership management section.
  """

  global maxchunk, letters

  # set admin url
  member_url = url + "/mailman/admin/" + name + "/members"
  p = {'adminpw': password}

  # login, picking up the cookie
  page = opener(member_url, urllib.urlencode(p))
  page.close()
  p = {}

  # loop through the letters, and all chunks of each
  while len(letters) > 0:
    letter = letters[0]
    letters = letters[1:]
    processed_letters.append(letter)
    chunk = 0
    maxchunk = 0

    while chunk <= maxchunk:
      page = opener(member_url + "?letter=%s&chunk=%d" % (letter, chunk))
      lines = page.read()
      page.close()

      parser = MailmanHTMLParser()
      parser.feed(lines)
      parser.close()
      chunk += 1

  subscriberlist = subscribers.items()
  subscriberlist.sort()

  # save emails to a list
  members = []
  for (email, name) in subscriberlist:
    members.append(email.replace("%40", "@"))

  return members


def parse_ldap_users(source):
  """
  Email addresses are found in various LDAP attributes, and are sometimes
  cut off in the gecos field. Since the list should already be in alphabetical
  order, this function checks if the current address is a substring of the
  following email address. If it is, it's discarded.
  """

  ldap_users = []
  users = []

  if os.path.isfile(source):
    ldap_users = [line.rstrip('\n') for line in open(source)]
  else:
    raise Exception("The file " + source + " was not found!")

  num_ldap_users = len(ldap_users)

  for i in range(num_ldap_users):
    email = ldap_users[i]
    if i + 1 < num_ldap_users:
      next_email = ldap_users[i + 1]
      if email not in next_email:
        users.append(email)
    else:
      users.append(email)

  return users


def exclude_active_users(all_active_users, disabled_users):
  """
  Some emails may be part of multiple accounts. In order to prevent active
  users from being removed from the list (as part of the disabled users list)
  this will remove the email address if it's attached to an active account.
  """

  users = []

  for email in disabled_users:
    if email not in all_active_users:
      users.append(email)

  return users


def parse_out_users(user_list, subscribers, is_in_list):
  """
  If the email is a disabled account and does not exist in Outages, keep it.
  If the email is a new user and exists in Outages, discard it.
  """

  parsed_users = []

  for user in user_list:
    if is_in_list:
      # comparing disabled users to current subscribers
      if user in subscribers:
        parsed_users.append(user)
    else:
      # comparing active users to current subscribers
      if user not in subscribers:
        parsed_users.append(user)

  return parsed_users


def email_list(users_to_add, users_to_remove):
  """
  Formats the lists for email, creates the email, and sends it.
  """

  fromaddr = "ops@latte.harvard.edu"
  toaddr = "bfrank@hmdc.harvard.edu"
  msg = MIMEMultipart()
  msg['From'] = fromaddr
  msg['To'] = toaddr
  msg['Subject'] = "Outages mailing list changes"

  body = "Please visit " \
    "https://lists.hmdc.harvard.edu/mailman/admin/outages/members to add or " \
    "remove the following users from the Outages mailing list.\n"

  body = body + "\nUSERS TO ADD TO OUTAGES LIST\n"
  for user in users_to_add:
    body = body + user + "\n"

  body = body + "\nUSERS TO REMOVE FROM OUTAGES LIST\n"
  for user in users_to_remove:
    body = body + user + "\n"

  msg.attach(MIMEText(body, 'plain'))

  server = smtplib.SMTP('localhost')
  text = msg.as_string()
  server.sendmail(fromaddr, toaddr, text)
  server.quit()


if __name__ == '__main__':
  # scrape Mailman for Outages list subscribers
  subscribers = scrape_emails(list_name, list_password, list_url)

  # clean up emails generated by ldapsearch
  all_active_users = parse_ldap_users(all_active_rce_users)
  new_active_users = parse_ldap_users(new_active_rce_users)
  disabled_users = parse_ldap_users(disabled_rce_users)

  # compare lists to each other
  disabled_users = exclude_active_users(all_active_users, disabled_users)
  new_active_users = parse_out_users(new_active_users, subscribers, False)
  disabled_users = parse_out_users(disabled_users, subscribers, True)

  # email the complete list
  email_list(new_active_users, disabled_users)
