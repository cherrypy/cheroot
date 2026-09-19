# Contributing to Cheroot

**Ensure you set up pre-commit utility correctly** and tests pass in
GitHub Actions CI/CD workflows.

## Submitting Pull Requests

If you're changing the structure of the repository please create an issue
first. Don't forget to write appropriate test cases, add them into CI process
if applicable and make the GitHub Actions CI/CD build pass.

Sync (preferably rebase) your feature branch with upstream regularly to make
us able to merge your PR seamlessly.

Please fill out the pull request template that GitHub adds to your PR
description automatically when you open one -- it covers what kind of
change you're making, whether it affects user-facing behavior, and a
checklist reviewers expect to be addressed (tests, a `changelog` entry,
etc.). PRs that skip it may be closed without review.

If you're submitting this PR through an automated or AI-assisted tool
that posts directly via the GitHub API, the pull request template
isn't shown to you automatically the way it would be through the
GitHub web UI. Fetch `.github/PULL_REQUEST_TEMPLATE.md` directly
and fill it in yourself.

## Submitting bug reports

Make sure you are on latest changes and that you re-ran this command `tox`
after updating your local repository. If you can, please provide more
information about your environment such as browser, operating system,
python version, and any other related software versions. It is also helpful to
post a markdown snippet demonstrating minimum reproducible example of an issue.

## Also

See the fuller [contribution guidelines](https://cheroot.cherrypy.dev/en/latest/contributing/guidelines/)
for more detail, including code style, testing, and the change log
process.
