import subprocess

from datetime import datetime
from tempfile import mkdtemp
from typing import Optional

from . import Abort, debug, info


class Git:
    """Provides access to a local Git repository."""

    def __init__(self, repo: str, token: str) -> None:
        self._repo = repo
        self._token = token
        self._default_branch = ""
        self.__dir: Optional[str] = None

    @property
    def _dir(self) -> str:
        """Get the repository clone location (cloning if necessary)."""
        if self.__dir is not None:
            return self.__dir
        url = f"https://oauth2:{self._token}@github.com/{self._repo}"
        dest = mkdtemp(prefix="tagbot_repo_")
        self.command("clone", url, dest, repo=None)
        self.__dir = dest
        self._default_branch = self.command("rev-parse", "--abbrev-ref", "HEAD")
        return self.__dir

    def command(self, *argv: str, repo: Optional[str] = "") -> str:
        """Run a Git command."""
        args = ["git"]
        if repo is not None:
            # Ideally, we'd set self._dir as the default for repo,
            # but it gets evaluated at method definition.
            args.extend(["-C", repo or self._dir])
        args.extend(argv)
        cmd = " ".join(args)
        debug(f"Running '{cmd}'")
        proc = subprocess.run(args, text=True, capture_output=True)
        out = proc.stdout.strip()
        if proc.returncode:
            if out:
                info(out)
            if proc.stderr:
                info(proc.stderr.strip())
            raise Abort(f"Git command '{cmd}' failed")
        return out

    def check(self, *argv: str, repo: Optional[str] = "") -> bool:
        """Run a Git command, but only return its success status."""
        try:
            self.command(*argv, repo=repo)
            return True
        except Abort:
            return False

    def commit_sha_of_default(self) -> str:
        return self.command("rev-parse", self._default_branch)

    def set_remote_url(self, url: str) -> None:
        """Update the origin remote URL."""
        self.command("remote", "set-url", "origin", url)

    def config(self, key: str, val: str) -> None:
        """Configure the repository."""
        self.command("config", key, val)

    def create_tag(self, version: str, sha: str, annotate: bool = False) -> None:
        """Create and push a Git tag."""
        args = ["tag"]
        if annotate:
            args.extend(["-m", version])
        self.command(*args, version, sha)
        self.command("push", "origin", version)

    def fetch_branch(self, branch: str) -> bool:
        """Try to checkout a remote branch, and return whether or not it succeeded."""
        # Git lets us check out remote branches without the remote name,
        # and automatically creates a local branch that tracks the remote one.
        # Git does not let us do the same with a merge, so this method must be called
        # before we call merge_and_delete_branch.
        if not self.check("checkout", branch):
            return False
        self.command("checkout", self._default_branch)
        return True

    def can_fast_forward(self, branch: str) -> bool:
        """Check whether the default branch can be fast-forwarded to branch."""
        # https://stackoverflow.com/a/49272912
        return self.check("merge-base", "--is-ancestor", self._default_branch, branch)

    def merge_and_delete_branch(self, branch: str) -> None:
        """Merge a branch into master and delete the branch."""
        self.command("checkout", self._default_branch)
        self.command("merge", branch)
        self.command("push", "origin", self._default_branch)
        self.command("push", "-d", "origin", branch)

    def time_of_commit(self, sha: str) -> datetime:
        """Get the time that a commit was made."""
        # The format %cI is "committer date, strict ISO 8601 format".
        date = self.command("show", "-s", "--format=%cI", sha)
        dt = datetime.fromisoformat(date)
        # Convert to UTC and remove time zone information.
        offset = dt.utcoffset()
        if offset:
            dt -= offset
        return dt.replace(tzinfo=None)
