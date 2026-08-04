

"""
AtlRemoveUsersGroup.py

Implements Atlassian Cloud group cleanup per ICC-1: list group members,
lookup org account statuses, and remove non-active users from a specified
group. Use `--dry-run` to preview deletions without performing them.

Environment variables:
- JIRA_EMAIL: Service account email for Jira REST API (Basic auth)
- JIRA_PAT: API token for Jira REST API (Basic auth)
- ATLASSIAN_TOKEN / ATLASSIAN_ORG: optional legacy values; no longer required for the removal decision
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ANSI_RESET = "\033[0m"
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"
ANSI_GREEN = "\033[32m"


def warn(message: str) -> None:
	print(f"{ANSI_YELLOW}WARN{ANSI_RESET}: {message}", file=sys.stderr)


def success(message: str) -> None:
	print(f"{ANSI_GREEN}SUCCESS{ANSI_RESET}: {message}")


def error(message: str) -> None:
	print(f"{ANSI_RED}ERROR{ANSI_RESET}: {message}", file=sys.stderr)


def normalize_site(site: str) -> str:
	clean_site = (site or "").strip()
	if not clean_site:
		raise ValueError("Atlassian site is required; provide --site or set ATLASSIAN_SITE")
	if clean_site.startswith("http://") or clean_site.startswith("https://"):
		parsed = urlparse(clean_site)
		clean_site = parsed.netloc or parsed.path
	clean_site = clean_site.rstrip("/")
	if not clean_site:
		raise ValueError("Atlassian site is required; provide --site or set ATLASSIAN_SITE")
	if clean_site.startswith("www."):
		clean_site = clean_site[4:]
	if "." not in clean_site:
		raise ValueError("Atlassian site must be a fully qualified hostname, for example example.atlassian.net")
	return clean_site


def build_base_url(site: str) -> str:
	return f"https://{normalize_site(site)}"


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


def is_member_active(member: dict) -> bool:
	active_value = member.get("active", True)
	if isinstance(active_value, bool):
		return active_value
	if isinstance(active_value, str):
		return active_value.strip().lower() in {"true", "1", "yes", "y"}
	return bool(active_value)


def fetch_group_members(session: requests.Session, site: str, group: str, auth: tuple) -> List[dict]:
	members: List[dict] = []
	url = f"{build_base_url(site)}/rest/api/3/group/member"
	start_at = 0
	max_results = 50
	params = {
		"groupname": group,
		"startAt": start_at,
		"maxResults": max_results,
		"includeInactiveUsers": True,
	}
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
	url = f"{build_base_url(site)}/rest/api/3/group/user"
	params = {"groupname": group, "accountId": account_id}
	resp = request_with_retries(session, "DELETE", url, params=params, auth=auth)
	return resp.status_code in (200, 204)


def write_results_csv(path: Path, rows: Iterable[Dict[str, str]]) -> None:
	fieldnames = ["email", "name", "account_id", "account_status", "action"]
	with path.open("w", newline="", encoding="utf-8") as fh:
		writer = csv.DictWriter(fh, fieldnames=fieldnames)
		writer.writeheader()
		for r in rows:
			writer.writerow({k: r.get(k, "") for k in fieldnames})


def build_arg_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(description="Remove non-active users from Atlassian Cloud group")
	p.add_argument(
		"-s",
		"--site",
		default=os.getenv("ATLASSIAN_SITE"),
		help="Atlassian site hostname, e.g. example.atlassian.net (default: ATLASSIAN_SITE env var)",
	)
	p.add_argument("-g", "--group", required=True, help="Group name to clean")
	p.add_argument("-o", "--org", default=os.getenv("ATLASSIAN_ORG"), help="Organization ID (default: ATLASSIAN_ORG env var)")
	p.add_argument("--dry-run", action="store_true", help="Preview removals without executing them")
	p.add_argument("--out", default="atl_group_cleanup.csv", help="CSV file to write results")
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


def get_available_filename(output_dir: Path, filename: str) -> Path:
	path = output_dir / filename
	if not path.exists():
		return path

	stem = path.stem
	suffix = path.suffix
	index = 1
	while True:
		candidate = output_dir / f"{stem}_{index}{suffix}"
		if not candidate.exists():
			return candidate
		index += 1


def main(argv: List[str] | None = None) -> int:
	parser = build_arg_parser()
	args = parser.parse_args(argv)

	if not args.site:
		parser.error("--site is required when ATLASSIAN_SITE env var is not set")

	try:
		site = normalize_site(args.site)
	except ValueError as exc:
		parser.error(str(exc))

	dry_run = args.dry_run

	jira_auth = get_jira_auth()
	if not jira_auth:
		error("Missing JIRA_EMAIL or JIRA_PAT environment variables")
		return 2

	request_session = create_request_session()

	warn(f"Fetching members of group '{args.group}' on site {site}")
	try:
		members = fetch_group_members(request_session, site, args.group, jira_auth)
	except Exception as exc:
		error(f"Failed to fetch group members: {exc}")
		return 3

	results: List[Dict[str, str]] = []
	active_kept = 0
	non_active = 0
	failed = 0
	for m in members:
		account_id = m.get("accountId") or m.get("account_id")
		display = m.get("displayName") or m.get("name") or ""
		email = m.get("emailAddress") or m.get("email") or ""
		is_active = is_member_active(m)
		row = {
			"email": email,
			"name": display,
			"account_id": account_id or "",
			"account_status": "active" if is_active else "inactive",
			"action": "",
		}
		if is_active:
			active_kept += 1
			row["action"] = "kept"
		else:
			non_active += 1
			if dry_run:
				warn(f"[DRY-RUN] Would remove {display or account_id} from {args.group}")
				row["action"] = "would-remove"
			else:
				try:
					if remove_user_from_group(request_session, site, args.group, account_id, jira_auth):
						row["action"] = "removed"
						success(f"Removed {display or account_id} from {args.group}")
					else:
						row["action"] = "failed"
						failed += 1
						error(f"Failed to remove {display or account_id} from {args.group}")
				except Exception as exc:
					row["action"] = "failed"
					failed += 1
					error(f"Failed to remove {display or account_id} from {args.group}: {exc}")
		results.append(row)

	out_path = Path(args.out)
	if not out_path.is_absolute():
		out_path = Path.cwd() / out_path
	out_path = get_available_filename(out_path.parent, out_path.name)
	write_results_csv(out_path, results)
	success(f"Results written to {out_path}")
	print("Summary:")
	print(f"  Group members total: {len(members)}")
	print(f"  Active (kept): {active_kept}")
	print(f"  Non-active ({'would remove' if dry_run else 'removed'}): {non_active - failed}")
	print(f"  Failed: {failed}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

