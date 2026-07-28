# AtlRemoveUsersGroup

Remove non-active users from an Atlassian Cloud group.

This script fetches group members from a Jira site, retrieves Atlassian organization user statuses, and removes users from the specified group when their account status is not `active`.

## Requirements

- Python 3.8+ (or compatible)
- `requests` Python package
- Network access to your Atlassian site and Atlassian admin APIs

## Environment variables

The script requires the following environment variables:

- `ATLASSIAN_TOKEN` - Bearer token for Atlassian Admin API
- `ATLASSIAN_ORG` - Organization ID for Atlassian Admin API
- `JIRA_EMAIL` - Service account email for Jira REST API Basic auth
- `JIRA_PAT` - API token for Jira REST API Basic auth

## Usage

```powershell
python AtlRemoveUsersGroup.py --site <your-site>.atlassian.net --group "Group Name"
```

Dry-run mode is the default. It writes a CSV report of group members and planned actions.

To actually remove users from the group, add `--execute`:

```powershell
python AtlRemoveUsersGroup.py --site <your-site>.atlassian.net --group "Group Name" --execute
```

## Options

- `-s`, `--site` : Atlassian site hostname, for example `example.atlassian.net`
- `-g`, `--group` : Group name to clean
- `--execute` : Actually remove non-active users from the group (default is dry-run)
- `--output` : CSV file to write results (default: `removals.csv`)

## Output

The script writes a CSV file with these columns:

- `accountId`
- `displayName`
- `email`
- `account_status`
- `action`
- `error`

Non-active users are marked as `will-remove` in dry-run mode and `removed` when `--execute` is used.
