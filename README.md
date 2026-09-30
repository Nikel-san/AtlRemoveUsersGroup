# AtlRemoveUsersGroup

Remove inactive, deactivated, or suspended users from one or every Atlassian Cloud group.

This script fetches group members from a Jira site and removes users whose account status is explicitly `inactive`, `deactivated`, or `suspended`. With `--all-groups`, it reads organization directory statuses and applies the cleanup to every organization group. Active, invited, invitation-pending, and unknown-status users remain in their groups.

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
python AtlRemoveUsersGroup.py --site your-site.atlassian.net --group "your-group"
python AtlRemoveUsersGroup.py --site your-site.atlassian.net --all-groups --exclude-group "critical-group" --dry-run
python AtlRemoveUsersGroup.py --site your-site.atlassian.net --group "your-group" --exclude-domain example.com,example.org --dry-run
python AtlRemoveUsersGroup.py --site your-site.atlassian.net --all-groups --exclude-domain example.com --allow-unverified-external --dry-run
```

Live execution is the default. Add `--dry-run` to preview removals without changing group membership.

## Options

- `-s`, `--site` : Atlassian site hostname, for example `example.atlassian.net` (env: `ATLASSIAN_SITE`)
- `-s`, `--site` : Atlassian site hostname, for example `your-site.atlassian.net` (env: `ATLASSIAN_SITE`)
- `-g`, `--group` : One group name to clean; mutually exclusive with `--all-groups`
- `--all-groups` : Enumerate site groups through Jira REST `/rest/api/3/group/bulk` and clean them using Admin API directory statuses; requires all four environment variables
- `-o`, `--org` : Organization ID for Atlassian Admin API (env: `ATLASSIAN_ORG`)
- `--exclude-group` : Group to skip when using `--all-groups`; repeat the option or provide comma-separated names
- `--exclude-domain` : Never remove accounts whose email domain matches; repeat the option or provide comma-separated domains. A leading `@` is optional, and matching is case-insensitive and exact.
- `--allow-unverified-external` : With `--exclude-domain`, allow removal of unresolved accounts missing from the organization directory. Requires `ATLASSIAN_ORG` and `ATLASSIAN_TOKEN`.
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
- `reason`

Inactive, deactivated, and suspended users are marked as `would-remove` in dry-run mode and `removed` in live mode. For `--all-groups`, accounts missing from the organization directory use Jira's member `active` flag only when `accountType` is `atlassian`, and their CSV status is `inactive (jira)` or `active (jira)`. Other account types remain `kept` with status `unknown`. Email is looked up in the organization directory first and Jira user API second when a removable member needs domain verification. Active, invited, invitation-pending, and unknown-status users are otherwise kept. Failed removals are recorded as `failed`. With `--exclude-domain`, matching removable users are recorded as `skipped` with reason `Excluded domain`. By default, an unresolved email is skipped with reason `Email unknown — domain exclusion cannot be verified`.

`--allow-unverified-external` is opt-in and requires `ATLASSIAN_ORG` and `ATLASSIAN_TOKEN`. If a removable account has no resolvable email and is not in the organization directory, it may be removed with reason `External, not in org directory`; directory members with unknown email are still skipped. Only use this flag when every domain passed to `--exclude-domain` is verified in the organization and managed accounts always appear in its directory. Do not use it when excluding unverified partner domains.
