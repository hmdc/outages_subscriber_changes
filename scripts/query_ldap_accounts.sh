#!/bin/bash

CREATED=$(date '+%Y%m%d000000Z' --date="1 week ago")
DISABLED=$(date '+%s' --date="6 months ago")

# all active users
ldapsearch -LLL -x -o ldif-wrap=no "(&(!(eduPersonEntitlement=disabled))(uid=*))" gecos mail | grep -Pzo "[a-zA-Z0-9.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+" | sort | uniq | tr "[:upper:]" "[:lower:]" > /tmp/all_active_rce_users.list

# new users
ldapsearch -LLL -x -o ldif-wrap=no "(&(!(eduPersonEntitlement=disabled))(uid=*)(createTimestamp>=${CREATED}))" gecos mail | grep -Pzo "[a-zA-Z0-9.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+" | sort | uniq | tr "[:upper:]" "[:lower:]" > /tmp/new_active_rce_users.list

# disabled users
ldapsearch -LLL -x -o ldif-wrap=no "(&(eduPersonEntitlement=disabled)(uid=*)(sambaPwdMustChange<=${DISABLED}))" gecos mail | grep -Pzo "[a-zA-Z0-9.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+" | sort | uniq | tr "[:upper:]" "[:lower:]" > /tmp/disabled_rce_users.list