import os
import sys
from dulwich.repo import Repo
from dulwich import porcelain

def sync_to_git(commit_message="Update Naukri Auto-Applier Pro software"):
    repo_path = os.path.abspath(os.path.dirname(__file__))
    
    if not os.path.exists(os.path.join(repo_path, '.git')):
        print("Initializing new Git repository...")
        repo = Repo.init(repo_path)
    else:
        repo = Repo(repo_path)

    print("Staging modified & new files...")
    porcelain.add(repo)

    try:
        commit_id = porcelain.commit(repo, message=commit_message.encode('utf-8'))
        print(f"Committed changes SHA: {commit_id.decode()[:7]}")
    except Exception as e:
        print(f"Commit status: {e}")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Updated software files"
    sync_to_git(msg)
