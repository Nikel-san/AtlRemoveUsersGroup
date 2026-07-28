

"""
AtlRemoveUsersGroup.py

Implements Atlassian Cloud group cleanup per ICC-1: list group members,
lookup org account statuses, and remove non-active users from a specified
group. Defaults to dry-run; use `--execute` to perform deletions.

Environment variables (required):
- ATLASSIAN_TOKEN: Bearer token for Admin API
- ATLASSIAN_ORG: Organization ID for Admin API
- JIRA_EMAIL: Service account email for Jira REST API (Basic auth)
- JIRA_PAT: API token for Jira REST API (Basic auth)
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LOG = logging.getLogger(__name__)


def normalize_site(site: str) -> str:
	clean_site = site.strip()
	if clean_site.startswith("http://") or clean_site.startswith("https://"):
		parsed = urlparse(clean_site)
		clean_site = parsed.netloc
	if clean_site.endswith("/"):
		clean_site = clean_site[:-1]
	return clean_site


def create_request_session() -> requests.Session:
	session = requests.Session()
	retry = Retry(
		total=3,
		read=3,
		connect=3,
		backoff_factor=0.5,
		status_forcelist=(429, 500, 502, 503, 504),
		allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]),
	)
	adapter = HTTPAdapter(max_retries=retry)
	session.mount("https://", adapter)
	session.mount("http://", adapter)
	return session


def request_with_retries(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
	kwargs.setdefault("timeout", 30)
	return session.request(method, url, **kwargs)


def _extract_list(data: Any, *keys: str) -> List[Any]:
	if isinstance(data, list):
		return data
	if not isinstance(data, dict):
		return []
	for key in keys:
		value = data.get(key)
		if isinstance(value, list):
			return value
		if isinstance(value, dict):
			for nested_key in ("users", "values"):
				nested_value = value.get(nested_key)
				if isinstance(nested_value, list):
					return nested_value
	return []


def get_jira_auth() -> Optional[tuple]:
	email = os.getenv("JIRA_EMAIL")
	token = os.getenv("JIRA_PAT")
	if not email or not token:
		return None
	return (email, token)


def get_admin_token() -> Optional[str]:
	return os.getenv("ATLASSIAN_TOKEN")


def fetch_group_members(session: requests.Session, site: str, group: str, auth: tuple) -> List[dict]:
	members: List[dict] = []
	url = f"https://{site}/rest/api/3/group/member"
	start_at = 0
	max_results = 50
	params = {"groupname": group, "startAt": start_at, "maxResults": max_results}
	while True:
		resp = request_with_retries(session, "GET", url, params=params, auth=auth)
		resp.raise_for_status()
		data = resp.json()
		page_members = _extract_list(data, "values", "members", "users", "results")
		members.extend(page_members)
		next_url = get_next_link(resp, data)
		if next_url:
			url = next_url
			params = None
			continue
		if params is None:
			break
		# determine pagination fallback
		total = data.get("total")
		if total is not None:
			start_at += max_results
			if start_at >= total:
				break
		else:
			# fallback: stop when fewer than page size returned
			if len(page_members) < max_results:
				break
			start_at += max_results
			params["startAt"] = start_at
	return members


def fetch_org_user_status_map(session: requests.Session, org_id: str, token: str) -> Dict[str, str]:
	headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
	url = f"https://api.atlassian.com/admin/v1/orgs/{org_id}/users"
	params = {"page": 1, "limit": 100}
	status_map: Dict[str, str] = {}
	while True:
		resp = request_with_retries(session, "GET", url, headers=headers, params=params)
		resp.raise_for_status()
		data = resp.json()
		# data may contain 'values' or 'users' or be a list
		items = _extract_list(data, "values", "users", "items", "results")

		for u in items:
			# account_id vs accountId
			acct = u.get("account_id") or u.get("accountId")
			status = u.get("account_status") or u.get("accountStatus") or u.get("status")
			if acct:
				status_map[str(acct)] = status or "unknown"

		next_url = get_next_link(resp, data)
		if next_url:
			url = next_url
			params = None
			continue
		if params is None:
			break
		# pagination: check if response indicates next page
		# increase page param until no items returned
		if not items or len(items) < params["limit"]:
			break
		params["page"] += 1
	return status_map


def remove_user_from_group(session: requests.Session, site: str, group: str, account_id: str, auth: tuple) -> bool:
	url = f"https://{site}/rest/api/3/group/user"
	params = {"groupname": group, "accountId": account_id}
	resp = request_with_retries(session, "DELETE", url, params=params, auth=auth)
	return resp.status_code in (200, 204)


def write_csv(path: Path, rows: Iterable[Dict[str, str]]) -> None:
	fieldnames = ["accountId", "displayName", "email", "account_status", "action", "error"]
	with path.open("w", newline="", encoding="utf-8") as fh:
		writer = csv.DictWriter(fh, fieldnames=fieldnames)
		writer.writeheader()
		for r in rows:
			writer.writerow({k: r.get(k, "") for k in fieldnames})


def build_arg_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(description="Remove non-active users from Atlassian Cloud group (dry-run default)")
	p.add_argument("-s", "--site", required=True, help="Atlassian site (e.g., yoursite.atlassian.net)")
	p.add_argument("-g", "--group", required=True, help="Group name to clean")
	mode_group = p.add_mutually_exclusive_group()
	mode_group.add_argument("--execute", action="store_true", help="Actually remove users")
	mode_group.add_argument("--dry-run", action="store_true", help="Do not remove users; only report planned actions")
	p.add_argument("--output", default="removals.csv", help="CSV file to write results")
	return p


def get_next_link(resp: requests.Response, data: Any) -> Optional[str]:
	next_url = resp.links.get("next", {}).get("url") if resp.links else None
	if next_url:
		return next_url
	links = data.get("links") or data.get("_links") or {}
	next_link = links.get("next")
	if isinstance(next_link, dict):
		return next_link.get("href")
	if isinstance(next_link, str):
		return next_link
	return None


def main(argv: List[str] | None = None) -> int:
	parser = build_arg_parser()
	args = parser.parse_args(argv)

	dry_run = args.dry_run or not args.execute

	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

	jira_auth = get_jira_auth()
	if not jira_auth:
		LOG.error("Missing JIRA_EMAIL or JIRA_PAT environment variables")
		return 2

	admin_token = get_admin_token()
	org_id = os.getenv("ATLASSIAN_ORG")
	if not admin_token or not org_id:
		LOG.error("Missing ATLASSIAN_TOKEN or ATLASSIAN_ORG environment variables")
		return 2

	site = normalize_site(args.site)
	request_session = create_request_session()

	LOG.info("Fetching members of group '%s' on site %s", args.group, site)
	try:
		members = fetch_group_members(request_session, site, args.group, jira_auth)
	except Exception as exc:
		LOG.exception("Failed to fetch group members: %s", exc)
		return 3

	LOG.info("Fetching org user statuses for org %s", org_id)
	try:
		status_map = fetch_org_user_status_map(request_session, org_id, admin_token)
	except Exception as exc:
		LOG.exception("Failed to fetch org users: %s", exc)
		return 4

	results: List[Dict[str, str]] = []
	for m in members:
		account_id = m.get("accountId") or m.get("account_id")
		display = m.get("displayName") or m.get("name") or ""
		email = m.get("emailAddress") or m.get("email") or ""
		acct_status = status_map.get(str(account_id), "unknown") if account_id else "unknown"

		row = {"accountId": account_id or "", "displayName": display, "email": email, "account_status": acct_status}
		if acct_status and acct_status.lower() != "active":
			row["action"] = "will-remove" if dry_run else "removed"
			row["error"] = ""
			if not dry_run and account_id:
				try:
					ok = remove_user_from_group(request_session, site, args.group, account_id, jira_auth)
					if not ok:
						row["error"] = "remove-failed"
				except Exception as exc:
					row["error"] = str(exc)
		else:
			row["action"] = "skip"
			row["error"] = ""
		results.append(row)

	out_path = Path(args.output)
	write_csv(out_path, results)
	LOG.info("Wrote results to %s", out_path)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

