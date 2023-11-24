import os
import re
import sys
import xml.etree.ElementTree as ET

import requests
from git import Commit, Repo, TagReference

GIT_MESSAGE_PREFIX = [
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "feature",
    "fix",
    "perf",
    "refactor",
    "style",
    "test",
]


def get_last_tag(repo: Repo, branch_name: str) -> TagReference:
    # Get the last tag in the given branch
    tags = [repo.tag(tag) for tag in repo.git.tag("--merged", branch_name).split("\n")]
    last_tag = max(tags, key=lambda tag: tag.commit.committed_date) if tags else None
    return last_tag


def get_commits_between(repo: Repo, start_commit: Commit, end_commit: Commit) -> list[Commit]:
    commits = list(repo.iter_commits(rev=f"{start_commit}..{end_commit}"))
    print("Commits:")
    for commit in commits:
        print(f" - {commit.summary}")
    return commits


def is_new_release(commits: list[Commit] = []):
    for commit in commits:
        if commit.summary.startswith(tuple(GIT_MESSAGE_PREFIX)):
            return True
    return False


def add_github_output(name, value):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"{name}={value}\n")


def create_gh_release(tag_name: str):
    github_token = os.environ["GITHUB_TOKEN"]
    github_repository = os.environ["GITHUB_REPOSITORY"]
    github_api_endpoint = f"https://api.github.com/repos/{github_repository}/releases"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {
        "tag_name": tag_name,
        "name": tag_name,
        "prerelease": True if len(tag_name.split("-")) > 1 else False,
        "make_latest": "false" if len(tag_name.split("-")) > 1 else "true"
    }
    with requests.post(github_api_endpoint, json=data, headers=headers) as r:
        if r.status_code == requests.codes.created:
            print("Release created")
        else:
            print(r.status_code)
            print(r.text)


def main():
    repo = Repo(os.environ["GITHUB_WORKSPACE"])

    current_branch = repo.active_branch.name
    last_tag = get_last_tag(repo, current_branch)
    last_tag_commit = last_tag.commit if last_tag else None
    print(f"current tag: {last_tag.name}")

    # check if empty
    commits = get_commits_between(repo, last_tag_commit, repo.active_branch.commit)
    create_new_release = is_new_release(commits)

    if create_new_release:
        blob = repo.head.commit.tree["pom.xml"]
        ns = "{http://maven.apache.org/POM/4.0.0}"
        pom = ET.fromstring(blob.data_stream.read().decode())

        pom_version = pom.find(f"{ns}version").text

        if current_branch in ["master"]:
            version_string = pom_version
        else:
            pre_release = re.sub(r"[^\w\s]", ".", current_branch).lower()
            last_tag_build = last_tag.name.removeprefix(f"v{pom_version}-{pre_release}.")
            if last_tag_build.isnumeric():
                build = int(last_tag_build) + 1
            else:
                build = 1
            version_string = f"v{pom_version}-{pre_release}.{build}"

        print(f"new tag: {version_string}")
        new_tag = repo.create_tag(version_string)
        repo.remotes.origin.push(new_tag)
        create_gh_release(version_string)
        add_github_output("new_release_version", version_string)

    add_github_output("new_release", "true" if create_new_release else "false")


if __name__ == '__main__':
    sys.exit(main())
