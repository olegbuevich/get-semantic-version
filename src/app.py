import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from git import Commit, Repo, TagReference
from jinja2 import Template

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

    if branch_name  == "master":
        tags = [repo.tag(tag) for tag in repo.git.tag("--merged", branch_name).split("\n")]
    else:
        filter = re.sub(r"[^\w\s]", ".", branch_name).lower()
        tags = [
            repo.tag(tag) for tag in repo.git.tag("--merged", branch_name).split("\n") if filter in tag
        ]

    last_tag = max(tags, key=lambda tag: tag.commit.committed_date) if tags else None
    return last_tag


def get_commits_between(repo: Repo, start_commit: Commit, end_commit: Commit) -> list[Commit]:
    commits = list(repo.iter_commits(rev=f"{start_commit}..{end_commit}"))
    if commits:
        print("Commits:")
        for commit in commits:
            print(f" - {commit.summary}")
    return commits


def get_commit_summary_regex() -> re.Pattern:
    prefix_match = "|".join([fr"\b{prefix}\b" for prefix in GIT_MESSAGE_PREFIX])
    commit_summary_regex = re.compile(fr"""^(?P<type>{prefix_match})  # prefix
                            (\((?P<issue>\S*)\))?  # issue
                            :\s+  # separator
                            (?P<comment>.*)$ # comment
                            """, re.IGNORECASE | re.VERBOSE)
    # print(commit_summary_regex)
    return commit_summary_regex


def is_new_release(commits: list[Commit] = []):
    commit_summary_regex = get_commit_summary_regex()
    for commit in commits:
        if commit_summary_regex.match(commit.summary):
            return True
    return False


def generate_release_notes(version: str, commits: list[Commit] = []) -> str:
    commit_summary_regex = get_commit_summary_regex()
    version_feature = []
    version_fix = []
    version_other = []
    for commit in commits:
        semver_commit = commit_summary_regex.match(commit.summary)
        if semver_commit:
            commit_info = semver_commit.groupdict()
            if commit_info.get("type") in ["fix"]:
                version_fix.append(commit_info)
            else:
                version_feature.append(commit_info)
        else:
            version_other.append(commit.summary)

    with open(Path(__file__).absolute().parent / "templates/release-notes.md.j2") as f:
        template = Template(f.read())
    return template.render({
        "version": version,
        "version_feature": version_feature,
        "version_fix": version_fix,
        "version_other": version_other
    })


def add_github_output(name, value):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"{name}={value}\n")


def create_gh_release(tag_name: str, release_notes: str):
    github_token = os.environ["GITHUB_TOKEN"]
    github_repository = os.environ["GITHUB_REPOSITORY"]
    github_api_url = os.environ["GITHUB_API_URL"]
    github_api_endpoint = f"{github_api_url}/repos/{github_repository}/releases"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {
        "tag_name": tag_name,
        "name": tag_name,
        "prerelease": True if len(tag_name.split("-")) > 1 else False,
        "make_latest": "false" if len(tag_name.split("-")) > 1 else "true",
        "body": release_notes
    }
    with requests.post(github_api_endpoint, json=data, headers=headers) as r:
        if r.status_code == requests.codes.created:
            print("Release created")
        else:
            print(r.status_code)
            print(r.text)


def get_repo_type(repo: Repo) -> str:
    if "pom.xml" in repo.head.commit.tree:
        return "maven"
    if "package.json" in repo.head.commit.tree:
        return "nodejs"
    return "unknown"


def main():
    repo = Repo(os.environ["GITHUB_WORKSPACE"])

    dry_run = os.environ.get("GITHUB_ACTIONS") != "true"
    if dry_run:
        print("dry-run mode!")

    repo_type = get_repo_type(repo)
    print(f"{repo_type} project detected")
    if repo_type == "unknown":
        return 1

    current_branch = repo.active_branch.name
    last_tag = get_last_tag(repo, current_branch)
    print(f"current tag: {last_tag.name if last_tag else 'None'}")
    last_tag_commit = last_tag.commit if last_tag else None

    # check if empty
    commits = get_commits_between(repo, last_tag_commit, repo.active_branch.commit)
    create_new_release = is_new_release(commits)

    if create_new_release or dry_run:
        if repo_type == "maven":
            blob = repo.head.commit.tree["pom.xml"]
            ns = "{http://maven.apache.org/POM/4.0.0}"
            pom = ET.fromstring(blob.data_stream.read().decode())
            version_number = pom.find(f"{ns}version").text
        if repo_type == "nodejs":
            blob = repo.head.commit.tree["package.json"]
            package_json = json.loads(blob.data_stream.read())
            version_number = package_json["version"]

        if current_branch in ["master"]:
            version_string = version_number
        else:
            pre_release = re.sub(r"[^\w\s]", ".", current_branch).lower()
            last_tag_build = last_tag.name.removeprefix(f"v{version_number}-{pre_release}.") if last_tag else ""
            if last_tag_build.isnumeric():
                build_number = int(last_tag_build) + 1
            else:
                build_number = 1
            version_string = f"v{version_number}-{pre_release}.{build_number}"

        print(f"new tag: {version_string}")
        if not dry_run:
            new_tag = repo.create_tag(version_string)
            repo.remotes.origin.push(new_tag)
            release_notes = generate_release_notes(version_string, commits)
            create_gh_release(version_string, release_notes)
            add_github_output("new_release_version", version_string)


    if not dry_run:
        add_github_output("new_release", "true" if create_new_release else "false")

    return 0


if __name__ == '__main__':
    sys.exit(main())
