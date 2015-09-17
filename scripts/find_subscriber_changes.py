#!/usr/bin/env python

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from HTMLParser import HTMLParser
import argparse
import cookielib
import getopt
import hmdclogger
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

# Email recipient
recipient = "operations@help.hmdc.harvard.edu"

# Cookie variables
policy = cookielib.DefaultCookiePolicy(rfc2965=True)
cookiejar = cookielib.CookieJar(policy)
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookiejar)).open

# List variables
list_name = "outages"
list_url = "https://lists.hmdc.harvard.edu"
with open("/nfs/tools/extras/Outages_Mailing_List_Password", "r") as f:
    list_password = f.read().replace('\n', '')

# Parsing variables
letters = ['0']
maxchunk = 0
nomails = {}
processed_letters = []
subscribers = {}

# LDAP query results
all_active_users = "/tmp/all_active_rce_users.list"
new_active_users = "/tmp/new_active_rce_users.list"
disabled_users = "/tmp/disabled_rce_users.list"


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


def email_list(users_to_add, users_to_remove, recipient):
  """Formats the lists for email, creates the email, and sends it."""

  fromaddr = "ops@latte.harvard.edu"
  toaddr = recipient
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

  hmdclog.log('debug', "From: " + fromaddr)
  hmdclog.log('debug', "To: " + toaddr)

  server = smtplib.SMTP('localhost')
  text = msg.as_string()
  server.sendmail(fromaddr, toaddr, text)
  server.quit()

  hmdclog.log('debug', "Email sent.")


def exclude_active_users(all_active_users, disabled_users):
  """
  Some emails may be part of multiple accounts. In order to prevent active
  users from being removed from the list (as part of the disabled users list)
  this will remove the email address if it's attached to an active account.
  """

  users = []
  num_disabled = len(disabled_users)

  for email in disabled_users:
    if email not in all_active_users:
      users.append(email)
    else:
      hmdclog.log('debug', "DISCARDED: " + email)

  return users


def load_users_list(source):
  """Parses list of email addresses from a file into a list."""

  if os.path.isfile(source):
    hmdclog.log('debug', "Reading in LDAP users: " + source)
    users = [line.rstrip('\n') for line in open(source)]
  else:
    raise Exception("The file " + source + " was not found!")

  return users


def scrape_emails(name, password, url):
  """
  Connects to Mailman and scrapes emails from each page of the
  membership management section.
  """

  hmdclog.log('debug', "Begining mailing list subscriber scraping.")
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
  hmdclog.log('debug', "Subscribers found and sorted.")

  # save emails to a list
  hmdclog.log('debug', "Parsing out email addresses.")
  members = []
  for (email, name) in subscriberlist:
    address = email.replace("%40", "@")
    members.append(address)
    hmdclog.log('debug', "\tAdding email: " + address)

  hmdclog.log('debug', "Scraping complete.")
  return members


def parse_out_users(user_list, subscribers, is_in_list):
  """
  Disabled LDAP users only need to be marked for removal if they are still in
  the mailing list -- so check if the email is in subscribers.
  Active LDAP users only need to be marked for inclusion if they are not in
  the mailing list -- so check if the email is not in subscribers.
  """

  parsed_users = []
  num_users = len(user_list)

  for user in user_list:
    if is_in_list:
      # comparing disabled users to current subscribers
      if user in subscribers:
        hmdclog.log('debug', "FOUND: " + user + " (appended to list)")
        parsed_users.append(user)
    else:
      # comparing active users to current subscribers
      if user not in subscribers:
        hmdclog.log('debug', "NOT FOUND: " + user + " (appended to list)")
        parsed_users.append(user)

  return parsed_users


if __name__ == '__main__':
  # Setup argument parsing with the argparse module.
  parser = argparse.ArgumentParser(description="Manage RCE group quotas.")
  parser.add_argument('-d', '--debug', action='store_true',
                      help="Enables verbose output.")
  args = parser.parse_args()

  # Set logging level based on the debug argument.
  debug_level = 'DEBUG' if args.debug else 'NOTSET'
  hmdclog = hmdclogger.HMDCLogger("OutagesSubscribers", debug_level)
  hmdclog.log_to_console()

  # Scrape Mailman for Outages list subscribers.
  subscribers = scrape_emails(list_name, list_password, list_url)
  hmdclog.log('debug', "")

  # Read in list of LDAP users.
  all_active_users = load_users_list(all_active_users)
  new_active_users = load_users_list(new_active_users)
  disabled_users = load_users_list(disabled_users)

  # Compare lists to each other.
  hmdclog.log('debug', "Exclude active users that have a disabled account.")
  disabled_users = exclude_active_users(all_active_users, disabled_users)
  hmdclog.log('debug', "")
  hmdclog.log('debug', "Looking for active users not in the subscriber list.")
  new_active_users = parse_out_users(new_active_users, subscribers, False)
  hmdclog.log('debug', "")
  hmdclog.log('debug', "Looking for disabled users in the subscriber list.")
  disabled_users = parse_out_users(disabled_users, subscribers, True)
  hmdclog.log('debug', "")

  # Email the resulting list.
  email_list(new_active_users, disabled_users, recipient)
