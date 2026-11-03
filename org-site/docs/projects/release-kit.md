# release-kit

**The Buchochelliq Labs release standard.**

One file, `release-kit.yml`, declares the packages that a repository publishes. One command,
`release.py tag`, tags a release. One workflow run then does the rest:

- checks the release and reruns CI on the tagged commit
- builds the artifacts and publishes them to GitHub Releases, crates.io, PyPI, npm and the VS Code Marketplace
- waits for each registry to serve the new version, then installs and tries each package the way a new user would

[Read the documentation](https://buchochelliq-labs.github.io/release-kit/){ .md-button .md-button--primary }
[release-kit on GitHub](https://github.com/buchochelliq-labs/release-kit){ .md-button }

## The rules

1. **A published version is permanent.** Nothing on its registry is tagged, selected or uploaded again.
2. **Releases come from the default branch.** Every tag points at a commit on `main`.
3. **Tags are records.** They are annotated and record the release and the commit, with one tag per package plus the release tag that starts the run.
4. **A release is one commit.** The same version may not ship different files from two commits.
5. **Re-run, don't repair.** After a failure, fix the cause and run `release.py tag` again.
6. **Least privilege.** Only publish jobs have write access. They use Trusted Publishing in protected environments, with actions pinned to commits.
