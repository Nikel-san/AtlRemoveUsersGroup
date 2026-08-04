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
python AtlRemoveUsersGroup.py --site example.atlassian.net --group "Group Name"
```

Live execution is the default. Use `--dry-run` to preview removals without changing the group.

To preview planned removals without executing them, add `--dry-run`:

```powershell
python AtlRemoveUsersGroup.py --site example.atlassian.net --group "Group Name" --dry-run
```

## Options

- `-s`, `--site` : Atlassian site hostname, for example `example.atlassian.net` (env: `ATLASSIAN_SITE`)
- `-g`, `--group` : Group name to clean
- `-o`, `--org` : Organization ID for Atlassian Admin API (env: `ATLASSIAN_ORG`)
- `--dry-run` : Preview removals without executing them (default is live execution)
- `--out` : CSV file to write results (default: `atl_group_cleanup.csv`)

## Output

The script writes a CSV file with these columns:

- `email`
- `name`
- `account_id`
- `account_status`
- `action`

Non-active users are marked as `would-remove` in dry-run mode and `removed` in live mode. Failed removals are recorded as `failed`.
