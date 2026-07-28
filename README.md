# AtlRemoveUsersGroup

Utility to plan or perform user suspensions for a batch of accounts.

Usage:

```powershell
python AtlRemoveUsersGroup.py --input users.csv         # dry-run (safe)
python AtlRemoveUsersGroup.py --input users.csv --execute  # actually perform actions
```

Input format: CSV, one username per row (username in first column).

Notes:
- The script defaults to dry-run and prints planned PowerShell `Disable-ADAccount` commands.
- Executing commands requires the machine to have the AD PowerShell module and appropriate permissions.
