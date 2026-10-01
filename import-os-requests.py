import os, requests
auth = (os.getenv("JIRA_EMAIL"), os.getenv("JIRA_PAT"))
r = requests.get("https://iderawebdev.atlassian.net/rest/api/3/user",
                 params={"accountId": "5b2ace87d85e5b59b06715a0"}, auth=auth)
d = r.json()
print(d.get("displayName"), d.get("accountType"), d.get("active"), d.get("emailAddress"))