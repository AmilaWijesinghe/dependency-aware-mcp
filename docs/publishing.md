# Publishing to GitHub

The Git remote is already configured. Review and commit the restructured files
before pushing. No repository settings or remote contents are changed by the
local cleanup.

## Review the public contents

From the repository root:

```sh
git status --short
git add --dry-run .
git check-ignore backend/.env frontend/.env.local
```

Environment files, local databases, logs, environments, dependency folders,
generated reports, and `.local-archive/` are ignored. The two `.env.example`
templates and both dependency lockfiles are intended to be committed.

The cleanup checked the working source and existing Git history for common token
formats, private keys, credential-bearing connection strings, and tracked secret
filenames. The only credential-shaped historical URI found was a documentation
placeholder. Automated pattern checks cannot establish that every possible
secret format is absent; review any additional files before staging them.

## Commit and push

```sh
git add .
git diff --cached --stat
git diff --cached --check
git commit -m "Organize frontend and backend for public release"
git push origin HEAD
```

Use GitHub repository settings to select public visibility if needed. A public
repository can be viewed without granting an open-source license; choose and
add a license if you want to grant reuse rights. No license was selected during
this cleanup.
