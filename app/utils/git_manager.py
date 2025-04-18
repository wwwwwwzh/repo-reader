import os
import dulwich.porcelain as git
from pathlib import Path
from dulwich.repo import Repo
from dulwich.client import get_transport_and_path

class GitManager:
    def __init__(self, cache_dir="/tmp/repos"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
    def clone(self, repo_url, update_if_exists=False):
        """
        Clone a repository or return an existing one
        
        Args:
            repo_url: URL of the git repository
            update_if_exists: Whether to check for and pull updates if repo exists
            
        Returns:
            tuple: (Repo object, repo path)
        """
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_path = self.cache_dir / repo_name
        
        if not repo_path.exists():
            # Repository doesn't exist locally, clone it
            git.clone(repo_url, str(repo_path), depth=1)
            return Repo(str(repo_path)), repo_path
        
        # Repository exists, check if we need to update
        if update_if_exists:
            # Check if there are new commits
            has_updates = self.has_new_commits(str(repo_path), repo_url)
            if has_updates:
                if isinstance(repo_path, Path):
                    repo_path = str(repo_path)
                # Pull the latest changes
                repo = Repo(repo_path)
                remote_refs = git.fetch(repo, repo_url)
                # Update the local HEAD to match remote
                for ref_name, sha in remote_refs.items():
                    if ref_name == b'refs/heads/main' or ref_name == b'HEAD':
                        repo.refs[b'refs/heads/main'] = sha
        
        return Repo(str(repo_path)), repo_path
    
    def has_new_commits(self, repo_path, repo_url, branch=b"refs/heads/main"):
        """
        Check if there are new commits in the remote repository
        
        Args:
            repo_path: Path to local repository
            repo_url: URL of remote repository
            branch: Branch name as bytes
            
        Returns:
            bool: True if there are new commits, False otherwise
        """
        # Open the local repository
        local_repo = Repo(repo_path)
        
        # Get the local commit hash
        try:
            local_hash = local_repo.refs[branch]
        except KeyError:
            # If the branch doesn't exist locally, assume there are new commits
            return True
        
        # Connect to the remote repository
        client, remote_path = get_transport_and_path(repo_url)
        
        # Get the remote references
        remote_refs = client.get_refs(remote_path)
        
        # Get the remote commit hash for the specified branch
        remote_hash = remote_refs.get(branch)
        
        # If we can't find the branch in the remote, assume no new commits
        if remote_hash is None:
            return False
        
        # Compare the hashes
        return local_hash != remote_hash