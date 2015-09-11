# Outages Mailing List Subscriber Changes

Finds changes in Outages subscribers for new or disabled accounts. At HMDC, this package is installed on the rce-services VM.

## Part 1: LDAP Searches

The script `query_ldap_accounts.sh` performs three LDAP queries:

 1. Finds all non-disabled LDAP user accounts.
 2. Finds all non-disabled LDAP user accounts created in the last week.
 3. Finds all disabled LDAP user accounts.

The results of each query are saved to files (with `.list` extensions) under `/tmp`. If being called via the weekly cronjob, the second part (the Python script `find_subscriber_changes.py`) will execute immediately following the LDAP queries.

## Part 2: List Comparisons and Filters

The script `find_subscriber_changes.py` executes secondly, in phases:

  1. Scrapes the Outages mailing list member management page for a list of subscriber emails. (We have admin but do not host the list at HMDC.)
  2. Cleans up the three lists obtained via LDAP queries above. Each list is read in, one email address per line. Since some addresses are invalid, they are parsed out by comparing it to the next one on the list. If the address is a substring of the next, it's discarded. A list of valid email addresses is returned.
  3. Some users may have had an account in the past that is now disabled. So their email isn't removed from the list (by virtue of being disabled) it is discarded.
  4. The list of recently created accounts is checked against the list of subscribers that was scraped from Mailman. If the email address is found, it is discarded. Otherwise it stays on the list of emails to add.
  5. The list of disabled user accounts is checked against the list of subscribers. Only if the disabled account is still subscribed should it be added to the list of emails to remove.
  6. Finally, an email containing the addresses to add and remove is sent out.