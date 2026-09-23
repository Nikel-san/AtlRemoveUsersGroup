# AtlRemoveUsersGroup

Remove non-active users from one or every Atlassian Cloud group.

This script fetches group members from a Jira site and removes users whose account status is not `active`. With `--all-groups`, it reads organization directory statuses and applies the cleanup to every organization group.

## Requirements

- Python 3.8+ (or compatible)
- `requests` Python package
- Network access to your Atlassian site and Atlassian Admin API

## Environment variables

The script requires the following environment variables:

- `ATLASSIAN_TOKEN` - Bearer token for Atlassian Admin API user directory status lookups
- `ATLASSIAN_ORG` - Organization ID for Atlassian Admin API user directory status lookups
- `JIRA_EMAIL` - Service account email for Jira REST API Basic auth
- `JIRA_PAT` - API token for Jira REST API Basic auth

## Usage

```powershell
python AtlRemoveUsersGroup.py --site example.atlassian.net --group "Group Name"
python AtlRemoveUsersGroup.py --site example.atlassian.net --all-groups --exclude-group "site-admins" --dry-run
```

Live execution is the default. Use `--dry-run` to preview removals without changing the group.

To preview planned removals without executing them, add `--dry-run`:

```powershell
python AtlRemoveUsersGroup.py --site example.atlassian.net --group "Group Name" --dry-run
```

## Options

- `-s`, `--site` : Atlassian site hostname, for example `example.atlassian.net` (env: `ATLASSIAN_SITE`)
- `-g`, `--group` : One group name to clean; mutually exclusive with `--all-groups`
- `--all-groups` : Enumerate site groups through Jira REST `/rest/api/3/group/bulk` and clean them using Admin API directory statuses; requires all four environment variables
- `-o`, `--org` : Organization ID for Atlassian Admin API (env: `ATLASSIAN_ORG`)
- `--exclude-group` : Group to skip when using `--all-groups`; repeat the option or provide comma-separated names
- `--dry-run` : Preview removals without executing them (default is live execution)
- `--out` : CSV file to write results (default: `atl_group_cleanup.csv`)

## Output

The script writes a CSV file with these columns:

- `group`
- `email`
- `name`
- `account_id`
- `account_status`
- `action`

Non-active users are marked as `would-remove` in dry-run mode and `removed` in live mode. Failed removals are recorded as `failed`.
